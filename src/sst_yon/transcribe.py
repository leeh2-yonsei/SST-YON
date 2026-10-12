"""Transcribe local media with faster-whisper, without an external API."""

import argparse
from contextlib import ExitStack
from importlib.metadata import distribution, PackageNotFoundError
import os
from pathlib import Path
import sys
import tempfile

from rich.markup import escape
from rich.progress import (
    BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn,
    TimeElapsedColumn, TimeRemainingColumn,
)


AUDIO_SUFFIXES = {".mp3", ".mp4", ".wav", ".flac", ".m4a", ".ogg", ".opus", ".webm"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="faster-whisper로 로컬 음성 파일을 텍스트로 변환합니다.")
    parser.add_argument(
        "inputs", nargs="*", type=Path,
        help="음성 파일 또는 폴더 (기본값: asset/mp3, 하위 폴더 제외)",
    )
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("asset/txt"))
    add_transcription_arguments(parser)
    return parser


def add_transcription_arguments(parser: argparse.ArgumentParser) -> None:
    """Share model options with the download-to-transcription pipeline."""
    parser.add_argument("--model", default="turbo", help="모델 이름 또는 로컬 모델 경로 (기본값: turbo)")
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    parser.add_argument(
        "--compute-type", choices=["int8_float16", "float16", "int8", "float32"],
        help="기본값: CUDA는 int8_float16, CPU는 int8",
    )
    parser.add_argument("--beam-size", type=int, default=5, help="디코딩 beam 크기 (기본값: 5)")
    parser.add_argument("-l", "--language", help="음성 언어 (예: ko, en). 생략 시 자동 감지")
    parser.add_argument("--initial-prompt", help="전문 용어 등 인식을 도울 문맥")
    parser.add_argument("--no-vad", action="store_true", help="무음 구간 필터 끄기")
    parser.add_argument(
        "--model-dir", type=Path, default=Path(".cache/whisper"),
        help="모델 다운로드 캐시 (기본값: .cache/whisper)",
    )
    parser.add_argument("--local-files-only", action="store_true", help="모델 다운로드 없이 캐시만 사용")
    parser.add_argument("--overwrite", action="store_true", help="기존 전사 결과 덮어쓰기")


def validate_options(parser: argparse.ArgumentParser, args: argparse.Namespace) -> str:
    if args.beam_size < 1:
        parser.error("--beam-size는 1 이상이어야 합니다.")
    compute_type = args.compute_type or ("int8_float16" if args.device == "cuda" else "int8")
    if args.device == "cpu" and compute_type in {"float16", "int8_float16"}:
        parser.error("CPU에서는 --compute-type int8 또는 float32를 사용하세요.")
    return compute_type


def add_windows_cuda_paths(stack: ExitStack) -> None:
    """Make DLLs from the optional CUDA wheels visible to this process."""
    if sys.platform != "win32":
        return
    directories: set[Path] = set()
    for name in ("nvidia-cublas-cu12", "nvidia-cudnn-cu12", "nvidia-cuda-nvrtc-cu12"):
        try:
            package = distribution(name)
        except PackageNotFoundError:
            continue
        for file in package.files or []:
            if str(file).lower().endswith(".dll"):
                directories.add(Path(package.locate_file(file)).resolve().parent)
    if directories:
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = os.pathsep.join([*(str(path) for path in sorted(directories)), old_path])
        stack.callback(os.environ.__setitem__, "PATH", old_path)
        for path in sorted(directories):
            stack.enter_context(os.add_dll_directory(str(path)))


def print_cuda_help() -> None:
    print(
        "Windows CUDA DLL 누락 시 uv sync --extra cuda 후 "
        "uv run --extra cuda transcribe로 실행하세요. "
        "GPU 메모리 부족 시 --model medium을 사용하세요. "
        "CPU 사용: --device cpu --model small",
        file=sys.stderr,
    )


def is_cuda_error(exc: Exception) -> bool:
    """Only suggest CUDA fixes when the error actually mentions GPU execution."""
    message = str(exc).lower()
    return any(
        term in message
        for term in ("cuda", "cudnn", "cublas", "gpu", "out of memory")
    )


def collect_sources(inputs: list[Path]) -> list[Path]:
    sources: list[Path] = []
    for source in inputs or [Path("asset/mp3")]:
        if source.is_dir():
            sources.extend(sorted(
                path.resolve() for path in source.iterdir()
                if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES
            ))
        elif source.is_file():
            sources.append(source.resolve())
        else:
            raise ValueError(f"입력 파일 또는 폴더를 찾을 수 없습니다: {source}")
    sources = list(dict.fromkeys(sources))
    if not sources:
        raise ValueError("전사할 음성 파일이 없습니다.")
    return sources


def prepare_jobs(sources: list[Path], output_dir: Path, overwrite: bool) -> dict[Path, Path]:
    """Validate all output paths before downloading or loading a model."""
    jobs: dict[Path, Path] = {}
    for source in sources:
        target = output_dir.resolve() / f"{source.stem}.txt"
        if target == source:
            raise ValueError(f"입력과 출력 경로가 같습니다: {source}")
        if target in jobs:
            raise ValueError(f"출력 이름이 겹칩니다. 출력 폴더를 나누세요: {target.name}")
        if target.exists() and not overwrite:
            raise ValueError(f"출력 파일이 이미 있습니다 (--overwrite로 덮어쓰기): {target}")
        jobs[target] = source
    return jobs


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    compute_type = validate_options(parser, args)
    try:
        sources = collect_sources(args.inputs)
        jobs = prepare_jobs(sources, args.output_dir, args.overwrite)
        args.output_dir.mkdir(parents=True, exist_ok=True)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))

    # Import after argument parsing so --help never loads native libraries.
    with ExitStack() as stack:
        progress = stack.enter_context(Progress(
            SpinnerColumn(), TextColumn("{task.description}"), BarColumn(),
            TaskProgressColumn(), TextColumn("{task.fields[detail]}"),
            TimeElapsedColumn(), TimeRemainingColumn(),
        ))
        loading_task = progress.add_task(
            "모델 로딩", total=None,
            detail=escape(f"{args.model} / {args.device} / {compute_type}"),
        )
        try:
            if args.device == "cuda":
                add_windows_cuda_paths(stack)
            from faster_whisper import WhisperModel

            model = WhisperModel(
                args.model, device=args.device, compute_type=compute_type,
                download_root=str(args.model_dir.resolve()),
                local_files_only=args.local_files_only,
            )
        except Exception as exc:
            # Download and native-library errors have different exception types.
            progress.stop_task(loading_task)
            progress.update(loading_task, description="모델 로딩 실패")
            print(f"모델 로딩 실패: {exc}", file=sys.stderr)
            if args.device == "cuda" and is_cuda_error(exc):
                print_cuda_help()
            raise SystemExit(1) from None

        progress.remove_task(loading_task)
        overall_task = progress.add_task("전체 파일", total=len(jobs), detail=f"0 / {len(jobs)}개")
        failed = False
        processed_files = 0
        failed_files = 0
        for target, source in jobs.items():
            temporary: Path | None = None
            file_task = progress.add_task(
                escape(source.name), total=None, detail="음성 분석 중",
            )
            try:
                segments, info = model.transcribe(
                    str(source), language=args.language, beam_size=args.beam_size,
                    vad_filter=not args.no_vad, initial_prompt=args.initial_prompt,
                )
                duration = max(info.duration, 0.0)
                progress.update(
                    file_task, total=duration or 1.0,
                    detail=escape(f"{info.language} · 0 / {duration:.0f}초"),
                )
                # Iterate the lazy segments and publish only a complete transcript.
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=target.parent,
                    prefix=f".{target.stem}.", suffix=".tmp", delete=False,
                ) as output:
                    temporary = Path(output.name)
                    processed = 0.0
                    for segment in segments:
                        text = segment.text.strip()
                        if text:
                            output.write(text + "\n")
                        # Model timestamps may exceed the duration or move backwards.
                        processed = min(duration, max(processed, segment.end))
                        progress.update(
                            file_task, completed=processed,
                            detail=escape(f"{info.language} · {processed:.0f} / {duration:.0f}초"),
                        )
                if args.overwrite:
                    temporary.replace(target)
                else:
                    # Publish without overwriting an output created while we ran.
                    os.link(temporary, target)
                    temporary.unlink()
                temporary = None
                progress.update(
                    file_task, completed=duration or 1.0,
                    detail=escape(f"{info.language} · 완료"),
                )
            except Exception as exc:
                # Keep processing other files after decoder or inference errors.
                progress.update(file_task, detail="실패")
                print(f"전사 실패: {source.name}: {exc}", file=sys.stderr)
                if args.device == "cuda" and is_cuda_error(exc):
                    print_cuda_help()
                failed = True
                failed_files += 1
            finally:
                progress.stop_task(file_task)
                processed_files += 1
                progress.update(
                    overall_task, completed=processed_files,
                    detail=f"{processed_files} / {len(jobs)}개 · 실패 {failed_files}개",
                )
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        if failed:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
