"""Verbatim transcript spans and conservative assertion checks for ICD selection."""
import re

STOP_WORDS = set("a an the to of for in on and or is are was were with patient has have had no not denies history family possible rule out unspecified other uncomplicated".split())


def tokens(text):
    return re.findall(r"\w+", str(text).casefold())


def exact_word_indices(phrase, words):
    wanted = tokens(phrase)
    if not wanted:
        return []
    flat, owners = [], []
    for index, word in enumerate(words):
        for token in tokens(word.get("text", "") if isinstance(word, dict) else word):
            flat.append(token)
            owners.append(index)
    for start in range(len(flat) - len(wanted) + 1):
        if flat[start:start + len(wanted)] == wanted:
            return list(dict.fromkeys(owners[start:start + len(wanted)]))
    return []


def _sentences(words, max_words=45):
    start = 0
    for index, word in enumerate(words):
        text = str(word.get("text", ""))
        next_speaker = index + 1 < len(words) and words[index + 1].get("speaker") != word.get("speaker")
        boundary = bool(re.search(r"[.!?][\"')]*$", text)) or next_speaker
        if boundary or index - start + 1 >= max_words:
            yield start, index + 1
            start = index + 1 if boundary else max(start + 1, index + 1 - 8)
    if start < len(words):
        yield start, len(words)


def build_evidence_spans(words, concepts, candidates=None, max_chars=14000, max_span_words=45):
    """Rank complete short utterances across the WHOLE transcript, retaining context.

    Exact diagnosis matches receive priority, but are never automatic code picks.
    Sentences keep negation/family/hypothetical wording rather than extracting an
    isolated disease name and losing its assertion.
    """
    words = [word if isinstance(word, dict) else {"text": str(word)} for word in words]
    diagnoses = [str(value) for value in concepts.get("diagnoses_mentioned", [])]
    terms = [str(value) for values in concepts.values() if isinstance(values, list) for value in values if isinstance(value, str)]
    if candidates:
        terms += [str(item.get("matched_query", "")) for item in candidates]
    term_tokens = [set(tokens(term)) - STOP_WORDS for term in terms]
    ranked = []
    for start, end in _sentences(words, max_span_words):
        text = " ".join(str(word.get("text", "")) for word in words[start:end]).strip()
        if not text:
            continue
        normalized = " ".join(tokens(text))
        sentence_tokens = set(tokens(text))
        exact = any(" ".join(tokens(diagnosis)) in normalized for diagnosis in diagnoses if tokens(diagnosis))
        overlap = max((len(query & sentence_tokens) / len(query) for query in term_tokens if query), default=0)
        ranked.append((int(exact) * 10 + overlap, start, end, text))
    chosen, used = [], 0
    # Relevant late statements compete on clinical relevance, not transcript offset.
    for score, start, end, text in sorted(ranked, key=lambda row: (-row[0], row[1])):
        if used + len(text) + 30 > max_chars:
            continue
        if score == 0 and used > max_chars // 2:
            continue
        chosen.append(dict(span_id=f"w{start}-{end}", text=text, word_indices=list(range(start, end))))
        used += len(text) + 30
    return sorted(chosen, key=lambda row: row["word_indices"][0])


def validate_evidence_span(span_id, spans, words):
    span = next((item for item in spans if item["span_id"] == span_id), None)
    if not span:
        return None
    indices = span["word_indices"]
    if not indices or any(type(index) is not int or index < 0 or index >= len(words) for index in indices):
        return None
    actual = " ".join(str(words[index].get("text", "")) for index in indices).strip()
    if actual != span["text"]:
        return None
    return {"phrase": actual, "word_indices": indices}


def assertion_reason(description, text, code=None):
    """Conservative checks around named conditions, not a full clinical NLP system."""
    normalized = " ".join(re.findall(r"\w+|[;.!?]", str(text).casefold()))
    normalized_description = " ".join(tokens(description))
    normalized_code = str(code or "").upper()
    family_history_code = (normalized_code.startswith(("Z80", "Z81", "Z82", "Z83", "Z84"))
                           and normalized_description.startswith("family history"))
    personal_history_code = (normalized_code.startswith(("Z85", "Z86", "Z87"))
                             and normalized_description.startswith("personal history"))
    # Keep an intact description as the first target. If it is not spoken,
    # "without X" describes the absence of X, rather than absence of the named
    # underlying disease, and X must not become that disease's fallback anchor.
    # Keep "with X" in the fallback: a negated required complication must still
    # be able to reject a code that asserts that complication.
    qualifier_tokens = {"complication", "complications", "uncomplicated", "without"}
    disease_description = re.split(r"\bwithout\b", normalized_description, maxsplit=1)[0]
    description_tokens = [token for token in tokens(disease_description)
                          if token not in STOP_WORDS and token not in qualifier_tokens]
    if not description_tokens:
        return None
    # Use the complete named diagnosis when available; a single broad word can
    # incorrectly bind unrelated negations (e.g. 'no fever' with positive acne).
    target = normalized_description
    positions = [match.start() for match in re.finditer(r"\b" + re.escape(target) + r"\b", normalized)]
    if positions and (family_history_code or personal_history_code):
        # Scope history assertions around the condition inside an exact history
        # label, so its family/personal marker remains in the preceding context.
        prefix = re.match(r"(?:family|personal) history of\s+", target)
        if prefix:
            positions = [position + prefix.end() for position in positions]
            target = target[prefix.end():]
    if not positions:
        target = " ".join(description_tokens)
        positions = [match.start() for match in re.finditer(r"\b" + re.escape(target) + r"\b", normalized)]
    if not positions:
        generic = set("disease disorder syndrome encounter care term current use personal".split())
        anchors = [token for token in description_tokens if token not in generic and len(token) >= 4 and token in tokens(text)]
        if not anchors and (family_history_code or personal_history_code):
            # Broad history labels (e.g. "diseases of the skin") need not name
            # the spoken condition (e.g. "acne vulgaris"). Use an anchor from an
            # actual history/family clause, while leaving semantic code choice
            # to the model and concept-support validator.
            marker = (r"\b(?:family history of|(?:mother|father|sister|brother|parent|grandmother|grandfather)"
                      r"\s+(?:has|had|was diagnosed with))\s+" if family_history_code else
                      r"\b(?:personal\s+)?history of\s+")
            clause = re.search(marker, normalized)
            if clause:
                condition = re.split(r"[;.!?]|\b(?:but|however|resolved|inactive|remote|currently|controlled|treated|managed)\b",
                                     normalized[clause.end():], maxsplit=1)[0]
                status_tokens = {"well", "poorly", "now", "still", "active", "daily", "medication", "treatment"}
                anchors = [token for token in tokens(condition)
                           if token not in STOP_WORDS | generic | qualifier_tokens | status_tokens and len(token) >= 4]
        if not anchors:
            if family_history_code or personal_history_code:
                return "history code requires evidence of the named history"
            return None
        target = max(anchors, key=len)
        positions = [match.start() for match in re.finditer(r"\b" + re.escape(target) + r"\b", normalized)]
    reasons = []
    for position in positions:
        before = normalized[max(0, position - 100):position]
        # Preserve the subject in "mother was diagnosed with ..." before
        # splitting positive assertion phrases for ordinary disease checks.
        subject_before = re.split(r"[;.!?]|\b(?:but|however|and the patient has)\b", before)[-1]
        before = re.split(r"[;.!?]|\b(?:but|however|and has|and reports|and the patient has)\b", before)[-1]
        # An affirmative diagnosis phrase can start a new assertion after an
        # unrelated negative finding. Its own negative/conditional modifier must
        # survive: "not diagnosed with" and "if diagnosed with" are not positive
        # assertion boundaries.
        assertion_modifier, cutoff = None, 0
        for match in re.finditer(r"\b(?:confirmed|confirms|diagnosed with|assessment is)\b", before):
            prefix = before[:match.start()]
            negative_scope = re.search(
                r"\b(?:no|not|never|denies|denied)\s+"
                r"(?:(?:yet|been|being|previously|formally|definitively|clinically)\s+){0,3}$", prefix)
            conditional_scope = re.search(
                r"\b(?:if|unless|might|may|could|would|possible|possibly)\s+"
                r"(?:(?:the|this|patient|is|was|be|been|being|eventually|later|ever|we|they|he|she|you|are|were)\s+){0,5}$", prefix)
            if negative_scope:
                assertion_modifier = "negated diagnosis"
            elif conditional_scope:
                assertion_modifier = "hypothetical or uncertain diagnosis"
            else:
                cutoff = match.end()
                assertion_modifier = None
        before = before[cutoff:]
        after = normalized[position + len(target):position + len(target) + 65]
        # A negative complication finding does not negate the named underlying
        # disease: "no current complications from type 2 diabetes mellitus".
        before = re.split(r"\bcomplications?\s+(?:from|of|due to|related to)\s+", before)[-1]
        family_context = re.search(
            r"\b(?:family history of|(?:mother|father|sister|brother|parent|grandmother|grandfather)"
            r"\s+(?:has|had|was diagnosed with))\s+(?:\w+\s+){0,4}$", subject_before)
        history_context = re.search(r"\b(history of|previous|prior|resolved)\s+(?:\w+\s+){0,3}$", before)
        resolved_after = re.match(r"\s+(?:(?:is|was|has)\s+)?(?:resolved|no longer present)\b", after)
        inactive = re.search(r"\b(resolved|remote|inactive|previous|prior|past|no longer|off treatment)\b",
                             before + " " + after)
        active_control = re.match(
            r"\s+(?:(?:disease|disorder|condition|syndrome)\s+)?"
            r"(?:(?:is|remains|still|currently|now)\s+){0,2}"
            r"(?:(?:well|poorly)\s+)?(?:controlled|managed|treated)\s+(?:on|with)\s+\w+", after)
        if assertion_modifier:
            reasons.append(assertion_modifier)
            continue
        if family_history_code and not family_context:
            reasons.append("family-history code requires a documented family history")
            continue
        if personal_history_code and (family_context or not (history_context or resolved_after)):
            reasons.append("personal-history code requires the patient's own historical condition")
            continue
        if personal_history_code and active_control and not inactive:
            reasons.append("personal-history code cannot replace a documented active condition")
            continue
        if re.match(r"\s+(?:(?:is|was)\s+not\s+(?:present|diagnosed|confirmed|found)|has\s+(?:not|never)\s+been\s+(?:diagnosed|confirmed)|(?:was\s+)?ruled\s+out)", after):
            reasons.append("negated diagnosis")
            continue
        if re.search(r"\b(no|not|never|denies|denied|without|negative for|ruled out)\s+(?:\w+\s+){0,3}$", before):
            reasons.append("negated diagnosis")
        elif family_context:
            if family_history_code:
                return None
            reasons.append("family history is not the patient's current diagnosis")
        elif re.search(r"\b(if|might|possible|possibly|rule out|screen for|screening for|checking for|testing for|risk of)\s+(?:\w+\s+){0,3}$", before):
            reasons.append("hypothetical or uncertain diagnosis")
        elif re.search(r"\b(history of|previous|prior|resolved)\s+(?:\w+\s+){0,3}$", before):
            if personal_history_code:
                return None
            # Bare "history of" remains ambiguous. Only an explicit ongoing
            # control/treatment statement for this condition establishes current
            # disease; resolved/remote/inactive histories retain their rejection.
            history_only = re.search(r"\bhistory of\s+(?:\w+\s+){0,3}$", before)
            if history_only and not inactive and active_control:
                return None
            reasons.append("historical diagnosis needs an appropriate history code")
        else:
            return None
    return reasons[0] if reasons else None
