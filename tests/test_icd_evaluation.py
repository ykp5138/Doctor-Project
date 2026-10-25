"""Evaluation integrity checks without loading models or contacting Ollama."""
import contextlib
import io
import unittest
from unittest.mock import patch

from evaluate_icd_accuracy import grounded_evidence, score_selection, selection_error, summarize, paired_comparisons, main


class IcdEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.words = [{"text": "Acne"}, {"text": "vulgaris."}]
        self.pick = {"code": "L70.0", "evidence": [{"phrase": "Acne vulgaris", "word_indices": [0, 1]}]}

    def test_selector_failure_cannot_pass_an_expected_empty_case(self):
        error = selection_error("enhanced_cls", [{"code": "L70.0"}], [], "",
                                {"error": "Model reply did not contain a picks array"})
        result = score_selection([], [], [], self.words, error)
        self.assertFalse(result["passed"])
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (0, 0, 0))

    def test_transport_and_baseline_swallowed_errors_are_detected(self):
        for generations, logs in (([{"error": "Timeout"}], ""),
                                   ([{"http_status": 503, "response": {}}], ""),
                                   ([], "[icd-rag] Ollama error: connection refused")):
            self.assertIsNotNone(selection_error("legacy", [{"code": "L70.0"}], generations, logs, {}))

    def test_valid_empty_baseline_reply_is_not_a_parsing_failure(self):
        generations = [{"response": {"response": "No supported codes: []"}}]
        self.assertIsNone(selection_error("legacy", [{"code": "L70.0"}], generations, "", {}))
        self.assertTrue(score_selection([], [], [], self.words)["passed"])

    def test_malformed_baseline_generation_is_an_error_even_for_empty_expected_codes(self):
        for raw in ("I cannot produce JSON", '{"picks": []}', '["L70.0"]'):
            self.assertIsNotNone(selection_error("legacy", [{"code": "L70.0"}],
                                                [{"response": {"response": raw}}], "", {}))

    def test_legitimate_empty_retrieval_is_distinct_from_no_generation_with_candidates(self):
        self.assertIsNone(selection_error("legacy", [], [], "", {}))
        self.assertIsNone(selection_error("enhanced_cls", [{"code": "L70"}], [], "",
                                          {"error": "No complete candidate codes in the requested range"}))
        self.assertIsNotNone(selection_error("legacy", [{"code": "L70.0"}], [], "", {}))
        self.assertFalse(score_selection([], ["L70.0"], [], self.words)["passed"])

    def test_selected_codes_require_nonempty_grounded_evidence(self):
        for evidence in ([], [{"phrase": "Acne vulgaris", "word_indices": []}],
                         [{"phrase": "Severe acne", "word_indices": [0, 1]}]):
            self.assertFalse(score_selection([{"code": "L70.0", "evidence": evidence}],
                                              ["L70.0"], [], self.words)["passed"])
        self.assertTrue(score_selection([self.pick], ["L70.0"], [], self.words)["passed"])

    def test_grounding_cannot_join_nonconsecutive_words_or_invalid_indices(self):
        transcript = [{"text": "Acne"}, {"text": "not"}, {"text": "vulgaris"}]
        for indices in ([0, 2], [True, 2], [0, "1"], [1, 0], [0, 0], [0, 3]):
            self.assertFalse(grounded_evidence({"phrase": "Acne vulgaris", "word_indices": indices}, transcript))

    def test_allowed_optional_codes_are_visible_and_other_extras_count_as_false_positives(self):
        optional = {**self.pick, "code": "Z84.0"}
        unexpected = {**self.pick, "code": "L70.9"}
        result = score_selection([self.pick, optional, unexpected], ["L70.0"], ["Z84.0"], self.words)
        self.assertEqual((result["tp"], result["fp"], result["fn"]), (1, 1, 0))
        self.assertEqual(result["optional_codes"], ["Z84.0"])
        self.assertFalse(result["passed"])
        row = {**result, "variant": "example", "candidate_hits": 1, "candidate_total": 1,
               "candidate_ranks": [1], "error": None}
        report = summarize([row])
        self.assertEqual(report["summary"]["example"]["optional_selected"], 1)
        self.assertEqual(report["summary"]["example"]["precision"], .5)
        self.assertIsNone(summarize([row], retrieval_only=True)["summary"]["example"]["precision"])

    @staticmethod
    def evaluation_row(case, variant, passed, *, input_sha256="same-frozen-input", repeat=0):
        return {"case": case, "variant": variant, "passed": passed, "input_sha256": input_sha256,
                "repeat": repeat, "codes": ["L70.0"] if passed else [], "error": None,
                "tp": int(passed), "fp": 0, "fn": int(not passed), "grounded": True,
                "candidate_hits": 1, "candidate_total": 1, "candidate_ranks": [1]}

    def test_paired_comparisons_expose_regressions_despite_aggregate_improvement(self):
        rows = []
        for name, old, new in (("regressed", True, False), ("improved_one", False, True),
                               ("improved_two", False, True), ("kept", True, True), ("still_missed", False, False)):
            rows += [self.evaluation_row(name, "legacy", old), self.evaluation_row(name, "enhanced_cls", new)]
        report = summarize(rows)
        self.assertGreater(report["summary"]["enhanced_cls"]["passed"], report["summary"]["legacy"]["passed"])
        paired = report["paired_comparisons"]["enhanced_cls"]
        self.assertEqual((paired["paired_runs"], paired["regression_count"], paired["improvement_count"]), (5, 1, 2))
        self.assertEqual((paired["both_passed"], paired["both_failed"]), (1, 1))
        self.assertEqual([item["case"] for item in paired["regressions"]], ["regressed"])

    def test_pairing_requires_matching_input_hash_and_repeat(self):
        rows = [self.evaluation_row("case", "legacy", True),
                self.evaluation_row("case", "enhanced_cls", False, input_sha256="changed-input"),
                self.evaluation_row("case", "enhanced_cls", False, repeat=1)]
        paired = paired_comparisons(rows)["enhanced_cls"]
        self.assertEqual(paired["paired_runs"], 0)
        self.assertEqual(paired["regression_count"], 0)
        self.assertEqual((paired["baseline_only_runs"], paired["proposed_only_runs"]), (1, 2))
        with self.assertRaisesRegex(ValueError, "Duplicate paired"):
            paired_comparisons([rows[0], rows[0]])

    def test_cli_can_fail_on_paired_regression_without_model_calls(self):
        rows = [self.evaluation_row("case", "legacy", True), self.evaluation_row("case", "enhanced_cls", False)]
        report = summarize(rows)
        with patch("sys.argv", ["evaluate_icd_accuracy.py", "--fail-on-regression", "enhanced_cls"]), \
                patch("evaluate_icd_accuracy.run", return_value=report), contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as failure:
                main()
        self.assertEqual(failure.exception.code, 1)
        rows[1] = self.evaluation_row("case", "enhanced_cls", True)
        report = summarize(rows)
        with patch("sys.argv", ["evaluate_icd_accuracy.py", "--fail-on-regression"]), \
                patch("evaluate_icd_accuracy.run", return_value=report), contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(main())

    def test_cli_regression_gate_requires_baseline_and_selected_variant(self):
        for arguments in (("--variants", "enhanced_cls", "--fail-on-regression", "enhanced_cls"),
                          ("--variants", "legacy", "enhanced_mean", "--fail-on-regression", "enhanced_cls"),
                          ("--fail-on-regression", "legacy"),
                          ("--retrieval-only", "--fail-on-regression", "enhanced_cls")):
            with self.subTest(arguments=arguments), patch("sys.argv", ["evaluate_icd_accuracy.py", *arguments]), \
                    patch("evaluate_icd_accuracy.run") as run, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as failure:
                    main()
                self.assertEqual(failure.exception.code, 2)
                run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
