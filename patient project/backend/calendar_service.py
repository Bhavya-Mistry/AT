# backend/calendar_service.py
import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import timedelta
import json
from google.auth.transport.requests import Request
import uuid

# 1. SETUP PATHS
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")


def get_calendar_service():
    """Authenticates using the saved User Token from Env Var or File."""
    token_json = os.getenv("GOOGLE_DRIVE_TOKEN")

    try:
        # 1. Try fetching from Environment Variable (.env)
        if token_json:
            info = json.loads(token_json)
            creds = Credentials(
                token=None,
                refresh_token=info["refresh_token"],
                token_uri=info["token_uri"],
                client_id=info["client_id"],
                client_secret=info["client_secret"],
                scopes=info["scopes"],
            )
            # Refresh token in memory
            creds.refresh(Request())
            return build("calendar", "v3", credentials=creds)

        # 2. Fallback to physical token.json file (for local dev)
        elif os.path.exists(TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(TOKEN_FILE)
            return build("calendar", "v3", credentials=creds)

        else:
            print("Error: No Google Token found in .env or token.json")
            return None

    except Exception as e:
        print(f"Auth Error: {e}")
        return None


def create_meet_link(start_time, doctor_email, patient_email):
    """Creates a Calendar Event and returns the attached Google Meet link."""
    service = get_calendar_service()
    if not service:
        return None

    # Assume a 15-minute appointment
    end_time = start_time + timedelta(minutes=15)

    event_details = {
        "summary": "ClinIQ",
        "description": "Automated Telemedicine Appointment via ClinIQ.",
        "start": {
            "dateTime": start_time.isoformat(),
            "timeZone": "Asia/Kolkata",  # Change this to your local timezone if needed
        },
        "end": {
            "dateTime": end_time.isoformat(),
            "timeZone": "Asia/Kolkata",
        },
        "attendees": [
            {"email": doctor_email},
            {"email": patient_email},
        ],
        # THIS IS THE MAGIC PART THAT GENERATES THE MEET LINK
        "conferenceData": {
            "createRequest": {
                "requestId": f"cliniq_{uuid.uuid4().hex}",
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
    }

    try:
        # conferenceDataVersion=1 is REQUIRED to get the Meet link back
        event = (
            service.events()
            .insert(calendarId="primary", body=event_details, conferenceDataVersion=1)
            .execute()
        )

        # Extract the Google Meet link from the response
        return event.get("hangoutLink")

    except Exception as e:
        print(f"Failed to create Google Meet event: {e}")
        return None
