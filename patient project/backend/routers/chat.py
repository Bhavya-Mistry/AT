# backend/routers/chat.py
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
    BackgroundTasks,
)
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


def process_chat_upload_in_background(
    temp_path: str,
    unique_name: str,
    file_content_type: str,
    media_id: int,
    session_id: str,
    filename: str,
):
    db = next(get_db())
    try:
        # 1. Upload & Analyze
        drive_data = drive_service.upload_to_drive(
            temp_path, unique_name, file_content_type
        )
        analysis_text = ai_service.analyze_medical_image(temp_path)

        # 2. Update Media DB
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
            media_record.transcript = analysis_text
            db.commit()

        # 3. Inject the result into the Chat History
        history = (
            db.query(models.ChatHistory)
            .filter(models.ChatHistory.session_id == session_id)
            .first()
        )
        if history:
            file_message = {
                "sender": "patient",
                "text": (
                    f"[System: User uploaded file '{filename}']\n"
                    f"*** EXTRACTED DOCUMENT CONTENT ***\n"
                    f"{analysis_text}\n"
                    f"**********************************\n"
                    f"(Please analyze this medical data)"
                ),
                "is_file": True,
                "file_url": media_record.drive_view_link,
            }

            # Remove the "processing" message we added earlier, append the real one
            current_messages = list(history.messages) if history.messages else []
            if current_messages and current_messages[-1].get("status") == "processing":
                current_messages.pop()

            current_messages.append(file_message)
            history.messages = current_messages
            flag_modified(history, "messages")
            db.commit()

    except Exception as e:
        print(f"Background Chat Upload Error: {e}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        db.close()


@router.post("/upload")
async def upload_chat_attachment(
    background_tasks: BackgroundTasks,  # <-- Inject BackgroundTasks
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

    # 1. Save locally instantly
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 2. Create placeholder in Media DB
    new_media = models.MedicalMedia(
        patient_id=secure_user_id,
        file_name=file.filename,
        file_type="image",
        drive_file_id="processing...",
        drive_view_link="",
        transcript="Analyzing file...",
    )
    db.add(new_media)
    db.commit()
    db.refresh(new_media)

    # 3. Create temporary "Processing" message in Chat History
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

    current_messages = list(history.messages) if history.messages else []
    current_messages.append(
        {
            "sender": "system",
            "text": f"Uploading and analyzing {file.filename} in the background...",
            "status": "processing",
        }
    )
    history.messages = current_messages
    flag_modified(history, "messages")
    db.commit()

    # 4. Queue the task
    background_tasks.add_task(
        process_chat_upload_in_background,
        temp_path=temp_path,
        unique_name=unique_name,
        file_content_type=file.content_type,
        media_id=new_media.id,
        session_id=session_id,
        filename=file.filename,
    )

    # 5. Instantly return
    return {
        "status": "processing",
        "message": "File is being uploaded and analyzed. The chat will update shortly.",
    }
