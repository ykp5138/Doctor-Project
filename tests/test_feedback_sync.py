"""Cloud download regressions using mock HTTP responses and temporary logs."""
import concurrent.futures
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

from feedback_store import FeedbackRequest, append_feedback
from sync_feedback import sync_feedback


SOURCE = "https://feedback.example.test"


def cloud_entry(cloud_id, correct=True):
    return {
        "id": cloud_id,
        "record": {
            "timestamp": "2026-10-24T00:00:00.000000",
            "code": "SYNTHETIC",
            "description": "Test fixture",
            "evidence_phrase": "example \u2713",
            "word_indices": [0],
            "is_correct": correct,
            "transcript_base": "cloud-test",
            "concepts": {"symptoms": ["example"]},
        },
    }


def response(entries, has_more=False, after_id=0):
    result = Mock()
    result.is_redirect = False
    result.json.return_value = {
        "entries": entries,
        "next_after_id": entries[-1]["id"] if entries else after_id,
        "has_more": has_more,
    }
    return result


class FeedbackSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.path = self.directory / "feedback.jsonl"
        self.session = Mock()

    def sync(self, **kwargs):
        return sync_feedback(SOURCE, "synthetic-export-token", self.directory, self.session, **kwargs)

    def read_entries(self):
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_preserves_unrelated_records_and_uses_latest_paginated_choice(self):
        original = b'{"code":"LOCAL","is_correct":true}\n'
        self.path.write_bytes(original)
        self.session.get.side_effect = [
            response([cloud_entry(1, True), cloud_entry(2, False)], has_more=True),
            response([cloud_entry(3, True)]),
        ]
        self.assertEqual(self.sync(page_size=2), 3)
        self.assertTrue(self.path.read_bytes().startswith(original))
        entries = self.read_entries()
        self.assertEqual([entry["is_correct"] for entry in entries[1:]], [True])
        self.assertEqual([entry["_cloud_id"] for entry in entries[1:]], [3])
        self.assertTrue(all(entry["_cloud_source"] == SOURCE for entry in entries[1:]))
        calls = self.session.get.call_args_list
        self.assertEqual([call.kwargs["params"]["after_id"] for call in calls], [0, 2])
        self.assertEqual(calls[0].kwargs["headers"], {"Authorization": "Bearer synthetic-export-token"})
        self.assertFalse(calls[0].kwargs["allow_redirects"])

    def test_repeated_sync_is_incremental_and_does_not_duplicate(self):
        self.session.get.return_value = response([cloud_entry(1)])
        self.assertEqual(self.sync(), 1)
        first = self.path.read_bytes()
        self.session.get.return_value = response([], after_id=1)
        self.assertEqual(self.sync(), 0)
        self.assertEqual(self.path.read_bytes(), first)
        self.assertEqual(self.session.get.call_args.kwargs["params"]["after_id"], 1)

    def test_interrupted_previous_download_resumes_from_saved_record(self):
        first = {**cloud_entry(1)["record"], "_cloud_id": 1, "_cloud_source": SOURCE}
        self.path.write_text(json.dumps(first) + "\n", encoding="utf-8")
        self.session.get.return_value = response([cloud_entry(2, False), cloud_entry(3, True)])
        self.assertEqual(self.sync(), 2)
        self.assertEqual([entry["_cloud_id"] for entry in self.read_entries()], [3])

    def test_new_choice_replaces_previous_cloud_record_instead_of_canceling(self):
        self.session.get.return_value = response([cloud_entry(1, True)])
        self.assertEqual(self.sync(), 1)
        self.session.get.return_value = response([cloud_entry(2, False)])
        self.assertEqual(self.sync(), 1)
        self.session.get.return_value = response([cloud_entry(3, False)])
        self.assertEqual(self.sync(), 1)
        entries = self.read_entries()
        self.assertEqual(len(entries), 1)
        self.assertFalse(entries[0]["is_correct"])
        self.assertEqual(entries[0]["_cloud_id"], 3)
        self.session.get.return_value = response([], after_id=3)
        self.assertEqual(self.sync(), 0)
        self.assertEqual(self.session.get.call_args.kwargs["params"]["after_id"], 3)

    def test_stale_concurrent_page_cannot_revert_newer_choice(self):
        self.session.get.return_value = response([cloud_entry(3, False)])
        self.assertEqual(self.sync(), 1)
        from sync_feedback import _append_page
        self.assertEqual(_append_page(self.directory, SOURCE, [cloud_entry(2, True)]), 0)
        self.assertFalse(self.read_entries()[0]["is_correct"])

    def test_local_update_preserves_applied_cloud_cursor(self):
        self.session.get.return_value = response([cloud_entry(3, True)])
        self.assertEqual(self.sync(), 1)
        with patch.dict(os.environ, {"FEEDBACK_DIR": str(self.directory)}):
            append_feedback(FeedbackRequest(code="SYNTHETIC", transcript_base="cloud-test", is_correct=False))
        self.session.get.return_value = response([], after_id=3)
        self.assertEqual(self.sync(), 0)
        self.assertEqual(self.session.get.call_args.kwargs["params"]["after_id"], 3)
        self.assertFalse(self.read_entries()[0]["is_correct"])

    def test_cloud_export_with_no_new_rows_compacts_older_duplicate_events(self):
        old = [{**cloud_entry(index, bool(index % 2))["record"], "_cloud_id": index, "_cloud_source": SOURCE} for index in (1, 2, 3)]
        original = ''.join(json.dumps(entry) + '\n' for entry in old).encode()
        self.path.write_bytes(original)
        self.session.get.return_value = response([], after_id=3)
        self.assertEqual(self.sync(), 0)
        self.assertEqual(len(self.read_entries()), 1)
        self.assertEqual(self.read_entries()[0]["_cloud_id"], 3)
        self.assertEqual((self.directory / "feedback.before-latest-choice.jsonl").read_bytes(), original)

    def test_network_and_authentication_failures_never_truncate_local_log(self):
        original = b'{"code":"LOCAL","is_correct":false}\n'
        self.path.write_bytes(original)
        self.session.get.side_effect = requests.ConnectionError("synthetic network failure")
        with self.assertRaises(requests.ConnectionError):
            self.sync()
        self.assertEqual(self.path.read_bytes(), original)
        self.session.get.side_effect = None
        failed = response([])
        failed.raise_for_status.side_effect = requests.HTTPError("401 synthetic authentication failure")
        self.session.get.return_value = failed
        with self.assertRaises(requests.HTTPError):
            self.sync()
        self.assertEqual(self.path.read_bytes(), original)

    def test_invalid_or_stalled_pages_are_rejected_without_writing_records(self):
        original = b'{"code":"LOCAL","is_correct":false}\n'
        self.path.write_bytes(original)
        self.session.get.return_value = response([], has_more=True)
        with self.assertRaises(ValueError):
            self.sync()
        self.assertEqual(self.path.read_bytes(), original)

    def test_incomplete_last_line_is_preserved_and_separated(self):
        original = b'{"partial":'
        self.path.write_bytes(original)
        self.session.get.return_value = response([cloud_entry(1)])
        self.assertEqual(self.sync(), 1)
        self.assertTrue(self.path.read_bytes().startswith(original + b"\n"))
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8").splitlines()[-1])["_cloud_id"], 1)

    def test_simultaneous_downloads_and_local_clicks_keep_complete_distinct_records(self):
        def remote_get(*args, **kwargs):
            after_id = kwargs["params"]["after_id"]
            entries = [cloud_entry(index, bool(index % 2)) for index in range(after_id + 1, 11)]
            for entry in entries:
                entry["record"]["transcript_base"] = f'recording-{entry["id"]}'
            return response(entries, after_id=after_id)

        self.session.get.side_effect = remote_get
        with patch.dict(os.environ, {"FEEDBACK_DIR": str(self.directory)}):
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                tasks = [executor.submit(self.sync), executor.submit(self.sync)]
                tasks.append(executor.submit(append_feedback, FeedbackRequest(code="LOCAL", is_correct=True)))
                results = [task.result(timeout=10) for task in tasks]
        entries = self.read_entries()
        self.assertEqual(len(entries), 11)
        self.assertEqual(sorted(entry["_cloud_id"] for entry in entries if "_cloud_id" in entry), list(range(1, 11)))
        self.assertEqual(sum(result for result in results if type(result) is int), 10)

    def test_same_id_from_another_cloud_does_not_suppress_this_cloud(self):
        previous = {**cloud_entry(1)["record"], "_cloud_id": 1, "_cloud_source": "https://other.example.test"}
        self.path.write_text(json.dumps(previous) + "\n", encoding="utf-8")
        self.session.get.return_value = response([cloud_entry(1)])
        self.assertEqual(self.sync(), 1)
        self.assertEqual(len(self.read_entries()), 1)
        self.assertEqual(self.read_entries()[0]["_cloud_source"], SOURCE)


if __name__ == "__main__":
    unittest.main()
