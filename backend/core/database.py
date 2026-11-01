import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import OperationalError, InterfaceError

from core.config import settings
from core.dns_fallback import resolve_db_hostaddr

DATABASE_URL = settings.DATABASE_URL
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./copilot_dev.db"

resolved_url = resolve_db_hostaddr(DATABASE_URL)

_SQLITE_URL = "sqlite:///./copilot_dev.db"
_fallback_engine = create_engine(_SQLITE_URL, connect_args={"check_same_thread": False})
FallbackSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_fallback_engine)


def _init_engine(url: str):
    is_sqlite = url.startswith("sqlite")
    connect_args = {"check_same_thread": False} if is_sqlite else {
        "connect_timeout": 5,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }
    kwargs = {}
    if not is_sqlite:
        kwargs["pool_pre_ping"] = True
        kwargs["pool_recycle"] = 120

    eng = create_engine(url, connect_args=connect_args, **kwargs)

    if not is_sqlite:
        try:
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as conn_err:
            print(f"[WARNING] Primary database connection failed ({conn_err}). Falling back to local SQLite database.")
            eng = _fallback_engine

    return eng


engine = _init_engine(resolved_url)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = None
    try:
        db = SessionLocal()
        yield db
    except (OperationalError, InterfaceError) as db_err:
        print(f"[WARNING] Database connection error ({db_err}). Serving from fallback SQLite session.")
        fallback_db = FallbackSessionLocal()
        try:
            yield fallback_db
        finally:
            fallback_db.close()
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass

