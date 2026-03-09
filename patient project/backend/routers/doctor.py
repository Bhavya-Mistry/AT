# backend/routers/doctor.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import flag_modified
from typing import List
from datetime import datetime
import uuid

import models
import schemas
import pdf_generation_service
import drive_service
from db import get_db
from security import get_current_doctor  # <-- VIP BOUNCER

router = APIRouter(
    prefix="/doctor",
    tags=["Doctor Dashboard"],
    dependencies=[
        Depends(get_current_doctor)
    ],  # <-- Protects EVERY route in this file!
)


@router.get("/patients/", response_model=List[schemas.UserRead])
def get_all_patients(db: Session = Depends(get_db)):
    # Fetch patients and their latest chat summaries
    patients = (
        db.query(models.User).filter(models.User.role == models.UserRole.PATIENT).all()
    )

    # Logic to sort patients based on the highest priority_score found in their ChatHistory
    # (This can be done in Python for simplicity or a complex SQL join)
    return patients


@router.get(
    "/patients/{patient_id}/summaries", response_model=List[schemas.ChatHistoryRead]
)
def get_patient_summaries(patient_id: int, db: Session = Depends(get_db)):
    """Fetches chat sessions and SORTS them by priority score."""
    sessions = (
        db.query(models.ChatHistory)
        .filter(models.ChatHistory.patient_id == patient_id)
        .all()
    )

    def get_priority(session):
        if session.summary and isinstance(session.summary, dict):
            return session.summary.get("priority_score", 0)
        return 0

    sessions.sort(key=get_priority, reverse=True)
    return sessions


@router.post("/prescribe/")
def create_prescription(
    request: schemas.PrescriptionRequest, db: Session = Depends(get_db)
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

    return {
        "message": "Prescription generated and sent to patient",
        "file_url": new_media.drive_view_link,
    }


@router.get("/patients/{patient_id}/files", response_model=List[schemas.MediaRead])
def get_patient_files_for_doctor(patient_id: int, db: Session = Depends(get_db)):
    """Allows doctors to see every document, OCR result, and prescription for a specific patient."""
    return (
        db.query(models.MedicalMedia)
        .filter(models.MedicalMedia.patient_id == patient_id)
        .all()
    )
