"""Offline replay integrity: never infer with a changed prompt or input."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evaluate_icd_accuracy import BASELINE_REF, make_words, score_selection
from icd_eval_cases import build_cases
from icd_selector import suggest_icd
from replay_icd_validation import RecordedResponse, RecordedRetriever, ReplayError, replay_row, replay_reports


class IcdReplayTests(unittest.TestCase):
    def setUp(self):
        self.case = build_cases()[0]
        self.catalog = {self.case["name"]: self.case}
        self.candidates = [{"code": "L70.0", "description": "Acne vulgaris", "matched_query": "acne vulgaris"}]
        trace = {}
        words = make_words(self.case["transcript"])
        raw = '{"picks":[{"code":"L70.0","span_id":"w0-5"}]}'
        generations = []
        def record_post(*args, **kwargs):
            generations.append({"request": deepcopy(kwargs["json"]), "response": {"response": raw}})
            return RecordedResponse(raw)
        selected = suggest_icd(self.case["concepts"], "", words, "",
                               retriever=RecordedRetriever(self.candidates), diagnostics=trace,
                               post=record_post)
        self.row = {"case": self.case["name"], "variant": "enhanced_cls", "repeat": 0,
                    "input_sha256": hashlib.sha256(json.dumps(self.case, sort_keys=True).encode()).hexdigest(),
                    "diagnostics": trace, "generations": generations,
                    "expected": self.case["expected_codes"], "allowed": self.case["allowed_codes"],
                    "error": None, "candidate_hits": 1, "candidate_total": 1, "candidate_ranks": [1],
                    **score_selection(selected, self.case["expected_codes"], self.case["allowed_codes"], words)}
        for name in ("requests.get", "requests.post", "icd10_retriever.get_retriever", "icd_embeddings.load_embedding_model"):
            blocker = patch(name, side_effect=AssertionError("Network/model loading is forbidden during replay"))
            blocker.start()
            self.addCleanup(blocker.stop)

    def test_acne_raw_reply_replays_without_network_or_model_loading(self):
        result = replay_row(self.row, self.catalog)
        self.assertTrue(result["passed"])
        self.assertEqual(result["codes"], ["L70.0"])
        self.assertTrue(result["replay"]["prompt_sha256_verified"])
        self.assertTrue(result["replay"]["full_request_verified"])
        self.assertFalse(result["replay"]["new_inference"])

    def test_changed_frozen_input_is_rejected(self):
        row = deepcopy(self.row)
        row["input_sha256"] = "0" * 64
        with self.assertRaisesRegex(ReplayError, "Frozen input changed"):
            replay_row(row, self.catalog)

    def test_changed_prompt_is_rejected_even_when_old_model_choice_would_be_correct(self):
        row = deepcopy(self.row)
        row["diagnostics"]["prompt_sha256"] = "0" * 64
        with self.assertRaisesRegex(ReplayError, "prompt differs"):
            replay_row(row, self.catalog)

    def test_raw_reply_can_be_read_from_recorded_generation(self):
        row = deepcopy(self.row)
        row["diagnostics"].pop("raw_response")
        self.assertTrue(replay_row(row, self.catalog)["passed"])

    def test_changed_options_schema_or_model_request_is_rejected(self):
        for field, changed in (("options", {"temperature": 0, "seed": 99, "num_ctx": 8192}),
                               ("format", "json"), ("model", "another-model"), ("stream", True)):
            row = deepcopy(self.row)
            row["generations"][0]["request"][field] = changed
            with self.assertRaisesRegex(ReplayError, "model request differs"):
                replay_row(row, self.catalog)

    def test_a_recorded_generation_requires_its_full_request(self):
        row = deepcopy(self.row)
        row["generations"][0].pop("request")
        with self.assertRaisesRegex(ReplayError, "full recorded request"):
            replay_row(row, self.catalog)

    def test_raw_only_input_explicitly_reports_prompt_only_verification(self):
        row = deepcopy(self.row)
        row["generations"] = []
        replay = replay_row(row, self.catalog)["replay"]
        self.assertTrue(replay["prompt_sha256_verified"])
        self.assertFalse(replay["full_request_verified"])

    def test_missing_recorded_reply_cannot_issue_an_unrecorded_request(self):
        row = deepcopy(self.row)
        row["diagnostics"].pop("raw_response")
        row["generations"] = []
        with self.assertRaisesRegex(ReplayError, "raw model reply"):
            replay_row(row, self.catalog)

    def test_baseline_rows_are_preserved_and_marked_without_reexecution(self):
        row = deepcopy(self.row)
        row["variant"] = "legacy"
        result = replay_row(row, self.catalog)
        replay = result.pop("replay")
        self.assertEqual(result, row)
        self.assertEqual(replay["mode"], "preserved_baseline")

    def test_report_keeps_original_inputs_and_mismatches_cannot_count_as_successes(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "input.json", Path(directory) / "output.json"
            bad = deepcopy(self.row)
            bad["diagnostics"]["prompt_sha256"] = "0" * 64
            content = json.dumps({"synthetic_cases": True, "retrieval_only": False,
                                  "baseline_commit": BASELINE_REF, "rows": [self.row, bad]})
            source.write_text(content, encoding="utf-8")
            report = replay_reports([source], output)
            self.assertEqual(source.read_text(encoding="utf-8"), content)
            self.assertEqual(report["summary"]["enhanced_cls"]["passed"], 1)
            self.assertEqual(report["summary"]["enhanced_cls"]["errors"], 1)
            self.assertEqual(report["summary"]["enhanced_cls"]["tp"], 1)
            self.assertTrue(output.exists())
            self.assertFalse(report["new_inference"])
            self.assertEqual(report["groups"][0]["rows"], 2)
            self.assertIn("icd_evidence.py", report["replay_metadata"]["source_sha256"])
            with self.assertRaisesRegex(ReplayError, "must not overwrite"):
                replay_reports([source], source)


if __name__ == "__main__":
    unittest.main()
