# backend/routers/appointment.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import uuid

import models
import schemas
from db import get_db
from security import get_current_user, get_current_doctor

router = APIRouter(prefix="/appointments", tags=["Appointments & Scheduling"])


@router.post("/", response_model=schemas.AppointmentRead)
def book_appointment(
    request: schemas.AppointmentCreate,
    db: Session = Depends(get_db),
    current_user: schemas.TokenData = Depends(get_current_user),
):
    """Allows a patient to book a time slot with a doctor."""

    # Check if doctor exists
    doctor = (
        db.query(models.User)
        .filter(
            models.User.id == request.doctor_id,
            models.User.role == models.UserRole.DOCTOR,
        )
        .first()
    )

    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    # Check if the chat session actually belongs to this patient
    chat_session = (
        db.query(models.ChatHistory)
        .filter(
            models.ChatHistory.session_id == request.session_id,
            models.ChatHistory.patient_id == current_user.user_id,
        )
        .first()
    )

    if not chat_session:
        raise HTTPException(status_code=403, detail="Invalid chat session")

    # Generate a dummy meeting link for the MVP
    fake_meeting_id = str(uuid.uuid4())[:10]
    meet_link = f"https://meet.google.com/{fake_meeting_id}"

    new_appointment = models.Appointment(
        patient_id=current_user.user_id,
        doctor_id=request.doctor_id,
        session_id=request.session_id,
        scheduled_time=request.scheduled_time,
        meeting_link=meet_link,
    )

    db.add(new_appointment)
    db.commit()
    db.refresh(new_appointment)

    return new_appointment


@router.get("/me", response_model=List[schemas.AppointmentRead])
def get_my_appointments(
    db: Session = Depends(get_db),
    current_user: schemas.TokenData = Depends(get_current_user),
):
    """Fetches all upcoming appointments for the logged-in patient."""
    appointments = (
        db.query(models.Appointment)
        .filter(models.Appointment.patient_id == current_user.user_id)
        .order_by(models.Appointment.scheduled_time.asc())
        .all()
    )

    return appointments


@router.get("/doctor", response_model=List[schemas.AppointmentRead])
def get_doctor_appointments(
    db: Session = Depends(get_db),
    current_doctor: schemas.TokenData = Depends(
        get_current_doctor
    ),  # <-- VIP Bouncer in action!
):
    """Fetches all schedule appointments for the logged-in doctor."""
    appointments = (
        db.query(models.Appointment)
        .filter(models.Appointment.doctor_id == current_doctor.user_id)
        .order_by(models.Appointment.scheduled_time.asc())
        .all()
    )

    return appointments
