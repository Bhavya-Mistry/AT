import urllib.parse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
 
 
# 2. Construct the URL using the encoded password
# Default postgres user is often 'postgres' - check if yours is 'user'
DATABASE_URL = "postgresql://postgres:Bm%406352181842@localhost:5432/patient_portal"
 
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()
 