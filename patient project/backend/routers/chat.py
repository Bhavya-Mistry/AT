# backend/routers/chat.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
import shutil
import os
import uuid

import models
import schemas
import ai_service
import drive_service
from db import get_db
from security import get_current_user

# The prefix "/chat" means every route in here automatically starts with /chat
router = APIRouter(prefix="/chat", tags=["AI Chat"])


@router.post("/")
def chat_with_doctor(
    request: schemas.ChatRequest,
    db: Session = Depends(get_db),
    current_user: schemas.TokenData = Depends(get_current_user),
):
    secure_user_id = current_user.user_id

    history_record = (
        db.query(models.ChatHistory)
        .filter(models.ChatHistory.session_id == request.session_id)
        .first()
    )

    if not history_record:
        messages = []
        new_record = models.ChatHistory(
            patient_id=secure_user_id, session_id=request.session_id, messages=messages
        )
        db.add(new_record)
        db.commit()
        db.refresh(new_record)
        history_record = new_record
    else:
        if history_record.patient_id != secure_user_id:
            raise HTTPException(
                status_code=403, detail="Not authorized to access this chat"
            )
        messages = history_record.messages if history_record.messages else []

    # Call AI
    ai_response_text = ai_service.get_ai_response(messages, request.message)

    messages.append({"sender": "patient", "text": request.message})
    messages.append({"sender": "ai", "text": ai_response_text})

    is_summary_request = (
        "SUMMARIZE" in request.message.upper() or "SUMMARY" in request.message.upper()
    )

    if is_summary_request:
        # Notice we call it from ai_service now!
        summary_json = ai_service.clean_ai_json(ai_response_text)
        if summary_json:
            history_record.summary = summary_json
            flag_modified(history_record, "summary")

    history_record.messages = messages
    flag_modified(history_record, "messages")
    db.commit()

    return {"response": ai_response_text}


@router.post("/upload")
async def upload_chat_attachment(
    file: UploadFile = File(...),
    session_id: str = Form(...),
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
        raise HTTPException(status_code=400, detail="Only Images or PDFs allowed")

    file_ext = file.filename.split(".")[-1]
    unique_name = f"chat_upload_{uuid.uuid4()}.{file_ext}"
    temp_path = f"temp_{unique_name}"

    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        drive_data = drive_service.upload_to_drive(
            temp_path, unique_name, file.content_type
        )
        if not drive_data:
            raise Exception("Drive Upload Failed")

        analysis_text = ai_service.analyze_medical_image(temp_path)

        new_media = models.MedicalMedia(
            patient_id=secure_user_id,
            file_name=file.filename,
            file_type="image",
            drive_file_id=drive_data["file_id"],
            drive_view_link="",
            transcript=analysis_text,
        )
        db.add(new_media)
        db.commit()

        new_media.drive_view_link = f"http://127.0.0.1:8000/media/view/{new_media.id}"
        db.commit()

        history = (
            db.query(models.ChatHistory)
            .filter(models.ChatHistory.session_id == session_id)
            .first()
        )

        if not history:
            history = models.ChatHistory(
                patient_id=secure_user_id, session_id=session_id, messages=[]
            )
            db.add(history)
            db.commit()

        file_message = {
            "sender": "patient",
            "text": (
                f"[System: User uploaded file '{file.filename}']\n"
                f"*** EXTRACTED DOCUMENT CONTENT ***\n"
                f"{analysis_text}\n"
                f"**********************************\n"
                f"(Please analyze this medical data)"
            ),
            "is_file": True,
            "file_url": new_media.drive_view_link,
        }

        current_messages = list(history.messages) if history.messages else []
        current_messages.append(file_message)

        history.messages = current_messages
        flag_modified(history, "messages")
        db.commit()

        if os.path.exists(temp_path):
            os.remove(temp_path)

        return {
            "status": "success",
            "analysis": analysis_text,
            "file_url": new_media.drive_view_link,
        }

    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        print(f"Upload Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
