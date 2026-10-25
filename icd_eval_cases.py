"""Synthetic, inspectable coding regression cases; not a clinician-validated corpus."""


def case(name, transcript, expected=(), diagnoses=(), symptoms=(), medications=(), procedures=(), history=(), allowed=()):
    return dict(name=name, transcript=transcript, expected_codes=list(expected), allowed_codes=list(allowed),
                concepts=dict(diagnoses_mentioned=list(diagnoses), symptoms=list(symptoms),
                              medications_discussed=list(medications), procedures_ordered=list(procedures),
                              history_relevant=list(history), vitals_exam_findings=[]))


def build_cases():
    return [
        case("acne_explicit", "The assessment is acne vulgaris. We will discuss treatment.", ["L70.0"], ["acne vulgaris"]),
        case("acne_late", "The weather and parking arrangements were discussed. " * 120 + "The assessment is acne vulgaris.", ["L70.0"], ["acne vulgaris"]),
        case("hypertension", "Assessment: Essential primary hypertension. This is the current diagnosis.", ["I10"], ["Essential (primary) hypertension"]),
        case("diabetes", "The patient has type 2 diabetes mellitus without complications.", ["E11.9"], ["type 2 diabetes mellitus without complications"]),
        case("back_pain", "Assessment: low back pain, unspecified. There was no injury.", ["M54.50"], ["low back pain, unspecified"]),
        case("aspirin", "The patient takes aspirin every day as an ongoing medication.", ["Z79.82"], medications=["takes aspirin daily"]),
        case("otitis", "Assessment: acute suppurative otitis media without spontaneous rupture of ear drum, right ear.", ["H66.001"], ["acute suppurative otitis media without spontaneous rupture of ear drum, right ear"]),
        case("multiple_diagnoses", "Assessment: acne vulgaris. The patient also has essential primary hypertension.", ["L70.0", "I10"], ["acne vulgaris", "Essential (primary) hypertension"]),
        case("acne_negated", "The patient does not have acne vulgaris. There is no skin complaint.", diagnoses=["no acne vulgaris"]),
        case("acne_family", "The patient's father has acne vulgaris. The patient has no skin complaints.", history=["father has acne vulgaris"], allowed=["Z84.0"]),
        case("acne_hypothetical", "If acne vulgaris develops in the future, we will discuss treatment. There is no current skin disorder.", diagnoses=["possible future acne vulgaris"]),
        case("acne_resolved", "The patient has a history of acne vulgaris, now resolved. No active skin problem is reported.", history=["history of acne vulgaris, resolved"], allowed=["Z87.2"]),
        case("vitamin_not_toxicity", "The patient takes a multivitamin daily. There is no overdose, toxicity, or adverse reaction.", medications=["multivitamin daily"], allowed=["Z79.899"]),
        case("not_pregnant", "The patient is trying to become pregnant but is not pregnant.", history=["trying to get pregnant, not pregnant"], allowed=["Z31.69", "Z31.9"]),
        case("nonclinical", "We discussed the football game, the weather, and coffee. No medical problem was discussed.", symptoms=["football game", "weather"], medications=["coffee"]),
        case("unrelated_negation", "The patient denies fever and has acne vulgaris. The acne is not severe.", ["L70.0"], ["acne vulgaris"]),
        case("screening_not_cancer", "A screening mammogram was ordered. No breast cancer has been diagnosed.", ["Z12.31"], procedures=["screening mammogram"]),
        case("family_diabetes_patient_acne", "The patient's mother has type 2 diabetes mellitus without complications. The patient's own assessment is acne vulgaris.", ["L70.0"], ["acne vulgaris"], history=["mother has type 2 diabetes mellitus without complications"], allowed=["Z83.3"]),
    ]


def build_holdout_cases():
    """Separate conditions/contexts for a second check after development changes."""
    return [
        case("holdout_psoriasis", "Assessment: psoriasis vulgaris. This is the patient's active skin disease.", ["L40.0"], ["psoriasis vulgaris"]),
        case("holdout_rosacea", "The patient has rosacea, unspecified. This is not acne vulgaris.", ["L71.9"], ["rosacea, unspecified"], history=["no acne vulgaris"]),
        case("holdout_eczema", "Assessment: atopic dermatitis, unspecified. The patient has no skin infection.", ["L20.9"], ["atopic dermatitis, unspecified"]),
        case("holdout_allergy", "Assessment: allergic rhinitis, unspecified. The patient has no pneumonia.", ["J30.9"], ["allergic rhinitis, unspecified"]),
        case("holdout_reflux", "Assessment: gastro-esophageal reflux disease without esophagitis.", ["K21.9"], ["gastro-esophageal reflux disease without esophagitis"]),
        case("holdout_knee", "The patient has unilateral primary osteoarthritis of the left knee. No injury occurred.", ["M17.12"], ["unilateral primary osteoarthritis, left knee"]),
        case("holdout_asthma_negated", "The patient denies asthma and has never had asthma. No breathing complaint is reported.", diagnoses=["no asthma"]),
        case("holdout_family_psoriasis", "The patient's mother has psoriasis vulgaris. The patient has normal skin and no skin condition.", history=["mother has psoriasis vulgaris"], allowed=["Z84.0"]),
        case("holdout_future_diabetes", "If type 2 diabetes mellitus develops in the future, we will discuss medication. Diabetes has not been diagnosed.", diagnoses=["possible future type 2 diabetes mellitus"]),
        case("holdout_late_reflux", "The appointment logistics were discussed. " * 170 + "The assessment is gastro-esophageal reflux disease without esophagitis.", ["K21.9"], ["gastro-esophageal reflux disease without esophagitis"]),
    ]


def build_context_cases():
    """Review-driven contexts, including synonyms and required history codes."""
    return [
        case("context_hypertension_synonym", "Your blood pressure remains persistently high. I am diagnosing hypertension today.", ["I10"], ["hypertension"]),
        case("context_reflux_synonym", "The patient has GERD with acid reflux. There is no esophagitis.", ["K21.9"], ["GERD"]),
        case("context_diabetes_qualifier", "The patient has type 2 diabetes, without complications.", ["E11.9"], ["type 2 diabetes mellitus without complications"]),
        case("context_chronic_controlled", "History of hypertension, well controlled on lisinopril.", ["I10"], ["hypertension"]),
        case("context_family_history", "Family history of diabetes mellitus. The patient does not have diabetes.", ["Z83.3"], history=["family history of diabetes mellitus"]),
        case("context_personal_history", "Personal history of malignant neoplasm of breast, now resolved. There is no current cancer.", ["Z85.3"], history=["personal history of malignant neoplasm of breast"]),
        case("context_no_family_history", "No family history of diabetes mellitus. The patient has no diabetes.", history=["no family history of diabetes mellitus"]),
        case("context_age_not_diabetes", "The patient is 2 years old and has no illness.", diagnoses=["type 2 diabetes mellitus without complications"]),
        case("context_question_then_denial", "Do you have acne vulgaris? No, I have never had acne vulgaris.", diagnoses=["acne vulgaris"]),
        case("context_question_then_confirmed", "Do you have acne vulgaris? Yes, my dermatologist confirmed acne vulgaris yesterday.", ["L70.0"], ["acne vulgaris"]),
    ]
