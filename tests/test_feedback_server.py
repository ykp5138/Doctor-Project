"""Central feedback tests use temporary files, without network listeners."""
import asyncio
import json
import multiprocessing
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import feedback_server
from feedback_store import FeedbackRequest, append_feedback, merge_feedback_records


def _append_in_process(directory, writer):
    os.environ["FEEDBACK_DIR"] = directory
    for index in range(12):
        append_feedback(FeedbackRequest(
            code=f"TEST-{writer}-{index}",
            description="Synthetic concurrency fixture",
            evidence_phrase="example \u2713 " * 10000,
            is_correct=bool(index % 2),
        ))


class FeedbackServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name) / "feedback"
        env = patch.dict(os.environ, {
            "FEEDBACK_DIR": str(self.directory),
            "FEEDBACK_API_TOKEN": "synthetic-test-token",
        })
        env.start()
        self.addCleanup(env.stop)
        self.client = TestClient(feedback_server.app)
        self.addCleanup(self.client.close)
        self.headers = {"Authorization": "Bearer synthetic-test-token"}
        self.payload = {
            "code": "TEST",
            "description": "Synthetic fixture",
            "evidence_phrase": "Example",
            "word_indices": [0],
            "transcript_base": "synthetic-test",
            "concepts": {"symptoms": ["example"]},
        }

    def send(self, correct, headers=None):
        return self.client.post(
            "/feedback",
            json={**self.payload, "is_correct": correct},
            headers=self.headers if headers is None else headers,
        )

    def test_last_choice_wins_and_repeated_cross_stays_incorrect(self):
        with self.client:
            for correct in (True, False, False):
                response = self.send(correct)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertTrue(response.json()["ok"])
                # Acknowledgement follows the completed canonical-file update.
                entries = self.read_entries()
                self.assertEqual(len(entries), 1)
                self.assertEqual(entries[-1]["timestamp"], response.json()["logged_at"])
        self.assertEqual([entry["is_correct"] for entry in entries], [False])
        history = [json.loads(line) for line in (self.directory / "feedback_history.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([entry["is_correct"] for entry in history], [True, False, False])
        for entry in entries:
            for key, value in self.payload.items():
                self.assertEqual(entry[key], value)

    def test_same_code_in_different_recordings_is_independent(self):
        self.assertEqual(self.send(True).status_code, 200)
        self.payload["transcript_base"] = "another-recording"
        self.assertEqual(self.send(False).status_code, 200)
        self.assertEqual([entry["is_correct"] for entry in self.read_entries()], [True, False])

    def test_existing_duplicates_compact_without_losing_original_or_malformed_bytes(self):
        self.directory.mkdir()
        first = {**self.payload, "is_correct": True, "timestamp": "first"}
        last = {**self.payload, "is_correct": False, "timestamp": "last"}
        original = json.dumps(first).encode() + b'\n{invalid preserved\n' + json.dumps(last).encode() + b'\n'
        path = self.directory / "feedback.jsonl"
        path.write_bytes(original)
        self.assertEqual(merge_feedback_records(self.directory, []), 0)
        updated = path.read_bytes()
        self.assertIn(b'{invalid preserved\n', updated)
        self.assertEqual(updated.count(b'"code": "TEST"'), 1)
        self.assertEqual((self.directory / "feedback.before-latest-choice.jsonl").read_bytes(), original)

    def test_brief_reader_lock_is_retried_before_acknowledging_the_choice(self):
        self.assertEqual(self.send(True).status_code, 200)
        real_replace = os.replace
        attempts = []

        def briefly_locked(*args, **kwargs):
            attempts.append(True)
            if len(attempts) == 1:
                raise PermissionError("Synthetic brief reader lock")
            return real_replace(*args, **kwargs)

        with patch("feedback_store.os.replace", side_effect=briefly_locked):
            response = self.send(False)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(attempts), 2)
        self.assertEqual([entry["is_correct"] for entry in self.read_entries()], [False])
        self.assertFalse(list(self.directory.glob(".feedback-*.tmp")))

    def test_failed_atomic_replacement_preserves_the_previous_current_file(self):
        self.assertEqual(self.send(True).status_code, 200)
        original = (self.directory / "feedback.jsonl").read_bytes()
        with patch("feedback_store.os.replace", side_effect=PermissionError("Synthetic reader lock")):
            response = self.send(False)
        self.assertEqual(response.status_code, 500)
        self.assertEqual((self.directory / "feedback.jsonl").read_bytes(), original)
        self.assertEqual((self.directory / "feedback.before-latest-choice.jsonl").read_bytes(), original)
        self.assertFalse(list(self.directory.glob(".feedback-*.tmp")))

    def test_existing_empty_log_accepts_first_click(self):
        self.directory.mkdir()
        (self.directory / "feedback.jsonl").write_text("", encoding="utf-8")
        response = self.send(False)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.read_entries()), 1)

    def test_missing_or_wrong_token_never_creates_feedback_files(self):
        for headers in ({}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic synthetic-test-token"}):
            response = self.send(True, headers=headers)
            self.assertEqual(response.status_code, 401)
        self.assertFalse(self.directory.exists())

    def test_unconfigured_receiver_refuses_startup_and_writes(self):
        async def start_receiver():
            async with feedback_server._lifespan(feedback_server.app):
                pass

        with patch.dict(os.environ, {"FEEDBACK_API_TOKEN": ""}):
            with self.assertRaisesRegex(RuntimeError, "Set FEEDBACK_API_TOKEN"):
                asyncio.run(start_receiver())
            response = self.send(True)
            self.assertEqual(response.status_code, 503)
        self.assertFalse(self.directory.exists())

    def test_write_failure_is_not_acknowledged_as_saved(self):
        with patch.object(feedback_server, "append_feedback", side_effect=PermissionError("Synthetic failure")):
            response = self.send(True)
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("ok", response.json())
        self.assertFalse(self.directory.exists())

    def test_receiver_exposes_no_transcription_or_feedback_download(self):
        self.assertEqual(self.client.get("/health").json(), {"ok": True})
        self.assertEqual(self.client.post("/transcribe", headers=self.headers).status_code, 404)
        self.assertEqual(self.client.get("/feedback", headers=self.headers).status_code, 405)
        self.assertEqual(self.client.get("/docs").status_code, 404)

    def test_concurrent_processes_keep_whole_json_lines(self):
        context = multiprocessing.get_context("spawn")
        processes = [context.Process(target=_append_in_process, args=(str(self.directory), writer)) for writer in range(2)]
        for process in processes:
            process.start()
        try:
            for process in processes:
                process.join(timeout=30)
                self.assertEqual(process.exitcode, 0)
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=5)
        entries = self.read_entries()
        self.assertEqual(len(entries), 24)
        self.assertEqual(len({entry["code"] for entry in entries}), 24)
        self.assertTrue(all(entry["evidence_phrase"] == "example \u2713 " * 10000 for entry in entries))

    def read_entries(self):
        return [json.loads(line) for line in (self.directory / "feedback.jsonl").read_text(encoding="utf-8").splitlines()]


if __name__ == "__main__":
    unittest.main()
