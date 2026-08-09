from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.auth import create_access_token, get_current_user_id, hash_password, verify_password
from core.database import get_db
from models.user import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class UserCreate(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    token: str
    userId: int
    email: str
    role: str


class UserProfile(BaseModel):
    id: int
    email: str
    role: str


@router.post("/register", response_model=AuthResponse)
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    email = user.email.strip().lower()

    if len(user.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(email=email, password_hash=hash_password(user.password))
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {
        "token": create_access_token(new_user.id, new_user.role),
        "userId": new_user.id,
        "email": new_user.email,
        "role": new_user.role,
    }


@router.post("/login", response_model=AuthResponse)
def login_user(user: UserCreate, db: Session = Depends(get_db)):
    email = user.email.strip().lower()
    db_user = db.query(User).filter(User.email == email).first()

    if not db_user or not verify_password(user.password, db_user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return {
        "token": create_access_token(db_user.id, db_user.role),
        "userId": db_user.id,
        "email": db_user.email,
        "role": db_user.role,
    }


@router.get("/me", response_model=UserProfile)
def get_profile(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == int(user_id)).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {"id": user.id, "email": user.email, "role": user.role}
