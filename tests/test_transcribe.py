"""Exercise progress rendering and atomic output without loading a real model."""

from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from rich.console import Console
from rich.progress import Progress

from sst_yon import transcribe


class TranscribeProgressTests(unittest.TestCase):
    def run_transcribe(self, root, model):
        display = StringIO()
        progress = Progress(
            console=Console(file=display, width=140), auto_refresh=False,
        )
        fake_whisper = SimpleNamespace(WhisperModel=Mock(return_value=model))
        arguments = ["transcribe", str(root / "audio"), "-o", str(root / "txt"), "--device", "cpu"]
        with patch.dict("sys.modules", {"faster_whisper": fake_whisper}), \
                patch("sys.argv", arguments), patch("sst_yon.transcribe.Progress", return_value=progress), \
                redirect_stderr(StringIO()):
            transcribe.main()
        return progress, display.getvalue()

    def test_progress_is_bounded_and_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "audio").mkdir()
            (root / "audio" / "lecture [index].mp3").write_bytes(b"audio")
            model = Mock()
            model.transcribe.return_value = (
                iter([SimpleNamespace(text=" 첫 문장 ", end=20),
                      SimpleNamespace(text="둘째 문장", end=200),
                      SimpleNamespace(text=" ", end=5)]),
                SimpleNamespace(language="ko", duration=100),
            )
            progress, rendered = self.run_transcribe(root, model)
            self.assertEqual((root / "txt" / "lecture [index].txt").read_text(encoding="utf-8"), "첫 문장\n둘째 문장\n")
            self.assertEqual([task.completed for task in progress.tasks], [1, 100])
            self.assertIn("완료", progress.tasks[1].fields["detail"])
            self.assertIn("lecture [index].mp3", rendered)
            self.assertFalse(list((root / "txt").glob("*.tmp")))

    def test_failed_file_cleans_partial_output_and_continues(self):
        def broken_segments():
            yield SimpleNamespace(text="partial", end=10)
            raise RuntimeError("decode failed")

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "audio").mkdir()
            for name in ("first", "second"):
                (root / "audio" / f"{name}.mp3").write_bytes(b"audio")
            info = SimpleNamespace(language="ko", duration=100)
            model = Mock()
            model.transcribe.side_effect = [
                (broken_segments(), info),
                (iter([SimpleNamespace(text="complete", end=100)]), info),
            ]
            with self.assertRaises(SystemExit) as failure:
                self.run_transcribe(root, model)
            self.assertEqual(failure.exception.code, 1)
            self.assertEqual(model.transcribe.call_count, 2)
            self.assertFalse((root / "txt" / "first.txt").exists())
            self.assertEqual((root / "txt" / "second.txt").read_text(encoding="utf-8"), "complete\n")
            self.assertFalse(list((root / "txt").glob("*.tmp")))


if __name__ == "__main__":
    unittest.main()
