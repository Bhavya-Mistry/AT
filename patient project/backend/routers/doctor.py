# backend/routers/doctor.py
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    BackgroundTasks,
)  # <-- Add BackgroundTasks
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import flag_modified
from typing import List
from datetime import datetime
import uuid
import audit_service
import models
import schemas
import pdf_generation_service
import drive_service
import email_service  # <-- Add this import
from db import get_db
from security import get_current_doctor

router = APIRouter(
    prefix="/doctor",
    tags=["Doctor Dashboard"],
    dependencies=[
        Depends(get_current_doctor)
    ],  # <-- Protects EVERY route in this file!
)


@router.get("/patients/", response_model=List[schemas.UserRead])
def get_all_patients(
    skip: int = 0,  # <-- Start at index 0 by default
    limit: int = 50,  # <-- Only fetch 50 patients at a time by default
    db: Session = Depends(get_db),
):
    """Fetches a paginated list of all patients."""
    patients = (
        db.query(models.User)
        .filter(models.User.role == models.UserRole.PATIENT)
        .offset(skip)  # Skip the first N records
        .limit(limit)  # Only take the next N records
        .all()
    )

    return patients


# @router.get(
#     "/patients/{patient_id}/summaries", response_model=List[schemas.ChatHistoryRead]
# )
# def get_patient_summaries(patient_id: int, db: Session = Depends(get_db)):
#     """Fetches chat sessions and SORTS them by priority score."""
#     sessions = (
#         db.query(models.ChatHistory)
#         .filter(models.ChatHistory.patient_id == patient_id)
#         .all()
#     )

#     def get_priority(session):
#         if session.summary and isinstance(session.summary, dict):
#             return session.summary.get("priority_score", 0)
#         return 0

#     sessions.sort(key=get_priority, reverse=True)
#     return sessions


@router.get("/patients/{patient_id}/summaries")
def get_patient_timeline(
    patient_id: int,
    skip: int = 0,  # <-- Add pagination params here too
    limit: int = 20,
    db: Session = Depends(get_db),
    current_doctor: schemas.TokenData = Depends(get_current_doctor),
):
    """Fetches a paginated, chronological timeline of AI chat summaries and uploaded files."""

    # (Assuming you added the HIPAA Audit Log here from our last step!)
    import audit_service

    audit_service.log_action(
        db=db,
        actor_id=current_doctor.user_id,
        patient_id=patient_id,
        action="VIEWED_PATIENT_TIMELINE",
    )

    # 1. Fetch all Chat Sessions
    sessions = (
        db.query(models.ChatHistory)
        .filter(models.ChatHistory.patient_id == patient_id)
        .all()
    )

    # 2. Fetch all Medical Files
    files = (
        db.query(models.MedicalMedia)
        .filter(models.MedicalMedia.patient_id == patient_id)
        .all()
    )

    timeline = []

    # 3. Format Chat Summaries
    for session in sessions:
        if session.summary:
            priority = (
                session.summary.get("priority_score", 0)
                if isinstance(session.summary, dict)
                else 0
            )
            timeline.append(
                {
                    "type": "triage_summary",
                    "id": f"chat_{session.id}",
                    "title": "AI Triage Assessment",
                    "created_at": session.created_at,
                    "priority_score": priority,
                    "content": session.summary,
                }
            )

    # 4. Format Medical Files
    for f in files:
        timeline.append(
            {
                "type": "medical_record",
                "id": f"file_{f.id}",
                "title": f.file_name,
                "created_at": f.created_at,
                "priority_score": None,
                "content": {
                    "file_type": f.file_type,
                    "transcript": f.transcript,
                    "url": f.drive_view_link,
                },
            }
        )

    # 5. Sort chronologically (Newest first)
    timeline.sort(key=lambda x: x["created_at"], reverse=True)

    # 6. --- NEW: APPLY PAGINATION VIA PYTHON SLICING ---
    paginated_timeline = timeline[skip : skip + limit]

    return paginated_timeline


@router.post("/prescribe/")
def create_prescription(
    request: schemas.PrescriptionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    history_record = (
        db.query(models.ChatHistory)
        .filter(models.ChatHistory.session_id == request.session_id)
        .first()
    )
    if not history_record:
        raise HTTPException(status_code=404, detail="Session not found")

    patient = (
        db.query(models.User)
        .filter(models.User.id == history_record.patient_id)
        .first()
    )
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    patient_name = patient.profile.full_name if patient.profile else "Patient"

    # Generate PDF
    filename = f"Prescription_{request.session_id}_{uuid.uuid4().hex[:6]}.pdf"
    file_path = pdf_generation_service.generate_medical_report(
        patient_name=patient_name,
        date_str=datetime.now().strftime("%Y-%m-%d"),
        summary_json=history_record.summary,
        doctor_notes=request.doctor_notes,
        filename=filename,
        follow_up_days=request.follow_up_days,
    )

    # Upload to Drive
    drive_data = drive_service.upload_to_drive(file_path, filename, "application/pdf")

    # Save to Database
    new_media = models.MedicalMedia(
        patient_id=patient.id,
        file_name=f"Rx: {filename}",
        file_type="pdf",
        drive_file_id=drive_data["file_id"],
        drive_view_link="",
        transcript=request.doctor_notes,
    )
    db.add(new_media)
    db.commit()

    new_media.drive_view_link = f"http://127.0.0.1:8000/media/view/{new_media.id}"
    db.commit()

    # Inject message into chat
    follow_up_msg = (
        f"*** AUTOMATED SYSTEM MESSAGE ***\n"
        f"Dr. Smith has issued a prescription. It is now available in your 'My Files' tab.\n"
        f"A follow-up check-in has been scheduled for {request.follow_up_days} days from now."
    )
    messages = history_record.messages if history_record.messages else []
    messages.append({"sender": "ai", "text": follow_up_msg})

    history_record.messages = messages
    flag_modified(history_record, "messages")
    db.commit()

    email_subject = "New Prescription Available - MediConnect"
    email_body = f"""Hello {patient_name},

A new prescription has been issued for you by your doctor. 
A follow-up check-in has been scheduled for {request.follow_up_days} days from now.

You can view and securely download your prescription by logging into your MediConnect Patient Portal and checking the 'My Files' section.

Best regards,
MediConnect Care Team
"""
    # Send the email in the background so the doctor's screen doesn't freeze waiting for it
    background_tasks.add_task(
        email_service.send_email_notification,
        to_email=patient.email,
        subject=email_subject,
        body=email_body,
    )
    # ------------------------------------

    return {
        "message": "Prescription generated and sent to patient",
        "file_url": new_media.drive_view_link,
    }


@router.get("/patients/{patient_id}/files", response_model=List[schemas.MediaRead])
def get_patient_files_for_doctor(
    patient_id: int,
    db: Session = Depends(get_db),
    current_doctor: schemas.TokenData = Depends(get_current_doctor),  # <-- Added
):
    """Allows doctors to see every document, OCR result, and prescription for a specific patient."""
    # --- 🔒 HIPAA AUDIT LOGGING ---
    audit_service.log_action(
        db=db,
        actor_id=current_doctor.user_id,
        patient_id=patient_id,
        action="VIEWED_ALL_PATIENT_FILES",
    )
    # ------------------------------
    return (
        db.query(models.MedicalMedia)
        .filter(models.MedicalMedia.patient_id == patient_id)
        .all()
    )
