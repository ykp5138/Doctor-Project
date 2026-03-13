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

    def build_timestamped_transcript(self, resolved_words):
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
                    ts = f"[{self._fmt_ts(current_start)} - {self._fmt_ts(current_end)}]"
                    lines.append(f"{ts} {current_speaker}: {' '.join(current_words)}")
                current_speaker = speaker
                current_start = start
                current_words = []

            current_end = end
            current_words.append(text)

        if current_speaker and current_words:
            ts = f"[{self._fmt_ts(current_start)} - {self._fmt_ts(current_end)}]"
            lines.append(f"{ts} {current_speaker}: {' '.join(current_words)}")

        return "\n".join(lines)

    def _fmt_ts(self, seconds):
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
    """API-facing entry point: runs full pipeline and returns (words, summary)."""
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
    return words, summary


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