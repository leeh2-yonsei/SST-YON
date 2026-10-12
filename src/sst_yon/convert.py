"""Convert local media files to MP3 using the installed ffmpeg."""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="로컬 파일 또는 폴더의 MP4를 MP3로 변환합니다.")
    parser.add_argument(
        "inputs", nargs="*", type=Path,
        help="미디어 파일 또는 MP4 폴더 (기본값: asset/mp4, 하위 폴더 제외)",
    )
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("asset/mp3"))
    parser.add_argument(
        "-q", "--quality", type=int, choices=range(10), default=2,
        help="MP3 VBR 품질: 0(최고)~9(최저), 기본값 2",
    )
    parser.add_argument("--overwrite", action="store_true", help="기존 MP3 덮어쓰기")
    args = parser.parse_args()

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        parser.error("PATH에서 ffmpeg를 찾을 수 없습니다.")

    sources: list[Path] = []
    for source in args.inputs or [Path("asset/mp4")]:
        if source.is_dir():
            sources.extend(sorted(
                path.resolve() for path in source.iterdir()
                if path.is_file() and path.suffix.lower() == ".mp4"
            ))
        elif source.is_file():
            sources.append(source.resolve())
        else:
            parser.error(f"입력 파일 또는 폴더를 찾을 수 없습니다: {source}")
    sources = list(dict.fromkeys(sources))
    if not sources:
        parser.error("변환할 MP4 파일이 없습니다.")

    output_dir = args.output_dir.resolve()
    jobs: dict[Path, Path] = {}
    for source in sources:
        target = output_dir / f"{source.stem}.mp3"
        if target == source:
            parser.error(f"입력과 출력 경로가 같습니다: {source}")
        if target in jobs:
            parser.error(f"출력 이름이 겹칩니다. 파일별로 실행하거나 출력 폴더를 나누세요: {target.name}")
        if target.exists() and not args.overwrite:
            parser.error(f"출력 파일이 이미 있습니다 (--overwrite로 덮어쓰기): {target}")
        jobs[target] = source

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        parser.error(f"출력 폴더를 만들 수 없습니다: {exc}")

    failed = False
    for target, source in jobs.items():
        print(f"변환: {source.name} -> {target}", flush=True)
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin",
            "-y" if args.overwrite else "-n",
            "-i", str(source), "-map", "0:a:0", "-vn",
            "-c:a", "libmp3lame", "-q:a", str(args.quality), str(target),
        ]
        try:
            subprocess.run(command, check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"변환 실패: {source.name}: {exc}", file=sys.stderr)
            failed = True
        else:
            print(f"완료: {target}", flush=True)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
