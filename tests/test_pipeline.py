"""Check pipeline file selection and failure boundaries without network access."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from sst_yon import pipeline


class PipelineTests(unittest.TestCase):
    def test_only_download_manifest_files_are_forwarded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            video = root / "mp4" / "1주차 강의.mp4"
            unrelated = root / "mp4" / "other.mp4"
            video.parent.mkdir()
            video.write_bytes(b"video")
            unrelated.write_bytes(b"unrelated")
            audio = root / "mp3" / "1주차 강의.mp3"
            transcript = root / "txt" / "1주차 강의.txt"
            stages = []

            def stage(label, module, arguments):
                stages.append((module, arguments))
                if module == "sst_yon.download":
                    self.assertEqual(arguments[arguments.index("--name") + 1], "1주차 강의")
                    manifest = Path(arguments[arguments.index("--manifest") + 1])
                    # Include a duplicate to check URL aliases do not repeat work.
                    manifest.write_text(f"{video}\n{video}\n", encoding="utf-8")
                elif module == "sst_yon.convert":
                    self.assertEqual(arguments[arguments.index("--") + 1:], [str(video)])
                    audio.parent.mkdir()
                    audio.write_bytes(b"audio")
                else:
                    self.assertEqual(arguments[arguments.index("--") + 1:], [str(audio)])
                    self.assertIn("--local-files-only", arguments)
                    self.assertIn("--overwrite", arguments)
                    self.assertEqual(arguments[arguments.index("--language") + 1], "ko")
                    transcript.parent.mkdir()
                    transcript.write_text("전사 결과", encoding="utf-8")

            with patch("sys.argv", [
                "pipeline", "https://example.com/video", "-o", str(root),
                "-n", "1주차 강의", "-l", "ko", "--local-files-only", "--overwrite",
            ]), patch("sst_yon.pipeline.run_stage", side_effect=stage), redirect_stdout(StringIO()):
                pipeline.main()
            self.assertEqual([module for module, _ in stages], [
                "sst_yon.download", "sst_yon.convert", "sst_yon.transcribe",
            ])
            self.assertTrue(transcript.is_file())
            self.assertFalse((root / "mp3" / "other.mp3").exists())

    def test_failed_stage_does_not_start_later_stages(self):
        for failed_module in ("sst_yon.download", "sst_yon.convert", "sst_yon.transcribe"):
            with self.subTest(failed_module=failed_module), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                video = root / "lecture.mp4"
                video.write_bytes(b"video")
                seen = []

                def stage(label, module, arguments):
                    seen.append(module)
                    if module == failed_module:
                        raise subprocess.CalledProcessError(7, module)
                    if module == "sst_yon.download":
                        manifest = Path(arguments[arguments.index("--manifest") + 1])
                        manifest.write_text(str(video), encoding="utf-8")
                    elif module == "sst_yon.convert":
                        audio = root / "mp3" / "lecture.mp3"
                        audio.parent.mkdir()
                        audio.write_bytes(b"audio")

                with patch("sys.argv", ["pipeline", "https://example.com/video", "-o", str(root)]), \
                        patch("sst_yon.pipeline.run_stage", side_effect=stage), \
                        redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                    with self.assertRaises(SystemExit) as failure:
                        pipeline.main()
                self.assertEqual(failure.exception.code, 7)
                self.assertEqual(seen[-1], failed_module)
                self.assertFalse((root / "txt" / "lecture.txt").exists())

    def test_invalid_model_options_fail_before_downloading(self):
        with patch("sys.argv", ["pipeline", "https://example.com/video", "--beam-size", "0"]), \
                patch("sst_yon.pipeline.run_stage") as stage, redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as failure:
                pipeline.main()
        self.assertEqual(failure.exception.code, 2)
        stage.assert_not_called()

    def test_invalid_name_options_fail_before_downloading(self):
        for options in (
            ["URL1", "URL2", "-n", "lecture"],
            ["URL", "--playlist", "-n", "lecture"],
            ["URL", "-n", "../lecture"],
        ):
            with self.subTest(options=options), patch("sys.argv", ["pipeline", *options]), \
                    patch("sst_yon.pipeline.run_stage") as stage, redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as failure:
                    pipeline.main()
                self.assertEqual(failure.exception.code, 2)
                stage.assert_not_called()


if __name__ == "__main__":
    unittest.main()
