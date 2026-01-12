import os
import datetime
import assemblyai as aai
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Set API key
aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")
if not aai.settings.api_key:
    raise ValueError("ASSEMBLYAI_API_KEY not set in environment variables")

def delete_today_transcripts():
    transcriber = aai.Transcriber()

    # Get today's date in UTC
    today = datetime.datetime.utcnow().date()

    # Make timezone-aware start and end of day
    start_of_day = datetime.datetime(today.year, today.month, today.day, tzinfo=datetime.timezone.utc)
    end_of_day = datetime.datetime(today.year, today.month, today.day, 23, 59, 59, tzinfo=datetime.timezone.utc)

    print(f"Deleting transcripts from {start_of_day} to {end_of_day} (UTC)")

    params = aai.ListTranscriptParameters(limit=50)
    deleted_count = 0

    while True:
        page = transcriber.list_transcripts(params)

        for t in page.transcripts:
            # Parse created timestamp (ISO string) as UTC
            created_dt = datetime.datetime.fromisoformat(t.created.replace("Z", "+00:00"))

            # Compare with UTC-aware start/end
            if start_of_day <= created_dt <= end_of_day:
                try:
                    aai.Transcript.delete_by_id(t.id)
                    print(f"✅ Deleted {t.id} (created {created_dt})")
                    deleted_count += 1
                except Exception as e:
                    print(f"❌ Failed to delete {t.id}: {e}")
            else:
                print(f"Skipping {t.id} → {created_dt}")

        # Pagination
        if page.page_details.before_id_of_prev_url is not None:
            params.before_id = page.page_details.before_id_of_prev_url
        else:
            break

    print(f"\nDone! Deleted {deleted_count} transcripts created today.")

if __name__ == "__main__":
    delete_today_transcripts()
