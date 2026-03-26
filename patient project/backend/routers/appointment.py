# backend/routers/appointment.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

import models
import schemas
import calendar_service  # <-- IMPORT OUR NEW SERVICE
from db import get_db
from security import get_current_user, get_current_doctor
from datetime import timedelta
from sqlalchemy import and_
from datetime import datetime, timezone


router = APIRouter(prefix="/appointments", tags=["Appointments & Scheduling"])


@router.post("/", response_model=schemas.AppointmentRead)
def book_appointment(
    request: schemas.AppointmentCreate,
    db: Session = Depends(get_db),
    current_user: schemas.TokenData = Depends(get_current_user),
):
    # 1. Check if doctor exists
    doctor = (
        db.query(models.User)
        .filter(
            models.User.id == request.doctor_id,
            models.User.role == models.UserRole.DOCTOR,
        )
        .with_for_update()
        .first()
    )

    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    # 2. Check if the chat session actually belongs to this patient
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

    # 3. PREVENT DOCTOR DOUBLE-BOOKING (Time Clash)
    # Calculate the dangerous time window in Python to avoid SQL interval issues
    lower_bound = request.scheduled_time - timedelta(minutes=15)
    upper_bound = request.scheduled_time + timedelta(minutes=15)

    doctor_clash = (
        db.query(models.Appointment)
        .filter(
            models.Appointment.doctor_id == request.doctor_id,
            models.Appointment.status == models.AppointmentStatus.SCHEDULED,
            models.Appointment.scheduled_time > lower_bound,
            models.Appointment.scheduled_time < upper_bound,
        )
        .first()
    )

    if doctor_clash:
        raise HTTPException(
            status_code=409,  # 409 Conflict
            detail="The doctor is already booked at this time. Please choose another slot.",
        )

    # 4. PREVENT SESSION DOUBLE-BOOKING
    existing_appointment = (
        db.query(models.Appointment)
        .filter(
            models.Appointment.session_id == request.session_id,
            models.Appointment.status == models.AppointmentStatus.SCHEDULED,
        )
        .first()
    )

    if existing_appointment:
        raise HTTPException(
            status_code=400,
            detail="An active appointment is already scheduled for this triage session.",
        )

    # 5. Generate REAL Google Meet Link
    real_meet_link = calendar_service.create_meet_link(
        start_time=request.scheduled_time,
        doctor_email=doctor.email,
        patient_email=current_user.email,
    )

    if not real_meet_link:
        real_meet_link = "https://meet.google.com/error-generating-link"

    # 6. Save to DB
    new_appointment = models.Appointment(
        patient_id=current_user.user_id,
        doctor_id=request.doctor_id,
        session_id=request.session_id,
        scheduled_time=request.scheduled_time,
        meeting_link=real_meet_link,
        # Default status is automatically SCHEDULED thanks to models.py
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


@router.patch("/{appointment_id}/cancel", response_model=schemas.AppointmentRead)
def cancel_appointment(
    appointment_id: int,
    db: Session = Depends(get_db),
    current_user: schemas.TokenData = Depends(get_current_user),
):
    """Cancels an existing appointment."""

    # 1. Find the appointment
    appointment = (
        db.query(models.Appointment)
        .filter(models.Appointment.id == appointment_id)
        .first()
    )

    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    # 2. Security Check: Ensure the person canceling is either the doctor OR the patient
    if current_user.user_id not in [appointment.patient_id, appointment.doctor_id]:
        raise HTTPException(
            status_code=403, detail="Not authorized to cancel this appointment"
        )

    # 3. Check if it's already cancelled or completed
    if appointment.status != models.AppointmentStatus.SCHEDULED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel an appointment that is already {appointment.status.value}",
        )

    # 4. Update the status
    appointment.status = models.AppointmentStatus.CANCELLED

    db.commit()
    db.refresh(appointment)

    return appointment


def mark_past_appointments_completed(db: Session):
    """Called by the scheduler. Marks any SCHEDULED appointment whose
    scheduled_time is in the past as COMPLETED."""
    now = datetime.now(timezone.utc)
    updated = (
        db.query(models.Appointment)
        .filter(
            models.Appointment.status == models.AppointmentStatus.SCHEDULED,
            models.Appointment.scheduled_time < now,
        )
        .all()
    )
    for appt in updated:
        appt.status = models.AppointmentStatus.COMPLETED
    if updated:
        db.commit()
    db.close()