# backend/drive_service.py
import os
import json
import io
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")

DRIVE_FOLDER_ID = "1SO-FXLoCpzEcc2ML0IM9KC5ncVbvPCq_"


def _load_credentials():
    """
    Loads OAuth credentials from env var (production) or token.json (local dev).
    Refreshes the access token in-memory — no disk write needed, works on any machine.
    The refresh_token is long-lived and doesn't expire unless revoked.
    """
    token_json = os.getenv("GOOGLE_DRIVE_TOKEN")

    if token_json:
        # Production: read from environment variable
        info = json.loads(token_json)
    elif os.path.exists(TOKEN_FILE):
        # Local dev: read from token.json file
        with open(TOKEN_FILE, "r") as f:
            info = json.load(f)
    else:
        print("Error: No Drive credentials found. Set GOOGLE_DRIVE_TOKEN env var or add token.json.")
        return None

    # Build credentials using only the refresh_token (token=None forces immediate refresh)
    # This means it always gets a fresh access token in-memory — no stale token issues.
    creds = Credentials(
        token=None,
        refresh_token=info["refresh_token"],
        token_uri=info["token_uri"],
        client_id=info["client_id"],
        client_secret=info["client_secret"],
        scopes=info["scopes"],
    )

    # Refresh in-memory right now — no disk write required
    creds.refresh(Request())
    return creds


def get_drive_service():
    """Returns an authenticated Google Drive API service instance."""
    try:
        creds = _load_credentials()
        if not creds:
            return None
        return build("drive", "v3", credentials=creds)
    except Exception as e:
        print(f"Drive Auth Error: {e}")
        return None


def upload_to_drive(file_path: str, file_name: str, mime_type: str):
    service = get_drive_service()
    if not service:
        return None

    try:
        file_metadata = {"name": file_name, "parents": [DRIVE_FOLDER_ID]}
        media = MediaFileUpload(file_path, mimetype=mime_type)

        file = (
            service.files()
            .create(body=file_metadata, media_body=media, fields="id")
            .execute()
        )

        print(f"File Uploaded to Drive. ID: {file.get('id')}")
        return {"file_id": file.get("id"), "view_link": ""}

    except Exception as e:
        print(f"Drive upload error: {e}")
        return None


def get_file_stream(file_id: str):
    service = get_drive_service()
    if not service:
        return None

    try:
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)

        done = False
        while not done:
            status, done = downloader.next_chunk()

        fh.seek(0)
        return fh

    except Exception as e:
        print(f"Drive download error: {e}")
        return None


def delete_file_from_drive(file_id: str):
    service = get_drive_service()
    if not service:
        return

    try:
        service.files().delete(fileId=file_id).execute()
        print(f"Deleted Drive file: {file_id}")

    except Exception as e:
        print(f"Error deleting from Drive: {e}")