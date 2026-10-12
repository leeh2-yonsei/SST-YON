"""Run download, MP3 conversion, and local transcription as one CLI command."""

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

from sst_yon.download import DEFAULT_COOKIE_FILE, add_name_argument, validate_name_options
from sst_yon.transcribe import add_transcription_arguments, validate_options


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="URL 다운로드 → MP3 변환 → 로컬 전사를 한 번에 실행합니다.")
    parser.add_argument("urls", nargs="+", help="다운로드할 URL (여러 개 지정 가능)")
    parser.add_argument(
        "-o", "--output-root", type=Path, default=Path("asset"),
        help="mp4, mp3, txt 폴더를 생성할 위치 (기본값: asset)",
    )
    cookies = parser.add_mutually_exclusive_group()
    cookies.add_argument(
        "--cookies", type=Path, metavar="FILE",
        help=f"쿠키 파일 (기본값: {DEFAULT_COOKIE_FILE.as_posix()})",
    )
    cookies.add_argument("--cookies-from-browser", metavar="BROWSER[:PROFILE]")
    parser.add_argument("--playlist", action="store_true", help="재생목록 전체 처리")
    add_name_argument(parser)
    parser.add_argument("-q", "--quality", type=int, choices=range(10), default=2, help="MP3 VBR 품질 (기본값: 2)")
    add_transcription_arguments(parser)
    return parser


def run_stage(label: str, module: str, arguments: list[str]) -> None:
    print(f"\n{label}", flush=True)
    # Use the active uv environment; no shell or additional uv sync is involved.
    subprocess.run([sys.executable, "-m", module, *arguments], check=True)


def read_downloads(manifest: Path) -> list[Path]:
    if not manifest.is_file():
        raise ValueError("다운로드한 영상 경로를 받지 못했습니다.")
    videos = list(dict.fromkeys(
        Path(line).resolve()
        for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()
    ))
    if not videos:
        raise ValueError("다운로드한 영상이 없습니다.")
    for video in videos:
        if not video.is_file():
            raise ValueError(f"다운로드 결과 파일을 찾을 수 없습니다: {video}")
        if video.suffix.lower() != ".mp4":
            raise ValueError(f"다운로드 결과가 MP4가 아닙니다: {video}")
    return videos


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    validate_options(parser, args)
    validate_name_options(parser, args)
    root = args.output_root.resolve()
    video_dir, audio_dir, text_dir = root / "mp4", root / "mp3", root / "txt"

    try:
        with tempfile.TemporaryDirectory(prefix="sst-yon-pipeline-") as temporary:
            manifest = Path(temporary) / "downloads.txt"
            download_args = ["--output-dir", str(video_dir), "--manifest", str(manifest)]
            if args.name is not None:
                download_args.extend(["--name", args.name])
            if args.cookies is not None:
                download_args.extend(["--cookies", str(args.cookies.resolve())])
            elif args.cookies_from_browser is not None:
                download_args.extend(["--cookies-from-browser", args.cookies_from_browser])
            if args.playlist:
                download_args.append("--playlist")
            run_stage("[1/3] 영상 다운로드", "sst_yon.download", [*download_args, "--", *args.urls])
            videos = read_downloads(manifest)

            convert_args = ["--output-dir", str(audio_dir), "--quality", str(args.quality)]
            if args.overwrite:
                convert_args.append("--overwrite")
            run_stage("[2/3] MP3 변환", "sst_yon.convert", [*convert_args, "--", *(str(path) for path in videos)])
            audio_files = [audio_dir / f"{video.stem}.mp3" for video in videos]
            for audio in audio_files:
                if not audio.is_file() or audio.stat().st_size == 0:
                    raise ValueError(f"MP3 변환 결과를 찾을 수 없거나 파일이 비어 있습니다: {audio}")

            transcribe_args = [
                "--output-dir", str(text_dir), "--model", args.model,
                "--device", args.device, "--beam-size", str(args.beam_size),
                "--model-dir", str(args.model_dir.resolve()),
            ]
            for flag, value in (
                ("--compute-type", args.compute_type), ("--language", args.language),
                ("--initial-prompt", args.initial_prompt),
            ):
                if value is not None:
                    transcribe_args.extend([flag, value])
            for flag, enabled in (
                ("--no-vad", args.no_vad), ("--local-files-only", args.local_files_only),
                ("--overwrite", args.overwrite),
            ):
                if enabled:
                    transcribe_args.append(flag)
            run_stage(
                "[3/3] 로컬 음성 전사", "sst_yon.transcribe",
                [*transcribe_args, "--", *(str(path) for path in audio_files)],
            )
            for audio in audio_files:
                target = text_dir / f"{audio.stem}.txt"
                if not target.is_file():
                    raise ValueError(f"전사 결과 파일을 찾을 수 없습니다: {target}")
                print(f"최종 결과: {target}", flush=True)
    except subprocess.CalledProcessError as exc:
        print("단계 실행에 실패하여 파이프라인을 중단했습니다. 위 오류를 확인하세요.", file=sys.stderr)
        raise SystemExit(exc.returncode if exc.returncode > 0 else 1) from None
    except (OSError, ValueError) as exc:
        print(f"파이프라인 실패: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
