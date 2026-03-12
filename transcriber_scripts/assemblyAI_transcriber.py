import os
import subprocess
import statistics
import json
from dotenv import load_dotenv
import assemblyai as aai


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO_DIR = os.path.join(BASE_DIR, "audio")


SUPPORTED_AUDIO_EXTS = (".mp3", ".wav", ".m4a")
VIDEO_EXTS = (".mov",)



def extract_audio_from_mov(video_path, wav_path):
    """
    Extract audio from .mov file and convert to 16kHz WAV
    """
    print(f"Extracting audio from {video_path} → {wav_path}")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            wav_path
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True
    )



def main():
    load_dotenv(os.path.join(BASE_DIR, ".env"))


    aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not aai.settings.api_key:
        raise ValueError("ASSEMBLYAI_API_KEY not found in .env file")


    if not os.path.isdir(AUDIO_DIR):
        raise FileNotFoundError(f"Folder '{AUDIO_DIR}' does not exist")


    files = os.listdir(AUDIO_DIR)
    audio_files = []


    for f in files:
        lower = f.lower()
        full_path = os.path.join(AUDIO_DIR, f)


        if lower.endswith(SUPPORTED_AUDIO_EXTS):
            audio_files.append(full_path)


        elif lower.endswith(VIDEO_EXTS):
            base = os.path.splitext(f)[0]
            wav_path = os.path.join(AUDIO_DIR, f"{base}.wav")


            if not os.path.exists(wav_path):
                extract_audio_from_mov(full_path, wav_path)


            audio_files.append(wav_path)


    audio_files.sort()


    if not audio_files:
        print(f"No supported audio or video files found in '{AUDIO_DIR}'.")
        return


    print("Files to transcribe:")
    for i, f in enumerate(audio_files, start=1):
        print(f"{i}. {os.path.basename(f)}")


    transcriber = aai.Transcriber()
    config = aai.TranscriptionConfig(
        speaker_labels=True,
        punctuate=True,
        format_text=True
    )


    out_dir = os.path.join(BASE_DIR, "outputs", "assembly")
    os.makedirs(out_dir, exist_ok=True)

    for audio_path in audio_files:
        filename = os.path.basename(audio_path)
        base_name = os.path.splitext(filename)[0]
        transcript = None


        print(f"\nTranscribing: {audio_path}\n")


        try:
            transcript = transcriber.transcribe(audio_path, config=config)


            if transcript.status == aai.TranscriptStatus.error:
                print(f"Transcription failed for {filename}: {transcript.error}")
                continue


            # ---------- CONFIDENCE STATISTICS ----------
            confidences = [
                w.confidence for w in getattr(transcript, "words", [])
                if w.confidence is not None
            ]


            if confidences:
                mean_conf = statistics.mean(confidences)
                std_conf = statistics.stdev(confidences) if len(confidences) > 1 else 0
                threshold = mean_conf - std_conf
            else:
                mean_conf = std_conf = threshold = None


            # ---------- WRITE TXT (RENAMED) ----------
            txt_file = os.path.join(out_dir, f"{base_name}_transcript.txt")
            with open(txt_file, "w", encoding="utf-8") as f:
                f.write("=== FULL TRANSCRIPT ===\n\n")


                if hasattr(transcript, "words"):
                    for word in transcript.words:
                        f.write(word.text + " ")
                else:
                    f.write(transcript.text)


                f.write("\n\n=== CONFIDENCE STATS ===\n")
                if mean_conf is not None:
                    f.write(f"Mean: {mean_conf:.3f}\n")
                    f.write(f"Std Dev: {std_conf:.3f}\n")
                    f.write(f"Flag Threshold: {threshold:.3f}\n")


                f.write("\n=== TIMESTAMPED UTTERANCES ===\n\n")
                for utt in transcript.utterances:
                    start = utt.start / 1000
                    end = utt.end / 1000
                    f.write(
                        f"[{start:.2f}s – {end:.2f}s] "
                        f"Speaker {utt.speaker}: {utt.text}\n"
                    )


            print(f"Transcript saved to {txt_file}")


            # ---------- WRITE HTML (RENAMED) ----------
            html_file = os.path.join(out_dir, f"{base_name}_transcript.html")
            with open(html_file, "w", encoding="utf-8") as f:
                f.write("<html><body>\n")
                f.write("<h2>FULL TRANSCRIPT</h2>\n<p>")


                if hasattr(transcript, "words"):
                    for word in transcript.words:
                        text = word.text
                        if (
                            mean_conf is not None
                            and word.confidence is not None
                            and word.confidence < threshold
                        ):
                            text = f"<mark title='Low confidence'>{text}</mark>"
                        f.write(text + " ")
                else:
                    f.write(transcript.text)


                f.write("</p>\n")


                f.write("<h3>Confidence Statistics</h3>\n")
                if mean_conf is not None:
                    f.write(
                        f"<p>Mean: {mean_conf:.3f}<br>"
                        f"Std Dev: {std_conf:.3f}<br>"
                        f"Flag Threshold: {threshold:.3f}</p>"
                    )


                f.write("<h2>TIMESTAMPED UTTERANCES</h2>\n")


                for utt in transcript.utterances:
                    start = utt.start / 1000
                    end = utt.end / 1000
                    utt_text = ""


                    for word in getattr(utt, "words", []):
                        w = word.text
                        if (
                            mean_conf is not None
                            and word.confidence is not None
                            and word.confidence < threshold
                        ):
                            w = f"<mark title='Low confidence'>{w}</mark>"
                        utt_text += w + " "


                    if not utt_text:
                        utt_text = utt.text


                    f.write(
                        f"<p>[{start:.2f}s – {end:.2f}s] "
                        f"Speaker {utt.speaker}: {utt_text.strip()}</p>\n"
                    )


                f.write("</body></html>")


            print(f"Transcript saved to {html_file}")


            # ---------- WRITE WORD-CONFIDENCE JSON (RENAMED) ----------
            json_words = [
                {
                    "word": w.text,
                    "confidence": w.confidence,
                    "start_ms": w.start,
                    "end_ms": w.end,
                    "speaker": getattr(w, "speaker", None)
                }
                for w in getattr(transcript, "words", [])
            ]


            json_output = {
                "file": filename,
                "confidence_summary": {
                    "mean": mean_conf,
                    "std_dev": std_conf,
                    "flag_threshold": threshold
                },
                "words": json_words
            }


            json_file = os.path.join(out_dir, f"{base_name}_confidence.json")
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(json_output, f, indent=2)


            print(f"Word-confidence JSON saved to {json_file}")


        finally:
            # ---------- DELETE + VERIFY ----------
            if transcript and getattr(transcript, "id", None):
                try:
                    aai.Transcript.delete(transcript.id)
                    print("Remote transcript deleted")


                    try:
                        aai.Transcript.get(transcript.id)
                        print("⚠️ WARNING: Transcript still exists after deletion")
                    except Exception:
                        print("✅ Deletion verified: transcript no longer exists")


                except Exception as e:
                    print(f"❌ Failed to delete transcript: {e}")



if __name__ == "__main__":
    main()