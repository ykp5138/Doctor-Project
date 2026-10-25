import os
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import icd10_retriever as retrieval
import main


class IcdConfigurationTests(unittest.TestCase):
    def test_builder_cannot_overwrite_either_original_index_even_with_force(self):
        import build_icd_index_sapbert as builder
        for directory in ("indexes", "indexes_sapbert"):
            with patch("sys.argv", ["build_icd_index_sapbert.py", "--output-dir", directory, "--force"]):
                with self.assertRaisesRegex(ValueError, "protected"):
                    builder.main()

    def test_defaults_activate_enhanced_selection(self):
        loaded = SimpleNamespace(sapbert=SimpleNamespace(embedding_config={"pooling": "cls"}))
        with patch.dict(os.environ, {}, clear=True), patch.object(retrieval, "get_retriever", return_value=loaded), patch("icd_selector.suggest_icd", return_value=[]) as enhanced:
            main._suggest_icd_rag({}, "", [], "")
        self.assertEqual(enhanced.call_args.kwargs["retrieval_mode"], "enhanced")

    def test_default_preserves_baseline_when_only_old_vectors_are_available(self):
        loaded = SimpleNamespace(sapbert=SimpleNamespace(embedding_config={"pooling": "legacy_auto"}))
        with patch.dict(os.environ, {}, clear=True), patch.object(retrieval, "get_retriever", return_value=loaded):
            with patch.object(main, "_suggest_icd_rag_legacy", return_value=[]) as saved:
                main._suggest_icd_rag({}, "", [], "")
        saved.assert_called_once()

    def test_enhanced_uses_new_index_only_when_both_artifacts_exist(self):
        with patch.dict(os.environ, {"ICD_SELECTOR_MODE": "enhanced"}, clear=True):
            with patch.object(retrieval.os.path, "isfile", return_value=True):
                self.assertEqual(retrieval._sapbert_index_dir(), retrieval.SAPBERT_CLS_DIR)
            with patch.object(retrieval.os.path, "isfile", side_effect=[True, False]):
                self.assertEqual(retrieval._sapbert_index_dir(), retrieval.SAPBERT_DIR)

    def test_explicit_legacy_mode_keeps_original_vectors(self):
        with patch.dict(os.environ, {"ICD_SELECTOR_MODE": "legacy"}, clear=True):
            self.assertEqual(retrieval._sapbert_index_dir(), retrieval.SAPBERT_DIR)

    def test_index_override_is_respected(self):
        with patch.dict(os.environ, {"ICD_SAPBERT_INDEX_DIR": "my-index"}, clear=True):
            self.assertEqual(retrieval._sapbert_index_dir(), "my-index")

    def test_selector_legacy_switch_uses_preserved_function(self):
        with patch.dict(os.environ, {"ICD_SELECTOR_MODE": "legacy"}, clear=True):
            with patch.object(main, "_suggest_icd_rag_legacy", return_value=[{"code": "L70.0"}]) as saved:
                result = main._suggest_icd_rag({"diagnoses_mentioned": ["acne vulgaris"]}, "summary", [{"text": "acne"}], "L70")
        self.assertEqual(result, [{"code": "L70.0"}])
        saved.assert_called_once_with({"diagnoses_mentioned": ["acne vulgaris"]}, "summary", [{"text": "acne"}], "L70")

    def test_enhanced_dispatch_preserves_words_summary_and_range(self):
        with patch.dict(os.environ, {"ICD_SELECTOR_MODE": "enhanced", "ICD_RETRIEVAL_MODE": "enhanced"}, clear=True):
            with patch("icd_selector.suggest_icd", return_value=[]) as enhanced:
                main._suggest_icd_rag({"diagnoses_mentioned": ["acne vulgaris"]}, "summary", [{"text": "acne"}], "L70")
        enhanced.assert_called_once_with({"diagnoses_mentioned": ["acne vulgaris"]}, "summary", [{"text": "acne"}], "L70",
                                         retrieval_mode="enhanced", guardrail=main._guardrail_reject)


if __name__ == "__main__":
    unittest.main()
