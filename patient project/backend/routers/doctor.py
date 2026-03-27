# backend/routers/doctor.py
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from typing import List
from datetime import datetime
import uuid
import audit_service
import models
import schemas
import pdf_generation_service
import drive_service
import email_service
from db import get_db
from security import get_current_doctor
import os

router = APIRouter(
    prefix="/doctor",
    tags=["Doctor Dashboard"],
    dependencies=[Depends(get_current_doctor)],
)


@router.get("/patients/", response_model=List[schemas.UserRead])
def get_all_patients(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    patients = (
        db.query(models.User)
        .filter(models.User.role == models.UserRole.PATIENT)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return patients


@router.get("/patients/{patient_id}/summaries")
def get_patient_timeline(
    patient_id: int,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_doctor: schemas.TokenData = Depends(get_current_doctor),
):
    audit_service.log_action(
        db=db,
        actor_id=current_doctor.user_id,
        patient_id=patient_id,
        action="VIEWED_PATIENT_TIMELINE",
    )

    sessions = (
        db.query(models.ChatHistory)
        .filter(models.ChatHistory.patient_id == patient_id)
        .all()
    )
    files = (
        db.query(models.MedicalMedia)
        .filter(models.MedicalMedia.patient_id == patient_id)
        .all()
    )

    timeline = []

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

    timeline.sort(key=lambda x: x["created_at"], reverse=True)
    return timeline[skip : skip + limit]


@router.get("/patients/{patient_id}/chat/{chat_id}")
def get_patient_chat_by_id(
    patient_id: int,
    chat_id: int,
    db: Session = Depends(get_db),
    current_doctor: schemas.TokenData = Depends(get_current_doctor),
):
    audit_service.log_action(
        db=db,
        actor_id=current_doctor.user_id,
        patient_id=patient_id,
        action="VIEWED_CHAT_SESSION",
    )

    session = (
        db.query(models.ChatHistory)
        .filter(
            models.ChatHistory.id == chat_id,
            models.ChatHistory.patient_id == patient_id,
        )
        .first()
    )

    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    return {
        "session_id": session.session_id,
        "patient_id": session.patient_id,
        "messages": session.messages or [],
        "summary": session.summary,
        "created_at": session.created_at,
    }


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

    # Mark session as reviewed
    if history_record.summary and isinstance(history_record.summary, dict):
        history_record.summary["reviewed"] = True
        flag_modified(history_record, "summary")

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
        date_str=datetime.now().strftime("%d %B %Y"),
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

    new_media.drive_view_link = f"/media/view/{new_media.id}"
    db.commit()

    # Inject follow-up message into chat
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

    # FIX 1: Use branded send_prescription_email (not the plain text fallback)
    # FIX 2: Schedule background task BEFORE os.remove so the PDF file still exists
    #         when the email task runs and tries to attach it
    background_tasks.add_task(
        email_service.send_prescription_email,
        to_email=patient.email,
        patient_name=patient_name,
        doctor_name="Dr. Smith",
        date_str=datetime.now().strftime("%d %B %Y"),
        notes=request.doctor_notes,
        pdf_path=file_path,
        follow_up_days=request.follow_up_days,
    )

    # FIX 2 cont: Delete local PDF only AFTER the background task is registered
    if os.path.exists(file_path):
        os.remove(file_path)

    return {
        "message": "Prescription generated and sent to patient",
        "file_url": new_media.drive_view_link,
    }


@router.get("/patients/{patient_id}/files", response_model=List[schemas.MediaRead])
def get_patient_files_for_doctor(
    patient_id: int,
    db: Session = Depends(get_db),
    current_doctor: schemas.TokenData = Depends(get_current_doctor),
):
    audit_service.log_action(
        db=db,
        actor_id=current_doctor.user_id,
        patient_id=patient_id,
        action="VIEWED_ALL_PATIENT_FILES",
    )
    return (
        db.query(models.MedicalMedia)
        .filter(models.MedicalMedia.patient_id == patient_id)
        .all()
    )
