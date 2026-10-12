"""Check literal download names without contacting external websites."""

import argparse
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sst_yon import download, transcribe


class DownloadTests(unittest.TestCase):
    def test_custom_output_template(self):
        with tempfile.TemporaryDirectory() as temporary:
            cookies = Path(temporary) / "cookies.txt"
            cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
            for name, expected in (
                ("1주차 강의", "1주차 강의.%(ext)s"),
                ("lecture.MP4", "lecture.%(ext)s"),
                ("lecture.mp4.mp4", "lecture.mp4.%(ext)s"),
                ("100% lecture", "100%% lecture.%(ext)s"),
                ("%(title)s", "%%(title)s.%(ext)s"),
                (None, "%(title)s [%(id)s].%(ext)s"),
            ):
                arguments = ["download", "URL", "--cookies", str(cookies)]
                if name is not None:
                    arguments.extend(["--name", name])
                with self.subTest(name=name), patch("sys.argv", arguments), \
                        patch("sst_yon.download.shutil.which", return_value="ffmpeg"), \
                        patch("sst_yon.download.yt_dlp.main") as invoke:
                    download.main()
                    options = invoke.call_args.args[0]
                    self.assertEqual(options[options.index("--output") + 1], expected)

    def test_invalid_filenames(self):
        for name in ("", ".mp4", "../lecture", "folder\\lecture", "CON", "NUL.mp4", "a:b", "a?b", "lecture."):
            with self.subTest(name=name), self.assertRaises(argparse.ArgumentTypeError):
                download.filename(name)

    def test_transcribe_language_alias(self):
        for flag in ("-l", "--language"):
            self.assertEqual(transcribe.build_parser().parse_args([flag, "ko"]).language, "ko")


if __name__ == "__main__":
    unittest.main()
