from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.security import AuthContext, require_api_key
from app.db.session import get_db
from app.models.insight_feedback import InsightFeedback
from app.schemas.insight import InsightFeedbackCreate, InsightFeedbackResponse, InsightsResponse
from app.services.insights_service import build_insights

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("", response_model=InsightsResponse)
def get_insights(
    lookback_minutes: int = Query(default=60, ge=5, le=1440),
    deep_analysis: bool = Query(default=False),
    auth: AuthContext = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> InsightsResponse:
    return build_insights(
        db=db,
        project_id=auth.project_id,
        lookback_minutes=lookback_minutes,
        deep_analysis=deep_analysis,
    )


@router.post("/feedback", response_model=InsightFeedbackResponse, status_code=status.HTTP_201_CREATED)
def submit_insight_feedback(
    payload: InsightFeedbackCreate,
    auth: AuthContext = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> InsightFeedbackResponse:
    row = InsightFeedback(
        project_id=auth.project_id,
        rating=payload.rating,
        lookback_minutes=payload.lookback_minutes,
        analysis_mode=payload.analysis_mode,
        model_name=payload.model_name,
        root_cause=payload.root_cause,
        suggestion=payload.suggestion,
        incident_summary=payload.incident_summary,
        correction=payload.correction,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return InsightFeedbackResponse(id=str(row.id), message="Feedback recorded")
