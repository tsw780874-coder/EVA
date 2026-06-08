from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.schemas.auth import (
    RegisterRequest, LoginRequest, RefreshRequest,
    AuthResponse, TokenResponse, UserResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    user, access_token, refresh_token = await auth_service.register_user(
        db, body.email, body.name, body.password
    )
    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    user, access_token, refresh_token = await auth_service.login_user(
        db, body.email, body.password
    )
    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserResponse.model_validate(user),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    _, access_token, refresh_token = await auth_service.refresh_token(db, body.refresh_token)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)
