import json
import statistics
import requests
import os
import string
import sys
import re

# Configuration
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3"

# Mapping common number words to digits to prevent semantic mismatches
NUMBER_MAP = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
    "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20", "thirty": "30",
    "forty": "40", "fifty": "50", "sixty": "60", "seventy": "70",
    "eighty": "80", "ninety": "90", "hundred": "100"
}

class TranscriptMerger:
    def __init__(self, whisper_path, assembly_path):
        self.whisper_path = whisper_path
        self.whisper_data = self._load_json(whisper_path)
        self.assembly_data = self._load_json(assembly_path)
        self.merged_transcript = []

    def _load_json(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def calculate_threshold(self, words):
        """Calculates Mean - 1 StdDev to determine low confidence threshold."""
        scores = [w['score'] for w in words if w.get('score') is not None]
        
        if not scores:
            return 0.0

        mean_score = statistics.mean(scores)
        std_dev = statistics.stdev(scores) if len(scores) > 1 else 0.0
        threshold = mean_score - std_dev
        
        print(f"Stats: Mean={mean_score:.3f}, StdDev={std_dev:.3f}, Threshold={threshold:.3f}")
        return threshold

    def preprocess_assembly(self):
        print("--- Processing AssemblyAI Data ---")
        raw_words = self.assembly_data.get('words', [])
        processed_words = []

        for w in raw_words:
            processed_words.append({
                'text': w['word'],
                'start': w['start_ms'] / 1000.0,
                'end': w['end_ms'] / 1000.0,
                'score': w['confidence'],
                'source': 'AssemblyAI'
            })

        threshold = self.calculate_threshold(processed_words)
        for w in processed_words:
            w['is_low_confidence'] = w['score'] < threshold
            
        return processed_words

    def preprocess_whisper(self):
        print("--- Processing WhisperX Data ---")
        segments = self.whisper_data.get('segments', [])
        flattened_words = []

        for seg in segments:
            speaker = seg.get('speaker', 'Unknown')
            seg_words = seg.get('words', [])
            last_end = seg.get('start', 0.0)
            seg_end = seg.get('end', last_end)

            # Collect words, estimating timestamps for any that whisperX couldn't align
            words_with_ts = []
            pending_no_ts = []

            for w in seg_words:
                if 'start' in w and 'end' in w:
                    # Flush any pending unaligned words into the gap before this word
                    if pending_no_ts:
                        gap_start = last_end
                        gap_end = w['start']
                        slot = (gap_end - gap_start) / (len(pending_no_ts) + 1)
                        for k, pw in enumerate(pending_no_ts):
                            pw['start'] = gap_start + slot * k
                            pw['end'] = gap_start + slot * (k + 1)
                        words_with_ts.extend(pending_no_ts)
                        pending_no_ts = []
                    last_end = w['end']
                    words_with_ts.append(w)
                else:
                    pending_no_ts.append(dict(w))

            # Flush any trailing unaligned words using remaining segment time
            if pending_no_ts:
                slot = (seg_end - last_end) / (len(pending_no_ts) + 1)
                for k, pw in enumerate(pending_no_ts):
                    pw['start'] = last_end + slot * k
                    pw['end'] = last_end + slot * (k + 1)
                words_with_ts.extend(pending_no_ts)

            for w in words_with_ts:
                score = w.get('score', 0.0)
                flattened_words.append({
                    'text': w['word'],
                    'start': w['start'],
                    'end': w['end'],
                    'score': score,
                    'speaker': speaker,
                    'source': 'WhisperX'
                })

        threshold = self.calculate_threshold(flattened_words)
        for w in flattened_words:
            w['is_low_confidence'] = w['score'] < threshold

        return flattened_words

    def get_overlap(self, w1, w2):
        start = max(w1['start'], w2['start'])
        end = min(w1['end'], w2['end'])
        return max(0, end - start)

    def normalize_text(self, text):
        """
        Strips punctuation, lowercases, and converts common number words to digits.
        Example: "Ninety," -> "90"
        """
        clean = text.translate(str.maketrans('', '', string.punctuation)).strip().lower()
        return NUMBER_MAP.get(clean, clean)

    def are_words_effectively_equal(self, w_text, a_text):
        """
        Checks if words are equal ignoring case, punctuation, and number formatting.
        Also accepts substring matches for compound tokens (e.g. 'HCT' in 'HCT160').
        """
        norm_w = self.normalize_text(w_text)
        norm_a = self.normalize_text(a_text)

        if norm_w == norm_a:
            return True
            
        # Substring/Compound check for length > 1 (Avoid matching "a" to "apple")
        if len(norm_w) >= 3 and len(norm_a) >= 3:
            if norm_w in norm_a or norm_a in norm_w:
                return True
                
        return False

    def align_streams(self, whisper_words, assembly_words):
        """
        Aligns Assembly words to Whisper words based on overlap + textual similarity score.
        """
        aligned_pairs = []
        assembly_idx = 0
        n_assembly = len(assembly_words)
        used_indices = set()  # track matched assembly words to prevent reuse

        for w_word in whisper_words:
            best_match = None
            best_score = 0

            # Look back slightly (5 words) then forward to handle slight desyncs
            search_start_idx = max(0, assembly_idx - 5)

            # Increased window to 150 to handle long letter-spelling / numeric sections
            search_end_idx = min(n_assembly, search_start_idx + 150)

            best_idx = assembly_idx

            best_text_match = None
            best_text_idx = -1
            best_overlap_match = None
            best_overlap_score = 0
            best_overlap_idx = assembly_idx

            for i in range(search_start_idx, search_end_idx):
                if i in used_indices:
                    continue

                a_word = assembly_words[i]
                text_match = self.are_words_effectively_equal(w_word['text'], a_word['text'])
                overlap = self.get_overlap(w_word, a_word)

                if text_match and overlap > 0:
                    # Perfect: same word AND same timestamp — can't do better
                    best_match = a_word
                    best_idx = i
                    break

                if text_match and best_text_match is None:
                    # Same word but timestamps drifted apart — still a valid match,
                    # but cap drift at 10s to prevent matching words from a completely
                    # different part of the transcript (e.g. second mention of a phrase)
                    time_diff = abs(a_word['start'] - w_word['start'])
                    if time_diff < 10.0:
                        best_text_match = a_word
                        best_text_idx = i

                if overlap > 0 and overlap > best_overlap_score:
                    # Timestamps align but word text differs — last resort
                    best_overlap_score = overlap
                    best_overlap_match = a_word
                    best_overlap_idx = i

            if best_match is None:
                # Prefer text match over overlap-only: timestamp drift is common,
                # but both transcribers transcribed the correct words
                if best_text_match is not None:
                    best_match = best_text_match
                    best_idx = best_text_idx
                elif best_overlap_match is not None:
                    best_match = best_overlap_match
                    best_idx = best_overlap_idx

            if best_match:
                used_indices.add(best_idx)
                assembly_idx = best_idx + 1

            aligned_pairs.append((w_word, best_match))
        return aligned_pairs

    def clean_llm_response(self, raw_response, option_a, option_b):
        """
        Aggressively cleans the LLM response.
        """
        norm_resp = self.normalize_text(raw_response)
        norm_a = self.normalize_text(option_a)
        norm_b = self.normalize_text(option_b)

        # 1. Exact clean match
        if norm_a in norm_resp and len(norm_resp) < len(norm_a) + 10:
            return option_a
        if norm_b in norm_resp and len(norm_resp) < len(norm_b) + 10:
            return option_b

        # 2. Regex artifact removal
        clean = re.sub(r'\[.*?\]', '', raw_response)
        clean = re.sub(r'(Option [AB]:?)', '', clean, flags=re.IGNORECASE)
        clean = clean.replace('"', '').replace("'", "").strip()
        
        if not clean:
            return option_a
        return clean

    def consult_llm(self, context_sentence, option_a, option_b):
        prompt = (
            f"You are a text cleaner. Pick the correct word based on context.\n"
            f"Context: \"...{context_sentence}...\"\n"
            f"Choice 1: \"{option_a}\"\n"
            f"Choice 2: \"{option_b}\"\n"
            f"Instruction: RETURN ONLY THE CHOSEN WORD TEXT. Do not write 'Choice 1', brackets, or punctuation."
        )

        try:
            payload = {
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False
            }
            response = requests.post(OLLAMA_URL, json=payload)
            response.raise_for_status()
            raw_result = response.json().get('response', '').strip()
            
            return self.clean_llm_response(raw_result, option_a, option_b)
            
        except Exception as e:
            print(f"LLM Error: {e}. Defaulting to Whisper option.")
            return option_a

    def resolve_conflicts(self, pairs, assembly_words=None):
        final_transcript = []
        # Pre-extract all whisper texts for occurrence counting
        all_w_texts = [p[0]['text'] for p in pairs]

        for i, (w_word, a_word) in enumerate(pairs):
            
            w_text = w_word['text']
            w_low = w_word['is_low_confidence']
            
            result_word = {
                "text": w_text,
                "speaker": w_word['speaker'],
                "flagged": False,
                "start": w_word.get('start', 0),
                "end": w_word.get('end', 0),
                "a_start": None,
                "a_end": None,
            }

            if not a_word:
                if w_low:
                    result_word['flagged'] = True
                # Fallback: find the Nth occurrence in assembly (same order as whisper)
                # so repeated words like "calling" match the correct instance.
                if assembly_words:
                    w_text = w_word['text']
                    occurrence = sum(
                        1 for j in range(i)
                        if self.are_words_effectively_equal(all_w_texts[j], w_text)
                    )
                    n = 0
                    matched = None
                    for aw in assembly_words:
                        if self.are_words_effectively_equal(aw['text'], w_text):
                            if n == occurrence:
                                matched = aw
                                break
                            n += 1
                    # If assembly has fewer occurrences, fall back to closest by time
                    if matched is None:
                        best_diff = float('inf')
                        for aw in assembly_words:
                            if self.are_words_effectively_equal(aw['text'], w_text):
                                diff = abs(aw.get('start', 0) - w_word.get('start', 0))
                                if diff < best_diff:
                                    best_diff = diff
                                    matched = aw
                    if matched:
                        result_word['a_start'] = matched.get('start')
                        result_word['a_end'] = matched.get('end')
                final_transcript.append(result_word)
                continue

            result_word['a_start'] = a_word.get('start', None)
            result_word['a_end'] = a_word.get('end', None)

            a_text = a_word['text']
            a_low = a_word['is_low_confidence']
            
            match = self.are_words_effectively_equal(w_text, a_text)

            if match:
                # MATCH LOGIC (Pick high confidence source)
                if w_low and not a_low:
                    result_word['text'] = a_text 
                elif a_low and not w_low:
                    result_word['text'] = w_text 
                else:
                    result_word['text'] = w_text 

                if w_low and a_low:
                    result_word['flagged'] = True
                    
            else:
                # MISMATCH LOGIC
                
                # Case 5: One High / One Low -> Trust High
                if w_low != a_low:
                    if w_low:
                        result_word['text'] = a_text
                    else:
                        result_word['text'] = w_text
                
                # Case 4: Ambiguous (Both High or Both Low)
                else:
                    # --- NEW: STUTTER / LOOKAHEAD CHECK ---
                    resolved_by_lookahead = False
                    
                    # Ensure we have a next word to peek at
                    if i + 1 < len(pairs):
                        next_w_word = pairs[i+1][0]
                        next_text = next_w_word['text'] # Whisper is master sequence
                        
                        matches_whisper_next = self.are_words_effectively_equal(w_text, next_text)
                        matches_assembly_next = self.are_words_effectively_equal(a_text, next_text)

                        # Rule: If one option replicates the next word, but the other doesn't,
                        # choose the one that DOESN'T duplicate.
                        if matches_whisper_next and not matches_assembly_next:
                            result_word['text'] = a_text
                            resolved_by_lookahead = True
                            # We flag it as it was a conflict, but resolved heuristically
                            result_word['flagged'] = True 
                            
                        elif matches_assembly_next and not matches_whisper_next:
                            result_word['text'] = w_text
                            resolved_by_lookahead = True
                            result_word['flagged'] = True

                    if resolved_by_lookahead:
                        print(f"Stutter detected: '{w_text}' vs '{a_text}'. Auto-selected '{result_word['text']}' based on next word '{next_text}'.")
                    
                    else:
                        # Fallback to LLM if stutter check didn't resolve it
                        print(f"Invoking LLM for ambiguity: '{w_text}' vs '{a_text}'")
                        
                        prev_context = " ".join([w['text'] for w in final_transcript[-3:]])
                        next_context = " ".join([p[0]['text'] for p in pairs[i+1:i+4]])
                        full_context = f"{prev_context} [TARGET] {next_context}"

                        chosen_word = self.consult_llm(full_context, w_text, a_text)
                        
                        result_word['text'] = chosen_word
                        result_word['flagged'] = True 

            final_transcript.append(result_word)

        return final_transcript

    def format_output(self, resolved_words, output_file):
        if not resolved_words:
            return

        with open(output_file, 'w', encoding='utf-8') as f:
            current_speaker = None
            current_line = []

            for word in resolved_words:
                speaker = word['speaker']
                text = word['text']
                
                if word['flagged']:
                    text = f"[{text}]*"

                if speaker != current_speaker:
                    if current_speaker is not None:
                        f.write(f"{current_speaker}: {' '.join(current_line)}\n\n")
                    
                    current_speaker = speaker
                    current_line = []

                current_line.append(text)

            if current_speaker and current_line:
                f.write(f"{current_speaker}: {' '.join(current_line)}\n")
        
        print(f"Successfully saved merged transcript to {output_file}")

    @staticmethod
    def build_timestamped_transcript(resolved_words):
        """Build a readable transcript with start-end timestamps per speaker turn."""
        lines = []
        current_speaker = None
        current_start = 0
        current_end = 0
        current_words = []

        for word in resolved_words:
            speaker = word['speaker']
            text = word['text']
            start = word.get('start', 0)
            end = word.get('end', 0)

            if speaker != current_speaker:
                if current_speaker is not None and current_words:
                    ts = f"[{TranscriptMerger._fmt_ts(current_start)} - {TranscriptMerger._fmt_ts(current_end)}]"
                    lines.append(f"{ts} {current_speaker}: {' '.join(current_words)}")
                current_speaker = speaker
                current_start = start
                current_words = []

            current_end = end
            current_words.append(text)

        if current_speaker and current_words:
            ts = f"[{TranscriptMerger._fmt_ts(current_start)} - {TranscriptMerger._fmt_ts(current_end)}]"
            lines.append(f"{ts} {current_speaker}: {' '.join(current_words)}")

        return "\n".join(lines)

    @staticmethod
    def _fmt_ts(seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _fmt_duration(self, seconds):
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        if h > 0:
            return f"{h}h {m}m {s}.{ms:03d}s"
        return f"{m}m {s}.{ms:03d}s"

    def generate_summary(self, resolved_words, keywords=None, patient_name=None):
        """Call Ollama to produce a condensed summary and topic chapters."""
        timestamped = self.build_timestamped_transcript(resolved_words)

        total_start = resolved_words[0].get('start', 0) if resolved_words else 0
        total_end = resolved_words[-1].get('end', 0) if resolved_words else 0
        duration = self._fmt_duration(total_end - total_start)

        keywords_block = ""
        if keywords:
            keywords_block = f"\nKEY TERMS PROVIDED BY DOCTOR (treat these as authoritative — prefer them when the transcript is ambiguous): {keywords}\n"
        if patient_name:
            keywords_block += f"PATIENT NAME: {patient_name}\n"

        prompt = f"""You are a medical transcription analyst. Analyze the transcript below and produce a structured report.

RECORDING DURATION: {duration}
{keywords_block}
TRANSCRIPT:
{timestamped}

STRICT OUTPUT RULES:
1. Always include === SUMMARY ===, === DURATION ===, and === CHAPTERS ===.
2. CLINICAL NOTE RULE — CRITICAL: Only include === CLINICAL NOTE === if this is clearly a medical or clinical encounter (clinic visit, phone prescription call, telehealth, etc.). If it is NOT medical (e.g. casual conversation, music, personal story, meeting), DO NOT include === CLINICAL NOTE === at all. Not even with Unknown values. Leave it out completely.
3. Inside CLINICAL NOTE: omit any field where the value is not known or not mentioned. Do not write "Unknown", "N/A", "Not stated", or similar — just skip that line.
4. For CHAPTERS: copy timestamps EXACTLY from the transcript above (format: [HH:MM:SS - HH:MM:SS]). Do not make up timestamps.
5. ICD-10 CODING: This report will be used downstream for ICD-10-CM coding. In CLINICAL NOTE, use precise medical terminology and include specificity details wherever the transcript supports them — laterality (left/right/bilateral), acuity (acute/chronic), severity, etiology, complications, and stage. In CHAPTERS, flag any segment that contains a diagnosable condition, procedure, or prescription with a brief clinical label.

Produce output in EXACTLY this format, no extra commentary:

=== SUMMARY ===
[1-6 sentences summarizing the recording.]

=== DURATION ===
Total recording time: {duration}

=== CLINICAL NOTE ===
[ONLY include this section if the recording is a medical/clinical encounter. Otherwise omit entirely.]
Patient: [full name if stated]
DOB/Age: [if stated]
Date/Time: [if stated]
Encounter Type: [Telehealth / ED / Clinic / Phone / etc.]
Chief Complaint: [reason for the call/visit]
Visit Reason: [new rx / refill / follow-up / etc.]
Medications Started/Changed: [drug, dose, sig, qty, refills]
HPI: [only if discussed]
PMH/Meds/Allergies: [only if discussed]
Vitals/Exam: [only if discussed]
Labs/Imaging: [only if discussed]
Assessment: [only if discussed]
Active Problems: [only if discussed]
Orders/Investigations: [only if discussed]
Procedures Done: [only if discussed]
Follow-up Instructions: [only if discussed]
Red Flags Given: [only if discussed]
Disposition: [only if discussed]
Patient Agreement/Concerns: [only if discussed]
Billing Items: [only if discussed]

=== CHAPTERS ===
[HH:MM:SS - HH:MM:SS] Chapter Title: one sentence description
[HH:MM:SS - HH:MM:SS] Chapter Title: one sentence description
"""

        try:
            response = requests.post(
                OLLAMA_URL,
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False}
            )
            response.raise_for_status()
            return response.json().get('response', '').strip()
        except Exception as e:
            return f"[Summary generation failed: {e}]"

    def run(self):
        a_words = self.preprocess_assembly()
        w_words = self.preprocess_whisper()

        print("--- Aligning Transcripts ---")
        pairs = self.align_streams(w_words, a_words)
        print(f"Aligned {len(pairs)} word pairs.")

        print("--- Resolving Conflicts ---")
        final_words = self.resolve_conflicts(pairs)

        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs", "kevin")
        os.makedirs(out_dir, exist_ok=True)

        # Derive base name from whisper input file
        base_name = os.path.splitext(os.path.basename(self.whisper_path))[0].replace('_full_output', '')

        self.format_output(final_words, os.path.join(out_dir, f"{base_name}_transcript.txt"))

        print("--- Generating Summary ---")
        summary = self.generate_summary(final_words)
        summary_path = os.path.join(out_dir, f"{base_name}_summary.txt")
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(summary)
        print(f"Summary saved to {summary_path}")



def merge_for_api(whisper_path, assembly_path, keywords=None, patient_name=None):
    """API-facing entry point: runs full pipeline and returns (words, summary, final_words).

    final_words is the raw resolved-word list (with speaker/timestamp metadata),
    returned so callers can run additional analysis (e.g. extract_clinical_concepts)
    without re-running the merge.
    """
    merger = TranscriptMerger(whisper_path, assembly_path)
    a_words = merger.preprocess_assembly()
    w_words = merger.preprocess_whisper()
    pairs = merger.align_streams(w_words, a_words)
    final_words = merger.resolve_conflicts(pairs, a_words)

    words = [
        {
            "text": w["text"],
            "speaker": w["speaker"],
            "flagged": w["flagged"],
            "start": w.get("start", 0),
            "end": w.get("end", 0),
            "a_start": w.get("a_start"),
            "a_end": w.get("a_end"),
        }
        for w in final_words
    ]

    summary = merger.generate_summary(final_words, keywords=keywords, patient_name=patient_name)
    return words, summary, final_words


def extract_clinical_concepts(resolved_words, keywords=None, patient_name=None):
    """
    Extract structured, machine-readable clinical concepts from a resolved transcript.

    Unlike generate_summary (which produces a human-readable clinical note for the UI),
    this returns a dict of short, self-contained phrases meant to be embedded for a
    downstream semantic-retrieval system. Schema (all keys always present):

        {
          "symptoms": [...],
          "diagnoses_mentioned": [...],
          "medications_discussed": [...],
          "procedures_ordered": [...],
          "history_relevant": [...],
          "vitals_exam_findings": [...]
        }

    Returns all-empty lists for a non-medical encounter or on any failure
    (never raises).
    """
    empty = {
        "symptoms": [],
        "diagnoses_mentioned": [],
        "medications_discussed": [],
        "procedures_ordered": [],
        "history_relevant": [],
        "vitals_exam_findings": [],
    }

    if not resolved_words:
        return empty

    # Reuse the exact timestamped transcript format that generate_summary feeds Ollama.
    timestamped = TranscriptMerger.build_timestamped_transcript(resolved_words)

    keywords_block = ""
    if keywords:
        keywords_block += f"\nKEY TERMS PROVIDED BY DOCTOR (authoritative — prefer them when the transcript is ambiguous): {keywords}\n"
    if patient_name:
        keywords_block += f"PATIENT NAME: {patient_name}\n"

    prompt = f"""You are a clinical information extractor. Read the transcript below and extract structured clinical concepts for a downstream search system.
{keywords_block}
TRANSCRIPT:
{timestamped}

EXTRACTION RULES:
1. Extract concepts ONLY from what is EXPLICITLY stated in the transcript. Do NOT infer unstated conditions, diagnoses, or findings.
2. Each item must be a short, COMPLETE clinical concept — never a single bare word. Bad: "cough". Good: "productive cough for 5 days".
3. Each phrase must be self-contained enough to stand alone when read out of context — it will be embedded for semantic search.
4. For medications, include drug + dose + frequency whenever stated (e.g. "amoxicillin 500mg three times daily").
5. Empty lists are valid. If a category has nothing explicitly stated, return an empty list for it.
6. If this is NOT a medical encounter, return all empty lists.

Field definitions:
- "symptoms": patient-reported symptoms and complaints
- "diagnoses_mentioned": conditions named or strongly implied as diagnoses
- "medications_discussed": drug + dose + frequency if available
- "procedures_ordered": labs, imaging, referrals ordered or discussed
- "history_relevant": past-medical-history items relevant to this encounter
- "vitals_exam_findings": vitals or physical exam findings if mentioned

Return ONLY valid JSON matching EXACTLY this schema — no prose, no markdown fences, no commentary:
{{
  "symptoms": [],
  "diagnoses_mentioned": [],
  "medications_discussed": [],
  "procedures_ordered": [],
  "history_relevant": [],
  "vitals_exam_findings": []
}}
"""

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0},  # minimize run-to-run concept variance
            },
            timeout=60,
        )
        response.raise_for_status()
        raw = response.json().get('response', '').strip()
        # Same JSON-extraction pattern as main.py's ICD suggestion, but for a JSON
        # object: take everything from the first '{' to the last '}'.
        start = raw.find('{')
        end = raw.rfind('}') + 1
        if start == -1 or end <= start:
            return empty
        parsed = json.loads(raw[start:end])
        if not isinstance(parsed, dict):
            return empty
        # Coerce to the exact schema: every key present, each value a list of
        # non-empty trimmed strings.
        result = {}
        for key in empty:
            value = parsed.get(key, [])
            if not isinstance(value, list):
                result[key] = []
                continue
            result[key] = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        return result
    except Exception as e:
        print(f"Concept extraction failed: {e}")
        return empty


def _normalize_word(text: str) -> str:
    return text.lower().translate(str.maketrans('', '', string.punctuation)).strip()


def _find_phrase_in_words(words: list, phrase: str) -> list:
    """
    Find word indices in words[] where the given phrase appears.
    Exact word-by-word match only (after stripping punctuation and lowercasing).
    Returns [] if not found — no fuzzy fallback to prevent false positives.
    """
    phrase_tokens = [_normalize_word(t) for t in phrase.split() if t.strip()]
    if not phrase_tokens:
        return []
    n = len(phrase_tokens)

    for i in range(len(words) - n + 1):
        if all(_normalize_word(words[i + j]['text']) == phrase_tokens[j] for j in range(n)):
            return list(range(i, i + n))

    return []


# Keywords that indicate a summary section may contain ICD-10-codeable content
_ICD_KEYWORDS = {
    'patient', 'diagnosis', 'diagnose', 'condition', 'disease', 'disorder',
    'symptom', 'complaint', 'pain', 'medication', 'prescription', 'drug',
    'treatment', 'procedure', 'surgery', 'exam', 'examination', 'assessment',
    'allergy', 'infection', 'injury', 'fracture', 'chronic', 'acute',
    'diabetes', 'hypertension', 'asthma', 'encounter', 'visit', 'follow',
    'refill', 'rx', 'vitals', 'labs', 'imaging', 'hpi', 'pmh', 'chief',
    'complaint', 'presenting', 'history', 'findings', 'result', 'blood',
    'pressure', 'glucose', 'insulin', 'dose', 'milligram', 'mg', 'tablet',
}


def _parse_summary_sections(summary: str) -> list:
    """
    Parse the summary string into a list of (name, body) tuples.
    Preserves order. CHAPTERS section is split into individual timestamped items.
    """
    sections = []
    pattern = re.compile(r'===\s*(.+?)\s*===([\s\S]*?)(?====|$)')
    for m in pattern.finditer(summary):
        name = m.group(1).strip().upper()
        body = m.group(2).strip()
        if not body:
            continue
        if name == 'CHAPTERS':
            # Treat each chapter line as its own mini-section
            for line in body.splitlines():
                line = line.strip()
                if line:
                    sections.append(('CHAPTER', line))
        else:
            sections.append((name, body))
    return sections


def _is_section_icd_relevant(name: str, body: str) -> bool:
    """
    Returns True if the section likely contains ICD-10 codeable content.
    Uses a fast keyword heuristic — no LLM call needed for screening.
    """
    # CLINICAL NOTE is always relevant when present — most structured medical content
    if 'CLINICAL' in name or 'NOTE' in name:
        return True
    # DURATION and individual CHAPTER lines are never sent to agents.
    # Chapter lines are one-sentence timestamp labels (e.g. "[00:01:37] Echo results discussion.")
    # — they are organizational markers, not clinical findings. Feeding them to an agent
    # produces hallucinated codes because the LLM has almost no real content to work with.
    if name in ('DURATION', 'CHAPTER'):
        return False
    # SUMMARY section: check for medical keywords
    lower = body.lower()
    return any(kw in lower for kw in _ICD_KEYWORDS)


def _ts_to_secs(ts: str) -> float:
    """Convert HH:MM:SS or MM:SS timestamp string to seconds."""
    parts = ts.strip().split(':')
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
    except ValueError:
        pass
    return 0.0


def _get_chapter_transcript(chapter_line: str, words: list) -> str:
    """
    Parse the timestamp from a chapter line (e.g. '[00:01:37 - 00:02:14] Echo results...')
    and return the actual spoken words from that time window as a readable transcript string.
    Returns '' if no timestamp found or no words fall in the range.
    """
    m = re.match(r'\[(\d{1,2}:\d{2}:\d{2})\s*[-\u2013\u2014]\s*(\d{1,2}:\d{2}:\d{2})\]', chapter_line)
    if not m:
        return ''

    start_sec = _ts_to_secs(m.group(1))
    end_sec = _ts_to_secs(m.group(2))

    slice_words = [w for w in words if w.get('start', 0) >= start_sec and w.get('end', 0) <= end_sec + 0.5]
    if not slice_words:
        return ''

    parts = []
    current_speaker = None
    current_chunk = []
    for w in slice_words:
        speaker = w.get('speaker', 'Speaker')
        if speaker != current_speaker:
            if current_speaker and current_chunk:
                parts.append(f"{current_speaker}: {' '.join(current_chunk)}")
            current_speaker = speaker
            current_chunk = []
        current_chunk.append(w['text'])
    if current_speaker and current_chunk:
        parts.append(f"{current_speaker}: {' '.join(current_chunk)}")

    return '\n'.join(parts)


def _build_feedback_block(feedback_items: list) -> str:
    if not feedback_items:
        return ""
    lines = []
    for fb in feedback_items:
        mark = "CONFIRMED" if fb.get('correct') else "REJECTED"
        ctx = f' (context: "{fb["context"]}")' if fb.get('context') else ''
        lines.append(f'{mark}: Code {fb["code"]} for "{fb["phrase"]}"{ctx}')
    return "\nCLINICIAN FEEDBACK (use to improve accuracy):\n" + "\n".join(lines)


def _extract_medical_phrases(transcript_text: str) -> list[str]:
    """
    Pass 1 of two-pass ICD suggestion.
    Ask the LLM to extract verbatim medical phrases from the raw transcript.
    Returns a list of exact quoted strings that appear in transcript_text.
    No code determination happens here — just phrase extraction.
    """
    prompt = (
        "You are a medical scribe. Your ONLY job is to find and copy verbatim phrases "
        "from the transcript below that describe a medical condition, symptom, sign, "
        "medication, procedure, or diagnosis.\n\n"
        "TRANSCRIPT:\n"
        f"{transcript_text}\n\n"
        "RULES:\n"
        "1. Copy each phrase EXACTLY as it appears in the transcript — letter for letter.\n"
        "2. Only include phrases that have clear medical significance.\n"
        "3. Do NOT include scheduling talk, greetings, or non-clinical conversation.\n"
        "4. Do NOT paraphrase, translate, or use medical jargon — use the speaker's exact words.\n"
        "5. Each phrase should be 2-10 words long.\n"
        "6. If nothing medically significant appears, return [].\n\n"
        'Return ONLY a valid JSON array of strings. Example:\n'
        '["shortness of breath", "slight murmur across the valve", "blood pressure is elevated"]\n'
        'If nothing applies: []'
    )
    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=60,
        )
        resp.raise_for_status()
        raw = resp.json().get('response', '[]').strip()
        start = raw.find('[')
        end = raw.rfind(']') + 1
        if start == -1 or end <= start:
            return []
        phrases = json.loads(raw[start:end])
        if not isinstance(phrases, list):
            return []
        # Keep only strings that actually appear verbatim in the transcript
        transcript_lower = transcript_text.lower()
        verified = []
        for p in phrases:
            if not isinstance(p, str) or not p.strip():
                continue
            if p.strip().lower() in transcript_lower:
                verified.append(p.strip())
            else:
                print(f"  Pass1: rejected non-verbatim phrase: \"{p}\"")
        return verified
    except Exception as e:
        print(f"  Pass1 error: {e}")
        return []


def _map_phrases_to_codes(
    phrases: list[str],
    candidate_codes: list,
    feedback_items: list,
    max_codes: int = 6,
) -> list[dict]:
    """
    Pass 2 of two-pass ICD suggestion.
    Given a locked list of verbatim phrases, map each to the most specific ICD-10-CM code.
    Returns [{code, evidence_phrase}].
    """
    if not phrases:
        return []

    if candidate_codes:
        code_lines = "\n".join(f"{c['code']} - {c['description']}" for c in candidate_codes)
        candidate_block = f"CANDIDATE ICD-10-CM CODES (only use codes from this list):\n{code_lines}\n\n"
    else:
        candidate_block = "Use your full ICD-10-CM knowledge.\n\n"

    feedback_block = _build_feedback_block(feedback_items)

    phrase_list = "\n".join(f'- "{p}"' for p in phrases)

    prompt = (
        "You are an ICD-10-CM medical coding specialist.\n\n"
        "A scribe has extracted the following verbatim phrases from a patient encounter transcript:\n"
        f"{phrase_list}\n\n"
        f"{candidate_block}"
        f"{feedback_block}\n"
        "TASK: For each phrase that maps to an ICD-10-CM code, return that mapping.\n"
        "RULES:\n"
        "- Only map phrases that clearly describe a codeable medical condition, symptom, "
        "sign, medication, or procedure.\n"
        "- Use the most specific code available (prefer 5-7 character codes over 3-character categories).\n"
        "- One phrase can only map to one code. Multiple phrases can share a code.\n"
        "- If a phrase does NOT have a clear ICD-10 mapping, skip it.\n"
        f"- Return at most {max_codes} codes total.\n"
        "- Return ONLY a valid JSON array, no explanation.\n\n"
        'FORMAT: [{"code": "R06.00", "phrase": "shortness of breath"}]\n'
        'Example: phrase "slight murmur across the valve" → {"code": "R01.1", "phrase": "slight murmur across the valve"}\n'
        'If nothing maps: []'
    )

    try:
        resp = requests.post(
            OLLAMA_URL,
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=60,
        )
        resp.raise_for_status()
        raw = resp.json().get('response', '[]').strip()
        start = raw.find('[')
        end = raw.rfind(']') + 1
        if start == -1 or end <= start:
            return []
        mappings = json.loads(raw[start:end])
        if not isinstance(mappings, list):
            return []
        result = []
        for m in mappings:
            if not isinstance(m, dict):
                continue
            code = m.get('code', '').strip().upper()
            phrase = m.get('phrase', '').strip()
            if code and phrase:
                result.append({'code': code, 'phrase': phrase})
        return result
    except Exception as e:
        print(f"  Pass2 error: {e}")
        return []


def _merge_suggestions(all_raw: list, candidate_desc_map: dict, validate_fn) -> list:
    """
    Deduplicate suggestions by code, merging evidence lists.
    Validates each code and filters unknowns when a candidate list is active.
    """
    merged: dict = {}
    has_candidates = bool(candidate_desc_map)

    for s in all_raw:
        if not isinstance(s, dict):
            continue
        code = s.get('code', '').strip().upper()
        if not code:
            continue

        desc = validate_fn(code)
        if desc is None:
            desc = candidate_desc_map.get(code)
        if desc is None and has_candidates:
            continue  # Outside requested range — skip
        if desc is None:
            desc = code

        evidence = [
            ev for ev in s.get('evidence', [])
            if isinstance(ev, dict) and ev.get('phrase', '').strip()
        ]
        if not evidence:
            continue

        if code not in merged:
            merged[code] = {'code': code, 'description': desc, 'evidence': []}
        # Add unique phrases only
        existing_phrases = {e['phrase'] for e in merged[code]['evidence']}
        for ev in evidence:
            if ev['phrase'] not in existing_phrases:
                merged[code]['evidence'].append({'phrase': ev['phrase']})
                existing_phrases.add(ev['phrase'])

    return list(merged.values())


def suggest_icd_codes(
    words: list,
    summary: str,
    code_range: str = "",
    feedback_path: str = None,
    max_suggestions: int = 10,
) -> list:
    """
    Suggest ICD-10-CM codes by scanning the structured clinical summary.

    Pipeline:
      1. Parse summary into named sections (SUMMARY, CLINICAL NOTE, each CHAPTER)
      2. Screen each section with a keyword heuristic for ICD relevance
      3. Deploy a focused LLM extraction agent to every flagged section
      4. Merge + deduplicate results across sections
      5. Match evidence phrases back to word indices in the transcript

    Returns list of:
    {
        "code": "E11.9",
        "description": "Type 2 diabetes mellitus without complications",
        "evidence": [{"phrase": "blood sugar levels", "word_indices": [12, 13, 14]}]
    }
    """
    try:
        from icd10_utils import get_codes_for_range_input, validate_and_describe
    except ImportError:
        def get_codes_for_range_input(*_a, **_k): return []
        def validate_and_describe(_c): return None

    if not summary or not summary.strip():
        print("ICD suggestion: no summary provided, skipping.")
        return []

    # Load candidate codes and feedback
    candidate_codes = get_codes_for_range_input(code_range) if code_range else []
    candidate_desc_map = {c['code']: c['description'] for c in candidate_codes}

    feedback_items = []
    if feedback_path and os.path.exists(feedback_path):
        try:
            with open(feedback_path, 'r', encoding='utf-8') as f:
                all_fb = json.load(f)
            feedback_items = all_fb[-20:] if len(all_fb) > 20 else all_fb
        except Exception:
            pass

    # Parse summary into sections — only CHAPTER sections are used.
    # CLINICAL NOTE and SUMMARY sections are skipped entirely: they contain paraphrased
    # text produced by the LLM, not verbatim spoken words, which causes evidence
    # to cite summaries rather than what the patient/doctor actually said.
    sections = _parse_summary_sections(summary)
    chapter_slices = []
    for name, body in sections:
        if name != 'CHAPTER':
            continue
        transcript_slice = _get_chapter_transcript(body, words)
        if not transcript_slice:
            print(f"  Skipping chapter (no words in range): {body[:60]}")
            continue
        chapter_slices.append((f"CHAPTER [{body[:50]}]", transcript_slice))

    print(f"ICD pipeline: {len(sections)} sections parsed, {len(chapter_slices)} chapter(s) with transcript data")

    # Two-pass extraction per chapter:
    #   Pass 1 — extract verbatim medical phrases from spoken transcript only
    #   Pass 2 — map locked-in phrases to ICD-10-CM codes
    # This prevents motivated reasoning (code-first → hunt for evidence).
    all_raw = []
    for label, transcript_slice in chapter_slices:
        print(f"  → Pass 1 (phrase extraction): [{label}]")
        phrases = _extract_medical_phrases(transcript_slice)
        print(f"    Extracted {len(phrases)} phrase(s): {phrases}")
        if not phrases:
            continue
        print(f"  → Pass 2 (code mapping): [{label}]")
        mappings = _map_phrases_to_codes(phrases, candidate_codes, feedback_items)
        print(f"    Mapped {len(mappings)} code(s)")
        # Convert to the format _merge_suggestions expects
        for m in mappings:
            all_raw.append({
                'code': m['code'],
                'evidence': [{'phrase': m['phrase']}],
            })

    # Merge duplicates, validate codes
    merged = _merge_suggestions(all_raw, candidate_desc_map, validate_and_describe)
    print(f"ICD pipeline: {len(merged)} unique code(s) after deduplication")

    # Match evidence phrases to word indices for transcript highlighting
    results = []
    for s in merged[:max_suggestions]:
        evidence_list = []
        for ev in s['evidence']:
            indices = _find_phrase_in_words(words, ev['phrase'])
            evidence_list.append({'phrase': ev['phrase'], 'word_indices': indices})
        results.append({
            'code': s['code'],
            'description': s['description'],
            'evidence': evidence_list,
        })

    return results


if __name__ == "__main__":
    # Check if user provided command line arguments
    if len(sys.argv) == 3:
        WHISPER_FILE = sys.argv[1]
        ASSEMBLY_FILE = sys.argv[2]
        print(f"Using provided files:\n  Whisper: {WHISPER_FILE}\n  Assembly: {ASSEMBLY_FILE}")
    else:
        # Fallback to defaults if no arguments provided
        print("No arguments provided. Using default filenames.")
        WHISPER_FILE = "whisperX_confidences.json"
        ASSEMBLY_FILE = "assemblyAI_confidences.json"

    if not os.path.exists(WHISPER_FILE) or not os.path.exists(ASSEMBLY_FILE):
        print(f"Error: One or both input files not found:\n  {WHISPER_FILE}\n  {ASSEMBLY_FILE}")
    else:
        merger = TranscriptMerger(WHISPER_FILE, ASSEMBLY_FILE)
        merger.run()