import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from icd_evidence import exact_word_indices, build_evidence_spans, validate_evidence_span, assertion_reason
from icd_embeddings import make_embedding_config, embedding_config_from_metadata, load_embedding_model
from icd_selector import suggest_icd
from icd10_utils import is_complete_code
from icd10_retriever import _retrieve_concepts


def words(text):
    return [{"text": token, "start": index * .2, "end": (index + 1) * .2} for index, token in enumerate(text.split())]


class IcdAccuracyTests(unittest.TestCase):
    def test_strict_matching_preserves_multi_token_asr_indices(self):
        self.assertEqual(exact_word_indices("acne vulgaris", [{"text": "Acne vulgaris."}]), [0])
        self.assertEqual(exact_word_indices("severe acne", words("Acne vulgaris.")), [])

    def test_selector_evidence_keeps_real_index_when_an_asr_word_contains_multiple_tokens(self):
        transcript = [{"text": "Assessment: acne vulgaris.", "start": 0, "end": 2}]
        retriever = SimpleNamespace(retrieve_for_concepts=lambda *a, **k: [
            {"code": "L70.0", "description": "Acne vulgaris", "matched_query": "acne vulgaris"}])
        response = Mock()
        response.json.return_value = {"response": '{"picks":[{"code":"L70.0","span_id":"w0-1"}]}'}
        result = suggest_icd({"diagnoses_mentioned": ["acne vulgaris"]}, "", transcript,
                             retriever=retriever, post=lambda *a, **k: response)
        self.assertEqual(result[0]["evidence"], [{"phrase": "Assessment: acne vulgaris.", "word_indices": [0]}])

    def test_late_diagnosis_is_available_beyond_old_cutoff(self):
        text = "The weather and parking were discussed. " * 150 + "The assessment is acne vulgaris."
        spans = build_evidence_spans(words(text), {"diagnoses_mentioned": ["acne vulgaris"]}, max_chars=1600)
        self.assertTrue(any("acne vulgaris" in item["text"] for item in spans))
        for item in spans:
            self.assertIsNotNone(validate_evidence_span(item["span_id"], spans, words(text)))
        self.assertIsNone(validate_evidence_span("invented", spans, words(text)))

    def test_assertions_reject_wrong_subject_or_status_without_losing_positive_diagnosis(self):
        for text in ("The patient denies acne vulgaris.", "The father has acne vulgaris.",
                     "If acne vulgaris develops we will discuss treatment.", "History of acne vulgaris, resolved.",
                     "Acne vulgaris has not been diagnosed."):
            self.assertIsNotNone(assertion_reason("Acne vulgaris", text), text)
        for text in ("The patient denies fever and has acne vulgaris.", "Assessment: acne vulgaris.",
                     "Acne vulgaris is not severe.", "No fever. The patient has acne vulgaris."):
            self.assertIsNone(assertion_reason("Acne vulgaris", text), text)

    def test_nonleaf_items_are_not_usable_codes(self):
        self.assertTrue(is_complete_code("L70.0"))
        self.assertFalse(is_complete_code("L70"))
        self.assertFalse(is_complete_code("T20.16"))

    def test_negated_specific_diagnosis_cannot_become_unspecified_disease(self):
        self.assertIsNotNone(assertion_reason("Acne, unspecified", "The patient does not have acne vulgaris."))
        self.assertIsNotNone(assertion_reason("Long term (current) use of aspirin", "The patient denies aspirin use."))

    def test_medication_similarity_does_not_support_unstated_deficiency(self):
        from icd_selector import _supported
        candidate = {"code": "E56.8", "description": "Deficiency of other vitamins",
                     "matched_query": "multivitamin daily",
                     "matched_concepts": [{"category": "medications_discussed", "text": "multivitamin daily"}]}
        self.assertFalse(_supported(candidate, {"phrase": "The patient takes a multivitamin daily."}))

    def test_age_does_not_support_diabetes_and_diabetes_type_must_agree(self):
        from icd_selector import _supported, _context_rejection
        self.assertFalse(_supported({"code": "E11.9", "description": "Type 2 diabetes mellitus without complications"},
                                    {"phrase": "The patient is 2 years old."}))
        self.assertIsNotNone(_context_rejection("E10.9", "The patient has type 2 diabetes mellitus."))
        self.assertIsNone(_context_rejection("E11.9", "The patient has type 2 diabetes mellitus."))

    def test_planning_pregnancy_and_weather_do_not_become_maternity_or_injury_codes(self):
        from icd_selector import _context_rejection, _supported
        self.assertIsNotNone(_context_rejection("O26.91", "The patient is trying to become pregnant but is not pregnant."))
        self.assertIsNotNone(_context_rejection("W00.9XXA", "We discussed the football game and weather."))
        self.assertIsNone(_context_rejection("W00.9XXA", "The patient fell on ice and was injured."))
        self.assertIsNone(_context_rejection("O72.1", "The patient is postpartum after delivery, not currently pregnant."))
        candidate = {"code": "R92.0", "description": "Mammographic microcalcification found on diagnostic imaging of breast",
                     "matched_concepts": [{"category": "procedures_ordered", "text": "screening mammogram"}]}
        self.assertFalse(_supported(candidate, {"phrase": "A screening mammogram was ordered."}))

    def test_old_vectors_keep_legacy_loader_and_dimensions_are_checked(self):
        old = embedding_config_from_metadata({"model_name": "sapbert"}, 768)
        self.assertEqual(old["pooling"], "legacy_auto")
        new = make_embedding_config("sapbert", pooling="cls", dimension=768)
        with self.assertRaises(ValueError):
            embedding_config_from_metadata({"embedding_config": new}, 384)

    def test_cls_loader_explicitly_disables_mean_pooling(self):
        transformer = Mock()
        transformer.get_word_embedding_dimension.return_value = 768
        model = Mock()
        model.get_sentence_embedding_dimension.return_value = 768
        fake = SimpleNamespace(SentenceTransformer=Mock(return_value=model),
                               models=SimpleNamespace(Transformer=Mock(return_value=transformer), Pooling=Mock()))
        with patch.dict("sys.modules", {"sentence_transformers": fake}):
            load_embedding_model(make_embedding_config("sapbert", pooling="cls", dimension=768))
        self.assertTrue(fake.models.Pooling.call_args.kwargs["pooling_mode_cls_token"])
        self.assertFalse(fake.models.Pooling.call_args.kwargs["pooling_mode_mean_tokens"])

    def test_diagnosis_anchor_survives_model_disagreement_and_preserves_concept_coverage(self):
        metadata = [{"code": "L70.0", "description": "Acne vulgaris"},
                    {"code": "L70.4", "description": "Infantile acne"},
                    {"code": "I10", "description": "Essential (primary) hypertension"}]
        def retrieve(queries, top_k=10):
            return [{**item, "score": .8, "matched_query": queries[0]} for item in reversed(metadata)]
        model = SimpleNamespace(metadata=metadata, retrieve=retrieve)
        candidates = _retrieve_concepts([("a", model), ("b", model)],
                                       {"diagnoses_mentioned": ["acne vulgaris", "Essential (primary) hypertension"]}, 2, 2)
        self.assertEqual([item["code"] for item in candidates], ["L70.0", "I10"])

    def test_official_inclusion_name_is_a_candidate_anchor_without_forcing_a_pick(self):
        metadata = [{"code": "I10", "description": "Essential (primary) hypertension"},
                    {"code": "I15.9", "description": "Secondary hypertension, unspecified"}]
        model = SimpleNamespace(metadata=metadata, retrieve=lambda queries, top_k: [
            {**metadata[1], "score": .9, "matched_query": queries[0]}])
        candidates = _retrieve_concepts([("a", model)], {"diagnoses_mentioned": ["hypertension"]}, 2, 2)
        self.assertEqual(candidates[0]["code"], "I10")
        self.assertTrue(candidates[0]["exact_diagnosis"])

    def test_selected_acne_with_bad_quote_repairs_to_real_diagnosis_without_inventing_codes(self):
        transcript = words("The assessment is acne vulgaris.")
        retriever = SimpleNamespace(retrieve_for_concepts=lambda *a, **k: [
            {"code": "L70.0", "description": "Acne vulgaris", "matched_query": "acne vulgaris"}])
        response = Mock()
        response.json.return_value = {"response": '{"picks":[{"code":"L70.0","evidence_phrase":"mild to moderate acne on the face"}]}'}
        trace = {}
        selected = suggest_icd({"diagnoses_mentioned": ["acne vulgaris"]}, "", transcript,
                               retriever=retriever, post=lambda *a, **k: response, diagnostics=trace)
        self.assertEqual([item["code"] for item in selected], ["L70.0"])
        self.assertEqual(selected[0]["evidence"][0]["phrase"], "The assessment is acne vulgaris.")
        self.assertIn("repaired", trace["decisions"][0])

    def test_repair_never_turns_family_history_into_patient_diagnosis(self):
        transcript = words("The father has acne vulgaris.")
        retriever = SimpleNamespace(retrieve_for_concepts=lambda *a, **k: [
            {"code": "L70.0", "description": "Acne vulgaris", "matched_query": "acne vulgaris"}])
        response = Mock()
        response.json.return_value = {"response": '{"picks":[{"code":"L70.0","span_id":"bad"},{"code":"MADEUP","span_id":"bad"}]}'}
        self.assertEqual(suggest_icd({"diagnoses_mentioned": ["acne vulgaris"]}, "", transcript,
                                    retriever=retriever, post=lambda *a, **k: response), [])

    def test_requested_range_cannot_leak_excluded_code_from_model_response(self):
        transcript = words("The patient has acne vulgaris and hypertension.")
        retriever = SimpleNamespace(retrieve_for_concepts=lambda *a, **k: [
            {"code": "L70.0", "description": "Acne vulgaris", "matched_query": "acne vulgaris"},
            {"code": "I10", "description": "Essential (primary) hypertension", "matched_query": "hypertension"}])
        response = Mock()
        response.json.return_value = {"response": '{"picks":[{"code":"I10","span_id":"w0-8"}]}'}
        with patch("icd_selector.get_codes_for_range_input", return_value=[{"code": "L70.0"}]):
            result = suggest_icd({"diagnoses_mentioned": ["acne vulgaris", "hypertension"]}, "", transcript, "L70",
                                 retriever=retriever, post=lambda *a, **k: response)
        self.assertEqual(result, [])

    def test_selected_hypertension_repairs_wrong_span_using_official_inclusion(self):
        transcript = words("Your blood pressure remains high. I am diagnosing hypertension today.")
        retriever = SimpleNamespace(retrieve_for_concepts=lambda *a, **k: [
            {"code": "I10", "description": "Essential (primary) hypertension", "matched_query": "hypertension",
             "matched_alias": "hypertension (arterial) (benign) (essential) (malignant) (primary) (systemic)"}])
        response = Mock()
        response.json.return_value = {"response": '{"picks":[{"code":"I10","span_id":"w0-5"}]}'}
        result = suggest_icd({"diagnoses_mentioned": ["hypertension"]}, "", transcript,
                             retriever=retriever, post=lambda *a, **k: response)
        self.assertEqual(result[0]["evidence"][0]["phrase"], "I am diagnosing hypertension today.")

    def test_question_and_denial_cannot_become_confirmed_diagnosis(self):
        transcript = words("Do you have acne vulgaris? No, I have never had acne vulgaris.")
        retriever = SimpleNamespace(retrieve_for_concepts=lambda *a, **k: [
            {"code": "L70.0", "description": "Acne vulgaris", "matched_query": "acne vulgaris"}])
        response = Mock()
        response.json.return_value = {"response": '{"picks":[{"code":"L70.0","span_id":"w0-5"}]}'}
        self.assertEqual(suggest_icd({"diagnoses_mentioned": ["acne vulgaris"]}, "", transcript,
                                    retriever=retriever, post=lambda *a, **k: response), [])


if __name__ == "__main__":
    unittest.main()
