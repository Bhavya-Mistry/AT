from db import engine
from models import Base

# This command deletes ALL tables in your database
print("⚠️  Dropping old tables...")
Base.metadata.drop_all(bind=engine)
print("✅  Old tables dropped.")

# This command recreates them with the NEW columns
print("🛠️  Recreating tables with new schema...")
Base.metadata.create_all(bind=engine)
print("✅  Database is now fresh and ready!")