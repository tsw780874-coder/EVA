from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
from app.config import get_settings

settings = get_settings()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(subject: str | int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode = {"sub": str(subject), "exp": expire, "type": "access"}
    return jwt.encode(to_encode, key=settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str | int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    to_encode = {"sub": str(subject), "exp": expire, "type": "refresh"}
    return jwt.encode(to_encode, key=settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    return jwt.decode(token, key=settings.jwt_secret, algorithms=[settings.jwt_algorithm])
