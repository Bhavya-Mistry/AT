# backend/calendar_service.py
import os
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from datetime import timedelta
import uuid

# 1. SETUP PATHS
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")


def get_calendar_service():
    """Authenticates using the saved User Token."""
    if not os.path.exists(TOKEN_FILE):
        print("Error: token.json not found.")
        return None
    try:
        creds = Credentials.from_authorized_user_file(TOKEN_FILE)
        return build("calendar", "v3", credentials=creds)
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
        "summary": "MediConnect Consultation",
        "description": "Automated Telemedicine Appointment via MediConnect AI.",
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
                "requestId": f"mediconnect_{uuid.uuid4().hex}",
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
