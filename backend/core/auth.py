from datetime import datetime, timedelta

import jwt
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import bcrypt
from sqlalchemy.orm import Session

from core.database import get_db
from models.user import User

from core.config import settings

security = HTTPBearer()

JWT_SECRET = settings.JWT_SECRET
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    pwd_bytes = plain_password.encode('utf-8')
    hash_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(pwd_bytes, hash_bytes)


def create_access_token(user_id: int | str, role: str) -> str:
    expire = datetime.utcnow() + timedelta(days=7)
    print(expire)
    payload = {"userId": str(user_id), "role": role, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> str:
    token = credentials.credentials

    try:
      payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
      user_id = payload.get("userId")
    except jwt.PyJWTError:
      raise HTTPException(status_code=401, detail="Token expired or invalid")

    if user_id is None:
      raise HTTPException(status_code=401, detail="Invalid token")

    return str(user_id)

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(get_db)
) -> User:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        user_id = payload.get("userId")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Token expired or invalid")
    
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid token")
        
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    return user

def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Not enough privileges")
    return user
