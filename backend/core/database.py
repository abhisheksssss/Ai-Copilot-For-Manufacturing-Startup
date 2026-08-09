import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from core.config import settings

DATABASE_URL = settings.DATABASE_URL
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./copilot.db"

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

kwargs = {}
if not DATABASE_URL.startswith("sqlite"):
    kwargs["pool_pre_ping"] = True
    kwargs["pool_recycle"] = 300

engine = create_engine(DATABASE_URL, connect_args=connect_args, **kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
