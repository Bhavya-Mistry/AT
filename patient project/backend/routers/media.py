# backend/routers/media.py
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
    BackgroundTasks,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import shutil
import os
import uuid

import models
import schemas
import ai_service
import drive_service
from db import get_db
from security import get_current_user

router = APIRouter(tags=["Media & Files"])


def process_audio_in_background(
    temp_path: str, unique_name: str, file_content_type: str, media_id: int
):
    db = next(get_db())
    try:
        # 1. Upload & Transcribe
        drive_data = drive_service.upload_to_drive(
            temp_path, unique_name, file_content_type
        )
        transcription_text = ai_service.transcribe_audio(temp_path)

        # 2. Update DB
        media_record = (
            db.query(models.MedicalMedia)
            .filter(models.MedicalMedia.id == media_id)
            .first()
        )
        if media_record:
            media_record.drive_file_id = drive_data["file_id"]
            media_record.drive_view_link = (
                f"http://127.0.0.1:8000/media/view/{media_id}"
            )
            media_record.transcript = transcription_text
            db.commit()
    except Exception as e:
        print(f"Background Audio Error: {e}")
        media_record = (
            db.query(models.MedicalMedia)
            .filter(models.MedicalMedia.id == media_id)
            .first()
        )
        if media_record:
            media_record.transcript = f"ERROR PROCESSING AUDIO: {str(e)}"
            db.commit()
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        db.close()


@router.post("/transcribe/")
async def transcribe_audio_endpoint(
    background_tasks: BackgroundTasks,  # <-- Inject BackgroundTasks
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: schemas.TokenData = Depends(get_current_user),
):
    secure_user_id = current_user.user_id
    file_ext = file.filename.split(".")[-1]
    unique_name = f"audio_{uuid.uuid4()}.{file_ext}"
    temp_path = f"temp_{unique_name}"

    # 1. Save file locally instantly
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 2. Create placeholder in DB
    new_media = models.MedicalMedia(
        patient_id=secure_user_id,
        file_name="Voice Note - " + unique_name[:8],
        file_type="audio",
        drive_file_id="processing...",
        drive_view_link="",
        transcript="Audio is being transcribed. Please wait...",  # Temporary
    )
    db.add(new_media)
    db.commit()
    db.refresh(new_media)

    # 3. Queue the background task
    background_tasks.add_task(
        process_audio_in_background,
        temp_path=temp_path,
        unique_name=unique_name,
        file_content_type=file.content_type,
        media_id=new_media.id,
    )

    # 4. Instantly return
    return {
        "media_id": new_media.id,
        "message": "Audio uploaded successfully! Transcription is running in the background.",
        "status": "processing",
    }


@router.delete("/media/{media_id}")
def delete_media(
    media_id: int,
    db: Session = Depends(get_db),
    current_user: schemas.TokenData = Depends(get_current_user),
):
    media_item = (
        db.query(models.MedicalMedia).filter(models.MedicalMedia.id == media_id).first()
    )

    if not media_item:
        raise HTTPException(status_code=404, detail="File not found")

    # Security: Ensure the user actually owns this file before they delete it!
    if media_item.patient_id != current_user.user_id:
        raise HTTPException(
            status_code=403, detail="Not authorized to delete this file"
        )

    if media_item.drive_file_id and media_item.drive_file_id != "local_error":
        drive_service.delete_file_from_drive(media_item.drive_file_id)

    db.delete(media_item)
    db.commit()
    return {"detail": "File deleted successfully"}


@router.get("/media/view/{media_id}")
def view_media_proxy(
    media_id: int,
    db: Session = Depends(get_db),
    current_user: schemas.TokenData = Depends(get_current_user),
):
    media = (
        db.query(models.MedicalMedia).filter(models.MedicalMedia.id == media_id).first()
    )
    if not media:
        raise HTTPException(status_code=404, detail="File not found")

    # Security: Ensure the user owns this file (or is a doctor, but we'll keep it simple for now)
    if media.patient_id != current_user.user_id and current_user.role != "doctor":
        raise HTTPException(status_code=403, detail="Not authorized to view this file")

    file_stream = drive_service.get_file_stream(media.drive_file_id)
    if not file_stream:
        raise HTTPException(
            status_code=500, detail="Could not retrieve file from Cloud"
        )

    mime_type = "application/pdf"
    if media.file_type == "audio":
        mime_type = "audio/webm"
    elif media.file_type == "image" or media.file_type == "image_ocr":
        mime_type = "image/jpeg"

    return StreamingResponse(file_stream, media_type=mime_type)


def process_ocr_in_background(
    temp_path: str, unique_name: str, file_content_type: str, media_id: int
):
    # We need a new database session just for this background worker
    db = next(get_db())

    try:
        # 1. Upload to Drive
        drive_data = drive_service.upload_to_drive(
            temp_path, unique_name, file_content_type
        )
        if not drive_data:
            raise Exception("Drive upload failed")

        # 2. Analyze with Gemini
        analysis_result = ai_service.analyze_medical_image(temp_path)

        # 3. Update the database record with the results
        media_record = (
            db.query(models.MedicalMedia)
            .filter(models.MedicalMedia.id == media_id)
            .first()
        )
        if media_record:
            media_record.drive_file_id = drive_data["file_id"]
            media_record.drive_view_link = (
                f"http://127.0.0.1:8000/media/view/{media_id}"
            )
            media_record.transcript = analysis_result
            db.commit()

    except Exception as e:
        print(f"Background OCR Error: {e}")
        # Mark as failed in DB so the user knows
        media_record = (
            db.query(models.MedicalMedia)
            .filter(models.MedicalMedia.id == media_id)
            .first()
        )
        if media_record:
            media_record.transcript = f"ERROR PROCESSING FILE: {str(e)}"
            db.commit()

    finally:
        # 4. Clean up the temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)
        db.close()


@router.post("/ocr/analyze")
async def analyze_medical_document(
    background_tasks: BackgroundTasks,  # <-- Inject BackgroundTasks here
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: schemas.TokenData = Depends(get_current_user),
):
    secure_user_id = current_user.user_id

    if file.content_type not in [
        "image/jpeg",
        "image/png",
        "image/webp",
        "application/pdf",
    ]:
        raise HTTPException(status_code=400, detail="Invalid file type.")

    file_ext = file.filename.split(".")[-1]
    unique_name = f"ocr_{uuid.uuid4()}.{file_ext}"
    temp_path = f"temp_{unique_name}"

    # 1. Save the file locally (Super fast)
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 2. Create a "Placeholder" record in the database (Super fast)
    new_media = models.MedicalMedia(
        patient_id=secure_user_id,
        file_name=file.filename,
        file_type="image_ocr",
        drive_file_id="processing...",  # Temporary
        drive_view_link="",
        transcript="File is being analyzed. Please refresh in a few seconds...",  # Temporary
    )
    db.add(new_media)
    db.commit()
    db.refresh(new_media)

    # 3. Hand off the heavy lifting to the background worker
    background_tasks.add_task(
        process_ocr_in_background,
        temp_path=temp_path,
        unique_name=unique_name,
        file_content_type=file.content_type,
        media_id=new_media.id,
    )

    # 4. Instantly reply to the user
    return {
        "id": new_media.id,
        "message": "File uploaded successfully! Analysis is running in the background.",
        "status": "processing",
    }


@router.post("/media/upload/")
async def upload_generic_media(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: schemas.TokenData = Depends(get_current_user),
):
    secure_user_id = current_user.user_id

    file_ext = file.filename.split(".")[-1]
    unique_name = f"upload_{uuid.uuid4()}.{file_ext}"
    temp_path = f"temp_{unique_name}"

    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        mime_type = file.content_type
        drive_data = drive_service.upload_to_drive(temp_path, unique_name, mime_type)

        if os.path.exists(temp_path):
            os.remove(temp_path)

        if not drive_data:
            raise HTTPException(
                status_code=500, detail="Failed to upload to Cloud Storage"
            )

        new_media = models.MedicalMedia(
            patient_id=secure_user_id,
            file_name=file.filename,
            file_type="image" if "image" in mime_type else "document",
            drive_file_id=drive_data["file_id"],
            drive_view_link="",
            transcript="User Uploaded Record",
        )

        db.add(new_media)
        db.commit()
        db.refresh(new_media)

        new_media.drive_view_link = f"http://127.0.0.1:8000/media/view/{new_media.id}"
        db.commit()

        return {
            "id": new_media.id,
            "file_url": new_media.drive_view_link,
            "message": "Upload successful",
        }

    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=500, detail=str(e))
