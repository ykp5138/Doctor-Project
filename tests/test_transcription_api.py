"""Upload/feedback regressions without models, API calls, or real feedback writes."""
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main


class TranscriptionApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base_dir = Path(self.temp.name)
        self.patch_attribute(main, "BASE_DIR", str(self.base_dir))
        self.pipeline = self.patch_attribute(main.subprocess, "run")
        self.downstream = self.patch_attribute(main, "_run_downstream")
        self.downstream.return_value = ([{"text": "Example", "start": 0}], "Test summary", {})
        self.client = TestClient(main.app)

    def patch_attribute(self, target, name, *args):
        patcher = patch.object(target, name, *args)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def upload(self):
        return self.client.post(
            "/transcribe",
            files={"file": ("example.wav", b"test audio", "audio/wav")},
            data={"keywords": "example", "patient_name": "Test Patient"},
        )

    def test_upload_with_windows_output_encoding_and_missing_audio_folder(self):
        output = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        self.addCleanup(output.close)
        with patch("sys.stdout", output):
            response = self.upload()

        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["summary"], "Test summary")
        self.assertEqual(result["concepts"], {})
        self.assertEqual(result["meta"]["filename"], "example.wav")
        self.assertEqual(result["meta"]["bytes"], 10)
        self.assertEqual(len(list((self.base_dir / "audio").glob("*.wav"))), 1)
        self.assertEqual(self.pipeline.call_count, 2)
        for call in self.pipeline.call_args_list:
            self.assertEqual(call.kwargs["env"]["PYTHONUTF8"], "1")
            self.assertEqual(call.kwargs["env"]["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(self.downstream.call_args.kwargs["patient_name"], "Test Patient")

    def test_pipeline_failure_returns_an_http_error(self):
        self.pipeline.side_effect = subprocess.CalledProcessError(1, ["transcriber"])
        response = self.upload()
        self.assertEqual(response.status_code, 500)
        self.assertIn("Pipeline step failed", response.json()["detail"])
        self.downstream.assert_not_called()

    def test_missing_upload_returns_validation_error(self):
        response = self.client.post("/transcribe")
        self.assertEqual(response.status_code, 422)
        self.pipeline.assert_not_called()

    def test_feedback_keeps_the_last_choice_with_transcript_context(self):
        feedback_dir = self.base_dir / "feedback"
        payload = {
            "code": "TEST",
            "description": "Synthetic regression fixture",
            "evidence_phrase": "Example",
            "word_indices": [0],
            "transcript_base": "synthetic-test",
            "concepts": {"symptoms": ["example"]},
        }
        with patch.dict(os.environ, {"FEEDBACK_DIR": str(feedback_dir)}):
            for correct in (True, False, False):
                response = self.client.post("/feedback", json={**payload, "is_correct": correct})
                self.assertEqual(response.status_code, 200, response.text)

        entries = [json.loads(line) for line in (feedback_dir / "feedback.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([entry["is_correct"] for entry in entries], [False])
        for entry in entries:
            self.assertTrue(entry["timestamp"])
            for key, value in payload.items():
                self.assertEqual(entry[key], value)


if __name__ == "__main__":
    unittest.main()
