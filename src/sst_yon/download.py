"""Download videos using yt-dlp with a default cookie file or explicit cookies."""

import argparse
import ntpath
from pathlib import Path
import shutil

import yt_dlp


DEFAULT_COOKIE_FILE = Path("asset/cookie/cookies.txt")


def filename(value: str) -> str:
    """Accept a literal filename, optionally including the final MP4 extension."""
    name = value[:-4] if value.lower().endswith(".mp4") else value
    if not name or name in {".", ".."} or ":" in name or ntpath.isreserved(name):
        raise argparse.ArgumentTypeError("유효한 파일 이름을 지정하세요 (경로, 예약 이름, 금지 문자 제외).")
    if "/" in name or "\\" in name:
        raise argparse.ArgumentTypeError("폴더 경로 대신 파일 이름만 지정하세요. 저장 위치는 -o로 지정합니다.")
    return value


def add_name_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-n", "--name", type=filename, metavar="NAME",
        help="저장할 파일 이름 (확장자 생략 가능, 단일 URL 및 --playlist 미사용 시에만 허용)",
    )


def validate_name_options(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.name is not None and (len(args.urls) != 1 or args.playlist):
        parser.error("--name은 단일 URL에서만 사용할 수 있으며 --playlist와 함께 사용할 수 없습니다.")


def main() -> None:
    parser = argparse.ArgumentParser(description="쿠키를 사용해 링크의 영상을 MP4로 다운로드합니다.")
    parser.add_argument("urls", nargs="+", help="다운로드할 URL (여러 개 지정 가능)")
    cookies = parser.add_mutually_exclusive_group()
    cookies.add_argument(
        "--cookies", type=Path, metavar="FILE",
        help=f"Netscape 형식 쿠키 파일 (쿠키 옵션 생략 시: {DEFAULT_COOKIE_FILE.as_posix()})",
    )
    cookies.add_argument(
        "--cookies-from-browser", metavar="BROWSER[:PROFILE]",
        help="yt-dlp 브라우저 지정값 (예: firefox, chrome:Default, edge)",
    )
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("asset/mp4"))
    parser.add_argument("--playlist", action="store_true", help="재생목록 전체 다운로드")
    parser.add_argument("--manifest", type=Path, help="완성된 영상 경로를 UTF-8 목록 파일에 추가 기록")
    add_name_argument(parser)
    args = parser.parse_args()
    validate_name_options(parser, args)

    if args.cookies is None and args.cookies_from_browser is None:
        args.cookies = DEFAULT_COOKIE_FILE

    if shutil.which("ffmpeg") is None:
        parser.error("PATH에서 ffmpeg를 찾을 수 없습니다.")
    if args.cookies is not None and not args.cookies.is_file():
        parser.error(
            f"쿠키 파일을 찾을 수 없습니다: {args.cookies}. "
            "파일을 준비하거나 --cookies 또는 --cookies-from-browser를 지정하세요."
        )

    # Delegate browser/profile parsing and error handling to yt-dlp itself.
    name = args.name
    if name is not None and name.lower().endswith(".mp4"):
        name = name[:-4]
    options = [
        "--ignore-config",
        "--yes-playlist" if args.playlist else "--no-playlist",
        "--format", "bv*+ba/b",
        "--merge-output-format", "mp4",
        "--remux-video", "mp4",
        "--no-overwrites",
        "--paths", str(args.output_dir.resolve()),
        "--output", (
            name.replace("%", "%%") + ".%(ext)s"
            if name is not None else "%(title)s [%(id)s].%(ext)s"
        ),
    ]
    if args.cookies is not None:
        options.extend(["--cookies", str(args.cookies.resolve())])
    else:
        options.extend(["--cookies-from-browser", args.cookies_from_browser])
    if args.manifest is not None:
        # after_move includes merging/remuxing and reports the final file path.
        options.extend([
            "--print-to-file", "after_move:%(filepath)s",
            str(args.manifest.resolve()).replace("%", "%%"),
        ])
    yt_dlp.main([*options, "--", *args.urls])


if __name__ == "__main__":
    main()
