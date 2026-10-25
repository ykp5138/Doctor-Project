import unittest

from icd_evidence import assertion_reason


class IcdAssertionRegressionTests(unittest.TestCase):
    def test_history_code_records_the_history_without_creating_current_disease(self):
        family = "Family history of diabetes mellitus."
        self.assertIsNone(assertion_reason("Family history of diabetes mellitus", family, "Z83.3"))
        self.assertIsNotNone(assertion_reason("Type 2 diabetes mellitus without complications", family, "E11.9"))
        personal = "Personal history of malignant neoplasm of breast."
        self.assertIsNone(assertion_reason("Personal history of malignant neoplasm of breast", personal, "Z85.3"))
        self.assertIsNotNone(assertion_reason("Malignant neoplasm of breast", personal, "C50.919"))

    def test_negated_history_still_rejects_history_codes(self):
        self.assertIsNotNone(assertion_reason("Family history of diabetes mellitus",
                                             "No family history of diabetes mellitus.", "Z83.3"))
        self.assertIsNotNone(assertion_reason("Personal history of malignant neoplasm of breast",
                                             "No personal history of malignant neoplasm of breast.", "Z85.3"))

    def test_history_codes_require_the_correct_subject_and_historical_context(self):
        family_description = "Family history of diabetes mellitus"
        personal_description = "Personal history of other endocrine, nutritional and metabolic disease"
        self.assertIsNotNone(assertion_reason(family_description,
                                             "The patient has type 2 diabetes mellitus.", "Z83.3"))
        self.assertIsNotNone(assertion_reason(personal_description,
                                             "The patient has endocrine disease.", "Z86.39"))
        self.assertIsNotNone(assertion_reason("Personal history of malignant neoplasm of breast",
                                             "The mother has malignant neoplasm of breast.", "Z85.3"))
        self.assertIsNotNone(assertion_reason("Personal history of other diseases of the circulatory system",
                                             "The patient is here for routine follow-up.", "Z86.79"))
        self.assertIsNone(assertion_reason(family_description,
                                          "The mother was diagnosed with diabetes mellitus.", "Z83.3"))
        self.assertIsNotNone(assertion_reason("Type 2 diabetes mellitus without complications",
                                             "The mother was diagnosed with type 2 diabetes mellitus.", "E11.9"))

    def test_active_controlled_disease_is_not_converted_to_personal_history(self):
        self.assertIsNotNone(assertion_reason("Personal history of other diseases of the circulatory system",
                                             "History of circulatory disease, currently controlled with medication.", "Z86.79"))

    def test_broad_history_labels_can_use_an_explicit_spoken_history_clause(self):
        personal = "Personal history of diseases of the skin and subcutaneous tissue"
        family = "Family history of diseases of the skin and subcutaneous tissue"
        self.assertIsNone(assertion_reason(personal, "History of acne vulgaris, resolved.", "Z87.2"))
        self.assertIsNone(assertion_reason(family, "Mother has eczema.", "Z84.0"))
        for text in ("The patient has acne vulgaris.", "Mother has acne vulgaris.",
                     "No history of acne vulgaris.",
                     "History of acne vulgaris, currently controlled with medication."):
            self.assertIsNotNone(assertion_reason(personal, text, "Z87.2"), text)
        for text in ("The patient has eczema.", "Mother has no eczema.",
                     "No family history of eczema.", "History of eczema, resolved."):
            self.assertIsNotNone(assertion_reason(family, text, "Z84.0"), text)

    def test_absent_complication_does_not_negate_underlying_diabetes(self):
        description = "Type 2 diabetes mellitus without complications"
        for text in ("The patient has type 2 diabetes, without complications.",
                     "Diabetes mellitus, type 2, without complications, controlled on metformin.",
                     "No current complications from type 2 diabetes mellitus."):
            self.assertIsNone(assertion_reason(description, text, "E11.9"), text)
        self.assertIsNotNone(assertion_reason(description, "The patient has no diabetes mellitus.", "E11.9"))

    def test_without_esophagitis_does_not_negate_reflux(self):
        from simple_icd_10_cm import get_description
        description = get_description("K21.9")
        for text in ("Assessment: gastro-esophageal reflux disease without esophagitis.",
                     "The patient has reflux without esophagitis.",
                     "No esophagitis, but reflux disease is present."):
            self.assertIsNone(assertion_reason(description, text, "K21.9"), text)
        for text in ("The patient has no reflux disease.",
                     "Gastro-esophageal reflux disease is not present.",
                     "No gastro-esophageal reflux disease without esophagitis."):
            self.assertIsNotNone(assertion_reason(description, text, "K21.9"), text)

    def test_required_with_complication_is_not_stripped_from_negation_check(self):
        self.assertIsNotNone(assertion_reason("Type 2 diabetes mellitus with diabetic nephropathy",
                                             "The patient has no diabetic nephropathy.", "E11.21"))

    def test_never_had_and_postfix_ruled_out_negate_all_occurrences(self):
        description = "Unspecified asthma, uncomplicated"
        for text in ("The patient denies asthma and has never had asthma.",
                     "The patient never had asthma.",
                     "Asthma ruled out.", "Asthma was ruled out.",
                     "Asthma has never been diagnosed."):
            self.assertIsNotNone(assertion_reason(description, text, "J45.909"), text)
        self.assertIsNone(assertion_reason(description, "The patient never had eczema but has asthma.", "J45.909"))

    def test_diagnosis_phrase_preserves_its_own_negative_or_conditional_scope(self):
        for text in ("The patient was not diagnosed with acne vulgaris.",
                     "The patient has not been diagnosed with acne vulgaris.",
                     "The patient denies being diagnosed with acne vulgaris.",
                     "If diagnosed with acne vulgaris, we will discuss treatment.",
                     "If the patient is diagnosed with acne vulgaris, we will discuss treatment.",
                     "The clinician has not confirmed acne vulgaris.",
                     "No confirmed diagnosis of acne vulgaris.",
                     "If confirmed acne vulgaris, treatment will be discussed."):
            self.assertIsNotNone(assertion_reason("Acne vulgaris", text, "L70.0"), text)
        for text in ("The patient was diagnosed with acne vulgaris.",
                     "The clinician confirmed acne vulgaris.",
                     "No fever, diagnosed with acne vulgaris.",
                     "No fever, the clinician confirmed acne vulgaris.",
                     "No fever. The patient was diagnosed with acne vulgaris.",
                     "The patient denies fever and has acne vulgaris."):
            self.assertIsNone(assertion_reason("Acne vulgaris", text, "L70.0"), text)

    def test_active_controlled_history_can_document_current_chronic_disease(self):
        for text in ("History of hypertension, well controlled on lisinopril.",
                     "History of hypertension, currently controlled with lisinopril.",
                     "History of hypertension, is managed with lisinopril."):
            self.assertIsNone(assertion_reason("Essential (primary) hypertension", text, "I10"), text)

    def test_remote_or_ambiguous_history_is_not_assumed_active(self):
        for text in ("History of hypertension.",
                     "Remote history of hypertension, resolved.",
                     "History of hypertension, inactive and off treatment.",
                     "Prior history of hypertension, previously controlled on lisinopril.",
                     "Family history of hypertension, well controlled on lisinopril."):
            self.assertIsNotNone(assertion_reason("Essential (primary) hypertension", text, "I10"), text)


if __name__ == "__main__":
    unittest.main()
