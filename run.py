#!/usr/bin/env python3
"""
Single-command pipeline: WhisperX → AssemblyAI → Kevin merge + summary
Usage: python run.py audio/meeting_doctor.mp3
"""
import subprocess
import sys
import os


def main():
    if len(sys.argv) < 2:
        print("Usage: python run.py <audio_file>")
        print("Example: python run.py audio/meeting_doctor.mp3")
        sys.exit(1)

    audio_path = sys.argv[1]
    if not os.path.exists(audio_path):
        print(f"Error: File not found: {audio_path}")
        sys.exit(1)

    base = os.path.splitext(os.path.basename(audio_path))[0]
    py = sys.executable

    print(f"\n{'='*55}")
    print(f"  Processing: {audio_path}")
    print(f"{'='*55}\n")

    # Step 1: WhisperX
    print("Step 1/3 — WhisperX transcription + diarization...")
    subprocess.run(
        [py, 'transcriber_scripts/whisperX_transcriber.py', audio_path],
        check=True
    )
    whisper_out = os.path.join('outputs', 'whisperx', f'{base}_full_output.json')

    # Step 2: AssemblyAI
    print("\nStep 2/3 — AssemblyAI transcription...")
    subprocess.run(
        [py, 'transcriber_scripts/assemblyAI_transcriber.py', audio_path],
        check=True
    )
    assembly_out = os.path.join('outputs', 'assembly', f'{base}_confidence.json')

    # Step 3: Kevin merge + summary
    print("\nStep 3/3 — Kevin merge + summary generation...")
    subprocess.run(
        [py, 'kevin.py', whisper_out, assembly_out],
        check=True
    )

    print(f"\n{'='*55}")
    print(f"  Done! Outputs saved to outputs/kevin/")
    print(f"    Transcript: {base}_transcript.txt")
    print(f"    Summary:    {base}_summary.txt")
    print(f"{'='*55}\n")


if __name__ == '__main__':
    main()
