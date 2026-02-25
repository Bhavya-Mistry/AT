# backend/routers/media.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
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


@router.post("/transcribe/")
async def transcribe_audio_endpoint(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: schemas.TokenData = Depends(get_current_user),
):
    secure_user_id = current_user.user_id

    file_ext = file.filename.split(".")[-1]
    unique_name = f"audio_{uuid.uuid4()}.{file_ext}"
    temp_path = f"temp_{unique_name}"

    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        drive_data = drive_service.upload_to_drive(
            temp_path, unique_name, file.content_type
        )
        transcription_text = ai_service.transcribe_audio(temp_path)

        if os.path.exists(temp_path):
            os.remove(temp_path)

        new_media = models.MedicalMedia(
            patient_id=secure_user_id,
            file_name="Voice Note - " + unique_name[:8],
            file_type="audio",
            drive_file_id=drive_data["file_id"],
            drive_view_link="",
            transcript=transcription_text,
        )
        db.add(new_media)
        db.commit()

        new_media.drive_view_link = f"http://127.0.0.1:8000/media/view/{new_media.id}"
        db.commit()

        return {
            "transcript": transcription_text,
            "media_id": new_media.id,
            "file_url": new_media.drive_view_link,
        }

    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=500, detail=str(e))


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


@router.post("/ocr/analyze")
async def analyze_medical_document(
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
        raise HTTPException(
            status_code=400, detail="Invalid file type. Please upload an Image or PDF."
        )

    file_ext = file.filename.split(".")[-1]
    unique_name = f"ocr_{uuid.uuid4()}.{file_ext}"
    temp_path = f"temp_{unique_name}"

    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        drive_data = drive_service.upload_to_drive(
            temp_path, unique_name, file.content_type
        )
        if not drive_data:
            raise HTTPException(
                status_code=500, detail="Failed to upload to Cloud Storage"
            )

        analysis_result = ai_service.analyze_medical_image(temp_path)

        new_media = models.MedicalMedia(
            patient_id=secure_user_id,
            file_name=file.filename,
            file_type="image_ocr",
            drive_file_id=drive_data["file_id"],
            drive_view_link="",
            transcript=analysis_result,
        )

        db.add(new_media)
        db.commit()
        db.refresh(new_media)

        new_media.drive_view_link = f"http://127.0.0.1:8000/media/view/{new_media.id}"
        db.commit()

        if os.path.exists(temp_path):
            os.remove(temp_path)

        return {
            "id": new_media.id,
            "filename": file.filename,
            "analysis": analysis_result,
            "file_url": new_media.drive_view_link,
        }

    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=500, detail=str(e))


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
