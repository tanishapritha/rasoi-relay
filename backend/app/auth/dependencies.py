from fastapi import Header, HTTPException

from app.core.config import get_settings

settings = get_settings()


def current_user(x_demo_user: str | None = Header(default=None, alias="X-Demo-User")) -> str:
    """Development identity only; production remains closed until real auth is configured."""
    if settings.app_env == "production":
        raise HTTPException(status_code=401, detail={"code": "AUTH_REQUIRED", "message": "Production authentication is not configured."})
    return x_demo_user or "demo-user"
