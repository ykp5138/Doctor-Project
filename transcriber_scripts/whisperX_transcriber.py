import os
import sys
import logging
import requests
import torch
import whisperx
import gc
import json  # <--- Enabled JSON support
from dotenv import load_dotenv

# --- FIX 1: Import Diarization from the correct specific location ---
from whisperx.diarize import DiarizationPipeline 

# --- CONFIGURATION ---
load_dotenv()
HF_TOKEN = os.getenv("HF_TOKEN")
OLLAMA_API_URL = "http://localhost:11434/api/generate"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class MeetingPipeline:
    def __init__(self, audio_path: str):
        self.audio_path = audio_path
        self.base_name = os.path.splitext(os.path.basename(audio_path))[0]
        
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.compute_type = "int8" 

        logging.info(f"🚀 Initialized on device: {self.device} (Compute: {self.compute_type})")
        
        if not HF_TOKEN:
            logging.error("❌ HF_TOKEN not found! Check your .env file.")
            sys.exit(1)

    def transcribe_and_align(self):
        logging.info("🎙️ Loading Whisper Model (large-v3)...")
        model = whisperx.load_model("large-v3", self.device, compute_type=self.compute_type)
        audio = whisperx.load_audio(self.audio_path)
        
        logging.info("⏳ Transcribing audio...")
        result = model.transcribe(audio, batch_size=16)
        
        # Cleanup
        del model
        gc.collect()
        torch.cuda.empty_cache()

        logging.info("🔗 Aligning text timestamps...")
        model_a, metadata = whisperx.load_align_model(language_code=result["language"], device=self.device)
        result = whisperx.align(result["segments"], model_a, metadata, audio, self.device, return_char_alignments=False)
        
        del model_a
        gc.collect()
        torch.cuda.empty_cache()
        
        return result, audio

    def diarize(self, result, audio):
        logging.info("👥 Loading Diarization Pipeline...")
        try:
            # --- FIX 2: Use the directly imported class ---
            diarize_model = DiarizationPipeline(use_auth_token=HF_TOKEN, device=self.device)
        except Exception as e:
            logging.error(f"❌ Failed to load Diarization. Error: {e}")
            sys.exit(1)
            
        logging.info("⏳ Identifying Speakers...")
        diarize_segments = diarize_model(audio)
        
        logging.info("🧠 Merging Speakers with Transcript...")
        final_result = whisperx.assign_word_speakers(diarize_segments, result)
        
        return final_result

    def format_output(self, result):
        segments = result["segments"]
        detailed_lines = []
        clean_text_blocks = []

        for seg in segments:
            start = seg["start"]
            end = seg["end"]
            text = seg["text"].strip()
            speaker = seg.get("speaker", "Unknown")
            
            line = f"[{start:.2f}s - {end:.2f}s] {speaker}: {text}"
            detailed_lines.append(line)
            clean_text_blocks.append(f"{speaker}: {text}")

        return "\n".join(detailed_lines), "\n".join(clean_text_blocks)

    def summarize(self, full_text):
        logging.info("🧠 Generating Summary with Ollama (Llama 3)...")
        text_chunk = full_text[:30000]
        
        prompt = f"""
        You are an expert minute-taker. Analyze the following transcript:
        
        {text_chunk}
        
        Output a Markdown summary with:
        1. **Executive Summary**: 3-5 bullet points.
        2. **Key Topics**: Grouped by theme.
        3. **Action Items**: Who promised what.
        """
        
        try:
            response = requests.post(
                OLLAMA_API_URL,
                json={"model": "llama3", "prompt": prompt, "stream": False}
            )
            return response.json().get("response", "Error: No response from Ollama.")
        except Exception as e:
            return f"⚠️ Could not connect to Ollama: {e}"

    def run(self):
        result_raw, audio_data = self.transcribe_and_align()
        final_result = self.diarize(result_raw, audio_data)
        detailed_txt, clean_txt = self.format_output(final_result)
        
        # --- FIX 3: Save the Raw JSON ---
        json_filename = f"{self.base_name}_full_output.json"
        with open(json_filename, "w", encoding="utf-8") as f:
            json.dump(final_result, f, indent=2)
        logging.info(f"💾 Saved JSON Data: {json_filename}")

        # Save Text
        txt_filename = f"{self.base_name}_transcript.txt"
        with open(txt_filename, "w", encoding="utf-8") as f:
            f.write(detailed_txt)
        logging.info(f"💾 Saved transcript: {txt_filename}")

        # Save Summary
        summary = self.summarize(clean_txt)
        md_filename = f"{self.base_name}_summary.md"
        with open(md_filename, "w", encoding="utf-8") as f:
            f.write(summary)
        logging.info(f"💾 Saved summary: {md_filename}")
        
        logging.info("🎉 Processing Complete!")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_meeting.py <audio_file.mp3>")
        sys.exit(1)
    
    pipeline = MeetingPipeline(sys.argv[1])
    pipeline.run()