import uuid
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.api_key import ApiKey


class AuthContext:
    def __init__(self, project_id: uuid.UUID):
        self.project_id = project_id


def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> AuthContext:
    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key")

    hashed = ApiKey.hash_key(x_api_key)
    stmt = select(ApiKey).where(ApiKey.key_hash == hashed, ApiKey.is_active.is_(True))
    key_obj = db.scalar(stmt)

    if not key_obj:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    key_obj.last_used_at = datetime.now(timezone.utc)
    db.commit()

    return AuthContext(project_id=key_obj.project_id)
