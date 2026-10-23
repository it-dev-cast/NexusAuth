from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.core.dependencies import get_admin_user, get_current_user, get_logout_user
from app.core.errors import api_ok
from app.database.database import get_db
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    RoleUpdateRequest,
    UserResponse,
)
from app.services.auth_service import (
    change_password,
    current_user_payload,
    dashboard_overview,
    list_user_sessions,
    login_user,
    logout_all_sessions,
    logout_user,
    refresh_tokens,
    register_user,
    revoke_user_session,
    unlock_user_account,
    update_user_role,
)


router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Authentication"],
)


@router.post("/register", status_code=201)
def register(
    data: RegisterRequest,
    db: Session = Depends(get_db),
):
    user = register_user(db, data)
    return api_ok(UserResponse.model_validate(user).model_dump())


@router.post("/login")
def login(
    data: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    return api_ok(login_user(db, data, request))


@router.get("/me")
def me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return api_ok(current_user_payload(db, current_user))


@router.post("/refresh")
def refresh(
    data: RefreshRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    return api_ok(refresh_tokens(db, data, request))


@router.post("/logout")
def logout(
    current_user: User = Depends(get_logout_user),
    db: Session = Depends(get_db),
):
    return api_ok(logout_user(db, current_user))


@router.get("/sessions")
def get_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return api_ok(list_user_sessions(db, current_user))


@router.delete("/sessions/{session_id}")
def revoke_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return api_ok(revoke_user_session(db, current_user, session_id))


@router.post("/logout-all")
def logout_all(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return api_ok(logout_all_sessions(db, current_user))


@router.get("/overview")
def overview(
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    return api_ok(dashboard_overview(db))


@router.patch("/users/{user_id}/role")
def set_user_role(
    user_id: int,
    data: RoleUpdateRequest,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    user = update_user_role(db, current_user, user_id, data.role)
    return api_ok(UserResponse.model_validate(user).model_dump())


@router.post("/users/{user_id}/unlock")
def unlock_user(
    user_id: int,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    user = unlock_user_account(db, current_user, user_id)
    return api_ok(UserResponse.model_validate(user).model_dump())


@router.post("/change-password")
def change_own_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    change_password(db, current_user, data.current_password, data.new_password)
    return api_ok({"message": "Password changed. All sessions have been logged out."})