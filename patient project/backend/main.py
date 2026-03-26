# --- FIX FOR PYTHON 3.12+ / BCRYPT ISSUES ---
import bcrypt

bcrypt.__about__ = type("about", (object,), {"__version__": bcrypt.__version__})
# --------------------------------------------
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI
import os
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from db import engine, SessionLocal
import models

from routers import auth, chat, user, doctor, media, appointment
from routers.appointment import mark_past_appointments_completed

from apscheduler.schedulers.background import BackgroundScheduler

# Create database tables
models.Base.metadata.create_all(bind=engine)


# ── Scheduler setup ───────────────────────────────────────────────────────────
def run_completion_job():
    db = SessionLocal()
    mark_past_appointments_completed(db)


scheduler = BackgroundScheduler()
scheduler.add_job(run_completion_job, "interval", minutes=1)  # runs every 5 minutes


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="Patient Portal API", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(user.router)
app.include_router(doctor.router)
app.include_router(media.router)
app.include_router(appointment.router)

# --- CORS SETTINGS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://patient-project-seven.vercel.app/"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("uploaded_files", exist_ok=True)
app.mount("/static", StaticFiles(directory="uploaded_files"), name="static")
