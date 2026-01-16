import os
import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io

# 1. SETUP PATHS
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, 'token.json')

# 2. YOUR FOLDER ID (We keep this from before)
DRIVE_FOLDER_ID = '1SO-FXLoCpzEcc2ML0IM9KC5ncVbvPCq_'

def get_drive_service():
    """Authenticates using the saved User Token (OAuth)."""
    # Debug check
    if not os.path.exists(TOKEN_FILE):
        print(f"Error: token.json not found at {TOKEN_FILE}. Run get_token.py first.")
        return None
    
    try:
        # Load credentials from the token file
        creds = Credentials.from_authorized_user_file(TOKEN_FILE)
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        print(f"Auth Error: {e}")
        return None

def upload_to_drive(file_path: str, file_name: str, mime_type: str):
    service = get_drive_service()
    if not service: return None

    try:
        # Upload as YOU (The User)
        file_metadata = {
            'name': file_name,
            'parents': [DRIVE_FOLDER_ID] 
        }
        
        media = MediaFileUpload(file_path, mimetype=mime_type)
        
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()

        print(f"File Uploaded to Drive. ID: {file.get('id')}")
        
        return {
            "file_id": file.get('id'),
            "view_link": "" 
        }

    except Exception as e:
        print(f"An error occurred during Drive upload: {e}")
        return None

def get_file_stream(file_id: str):
    service = get_drive_service()
    if not service: return None

    try:
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        
        fh.seek(0)
        return fh
    except Exception as e:
        print(f"Drive Download Error: {e}")
        return None

def delete_file_from_drive(file_id: str):
    service = get_drive_service()
    if not service: return

    try:
        service.files().delete(fileId=file_id).execute()
        print(f"Deleted Drive File: {file_id}")
    except Exception as e:
        print(f"Error deleting from Drive: {e}")