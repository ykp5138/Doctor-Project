import json
import numpy as np
import difflib
import ollama
import re
from typing import List, Dict, Any

class Kevin:
    def __init__(self, llm_model: str = "llama3"):
        self.llm_model = llm_model
        # Text Markers (Only used for TXT output)
        self.MARKER_INFERRED_START = "[LOW CONFIDENCE (Inferred): "
        self.MARKER_INFERRED_END = "]"
        self.MARKER_LOW_START = "[LOW CONFIDENCE: "
        self.MARKER_LOW_END = "]"

    def _load_json(self, file_path: str) -> List[Dict[str, Any]]:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('words', [])

    def _calculate_threshold(self, words: List[Dict[str, Any]]) -> float:
        confidences = [w.get('confidence', 0.0) for w in words if w.get('confidence') is not None]
        if not confidences: return 0.5
        mean_val = np.mean(confidences)
        std_val = np.std(confidences)
        threshold = mean_val - std_val
        print(f"Stats: Mean={mean_val:.4f}, Std={std_val:.4f}, Threshold={threshold:.4f}")
        return threshold

    def _is_regular(self, word_obj: Dict[str, Any], threshold: float) -> bool:
        return word_obj.get('confidence', 0.0) >= threshold

    def _clean_llm_output(self, text: str) -> str:
        clean = text.strip().strip('"').strip("'")
        patterns = [
            r"^here is the .*?:", r"^the correct text is:?", r"^the missing word is:?",
            r"^i infer that:?", r"^based on the context,?:?", r"^option [ab] is correct:?",
        ]
        for p in patterns:
            clean = re.sub(p, "", clean, flags=re.IGNORECASE).strip()
        if "\n" in clean:
            clean = clean.split("\n")[0]
        return clean

    def _remove_overlap(self, inferred_text: str, next_word: str) -> str:
        if not next_word or not inferred_text: return inferred_text
        inferred_clean = inferred_text.strip().lower()
        next_clean = next_word.strip().lower()
        if inferred_clean.endswith(next_clean):
            return inferred_text[:-(len(next_word))].strip()
        return inferred_text

    def _infer_with_llm(self, context_pre: str, context_post: str, option_a: str, option_b: str) -> str:
        system_prompt = (
            "You are a strict text completion engine. You are NOT a chatbot. "
            "You receive context and conflicting options. "
            "You output ONLY the missing text string. "
            "Do NOT speak to the user. Do NOT explain your choice."
        )
        user_prompt = (
            f"EXAMPLE INPUT:\nPre: 'Hello my name'\nPost: 'is Kevin'\nOpA: 'is'\nOpB: 'apple'\n"
            f"EXAMPLE OUTPUT: is\n\nREAL TASK:\n"
            f"Context Pre: \"...{context_pre}\"\nContext Post: \"{context_post}...\"\n"
            f"Option A: \"{option_a}\"\nOption B: \"{option_b}\"\n"
            f"Output ONLY the text for the gap. Do not repeat Pre/Post words."
        )
        try:
            response = ollama.chat(model=self.llm_model, messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt},
            ])
            return self._clean_llm_output(response['message']['content'])
        except Exception as e:
            print(f"LLM Error: {e}")
            return option_a

    def reconcile(self, txt_a_path: str, txt_b_path: str, json_a_path: str, json_b_path: str) -> List[Dict[str, Any]]:
        words_a = self._load_json(json_a_path)
        words_b = self._load_json(json_b_path)
        thresh_a = self._calculate_threshold(words_a)
        thresh_b = self._calculate_threshold(words_b)
        seq_a = [w['word'].lower().strip() for w in words_a]
        seq_b = [w['word'].lower().strip() for w in words_b]
        matcher = difflib.SequenceMatcher(None, seq_a, seq_b)
        
        final_words = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                for k in range(i2 - i1):
                    # Flag = None means standard word
                    w = words_a[i1 + k].copy()
                    w['flag'] = None 
                    final_words.append(w)
            
            elif tag == 'replace':
                len_a = i2 - i1
                len_b = j2 - j1
                if len_a == len_b:
                    for k in range(len_a):
                        wa = words_a[i1 + k]
                        wb = words_b[j1 + k]
                        reg_a = self._is_regular(wa, thresh_a)
                        reg_b = self._is_regular(wb, thresh_b)
                        
                        # Case: One Low, One Regular -> Accept Regular SILENTLY (no flag)
                        if reg_a and not reg_b:
                            w = wa.copy()
                            w['flag'] = None
                            final_words.append(w)
                        elif reg_b and not reg_a:
                            w = wb.copy()
                            w['flag'] = None
                            final_words.append(w)
                        else:
                            # Both Low -> Infer
                            pre_ctx = " ".join([w['word'] for w in words_a[max(0, i1-5):i1]])
                            next_obj = words_a[i2] if i2 < len(words_a) else None
                            next_str = next_obj['word'] if next_obj else ""
                            post_ctx = f"{next_str} " + " ".join([w['word'] for w in words_a[i2+1:min(len(words_a), i2+6)]])
                            
                            inferred = self._infer_with_llm(pre_ctx, post_ctx, wa['word'], wb['word'])
                            inferred = self._remove_overlap(inferred, next_str)
                            
                            new_w = wa.copy()
                            new_w['word'] = inferred
                            new_w['confidence'] = min(wa['confidence'], wb['confidence'])
                            new_w['flag'] = 'inferred' # Mark for HTML/TXT logic
                            final_words.append(new_w)
                else:
                    # Block Replace -> Infer
                    block_a = " ".join([w['word'] for w in words_a[i1:i2]])
                    block_b = " ".join([w['word'] for w in words_b[j1:j2]])
                    pre_ctx = " ".join([w['word'] for w in words_a[max(0, i1-5):i1]])
                    next_obj = words_a[i2] if i2 < len(words_a) else None
                    next_str = next_obj['word'] if next_obj else ""
                    post_ctx = f"{next_str} " + " ".join([w['word'] for w in words_a[i2+1:min(len(words_a), i2+6)]])
                    
                    inferred = self._infer_with_llm(pre_ctx, post_ctx, block_a, block_b)
                    inferred = self._remove_overlap(inferred, next_str)
                    
                    if i2 > i1:
                        base = words_a[i1].copy()
                        if i2 > i1: base['end_ms'] = words_a[i2-1]['end_ms']
                    elif j2 > j1:
                        base = words_b[j1].copy()
                        if j2 > j1: base['end_ms'] = words_b[j2-1]['end_ms']
                    else: continue
                    
                    base['word'] = inferred
                    base['flag'] = 'inferred'
                    final_words.append(base)

            elif tag == 'delete':
                for k in range(i2 - i1):
                    wa = words_a[i1 + k]
                    if self._is_regular(wa, thresh_a): 
                        w = wa.copy()
                        w['flag'] = None
                        final_words.append(w)
                    else:
                        wa_mod = wa.copy()
                        wa_mod['flag'] = 'low'
                        final_words.append(wa_mod)

            elif tag == 'insert':
                for k in range(j2 - j1):
                    wb = words_b[j1 + k]
                    if self._is_regular(wb, thresh_b): 
                        w = wb.copy()
                        w['flag'] = None
                        final_words.append(w)
                    else:
                        wb_mod = wb.copy()
                        wb_mod['flag'] = 'low'
                        final_words.append(wb_mod)
        return final_words

    def _format_word_txt(self, w: Dict[str, Any]) -> str:
        text = w.get('word', '')
        flag = w.get('flag')
        if flag == 'inferred':
            return f"{self.MARKER_INFERRED_START}{text}{self.MARKER_INFERRED_END}"
        elif flag == 'low':
            return f"{self.MARKER_LOW_START}{text}{self.MARKER_LOW_END}"
        return text

    def _format_word_html(self, w: Dict[str, Any]) -> str:
        text = w.get('word', '')
        flag = w.get('flag')
        if flag == 'inferred':
            # Highlight inferred text yellow
            return f"<span style='background-color: yellow;' title='Inferred by AI'>{text}</span>"
        elif flag == 'low':
            # Highlight simple low confidence gray (optional, can remove if unwanted)
            return f"<span style='background-color: lightgray;' title='Low Confidence'>{text}</span>"
        return text

    def _write_utterance(self, file_obj, words: List[Dict[str, Any]], format_type='txt'):
        if not words: return
        start_ms = words[0].get('start_ms', 0) or 0
        end_ms = words[-1].get('end_ms', 0) or 0
        speaker = words[0].get('speaker', 'Unknown')
        
        if format_type == 'txt':
            text = " ".join([self._format_word_txt(w) for w in words])
            file_obj.write(f"[{start_ms/1000.0:.2f}s – {end_ms/1000.0:.2f}s] Speaker {speaker}: {text}\n")
        else:
            text = " ".join([self._format_word_html(w) for w in words])
            file_obj.write(f"<p><strong>[{start_ms/1000.0:.2f}s – {end_ms/1000.0:.2f}s] Speaker {speaker}:</strong> {text}</p>\n")

    def save_output(self, final_words: List[Dict[str, Any]]):
        # 1. Save JSON
        with open("reconciled_confidence.json", "w", encoding="utf-8") as f:
            json.dump({"words": final_words}, f, indent=2)
        print("Saved reconciled_confidence.json")
        
        GAP_MS = 1000
        cur_spk = None
        cur_blk = []
        last_end = 0
        
        # Prepare blocks first to reuse logic
        blocks = []
        for w in final_words:
            spk = w.get('speaker', 'Unknown')
            start = w.get('start_ms', 0)
            end = w.get('end_ms', 0)
            
            spk_chg = (spk != cur_spk)
            gap = False
            if cur_blk and start is not None:
                if (start - last_end) > GAP_MS: gap = True
            
            if (spk_chg or gap) and cur_blk:
                blocks.append(cur_blk)
                cur_blk = []
            
            cur_spk = spk
            cur_blk.append(w)
            if end is not None: last_end = end
        if cur_blk: blocks.append(cur_blk)

        # 2. Save TXT
        with open("reconciled_transcript.txt", "w", encoding="utf-8") as f:
            f.write("=== RECONCILED TRANSCRIPT ===\n\n")
            for blk in blocks:
                self._write_utterance(f, blk, 'txt')
        print("Saved reconciled_transcript.txt")

        # 3. Save HTML
        with open("reconciled_transcript.html", "w", encoding="utf-8") as f:
            f.write("<html><head><style>body { font-family: sans-serif; max-width: 800px; margin: auto; padding: 20px; } p { line-height: 1.6; margin-bottom: 15px; }</style></head><body>")
            f.write("<h2>RECONCILED TRANSCRIPT</h2>")
            for blk in blocks:
                self._write_utterance(f, blk, 'html')
            f.write("</body></html>")
        print("Saved reconciled_transcript.html")

if __name__ == "__main__":
    kevin = Kevin(llm_model="llama3")
    try:
        res = kevin.reconcile("transcript_A.txt", "transcript_B.txt", "confidence_A.json", "confidence_B.json")
        kevin.save_output(res)
    except FileNotFoundError:
        print("Please provide valid file paths.")
