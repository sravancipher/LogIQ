from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import AuthContext, require_api_key
from app.db.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import investigate

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    auth: AuthContext = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> ChatResponse:
    """Ask a natural-language question about this project's logs. Stateless: no
    conversation is persisted, each request is an independent, bounded investigation
    (see MAX_TOOL_CALLS in chat_service.py)."""
    return investigate(db, auth.project_id, payload.message, payload.lookback_minutes)
