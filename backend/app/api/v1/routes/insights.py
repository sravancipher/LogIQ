from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.security import AuthContext, require_api_key
from app.db.session import get_db
from app.models.insight_feedback import InsightFeedback
from app.schemas.insight import InsightFeedbackCreate, InsightFeedbackResponse, InsightsResponse, LatestInsightResponse
from app.services.insights_service import build_insights, get_latest_insight

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("", response_model=InsightsResponse)
def get_insights(
    lookback_minutes: int = Query(default=60, ge=5, le=43200),
    deep_analysis: bool = Query(default=False),
    levels: list[str] | None = Query(default=None, description="Restrict analysis to these log levels (e.g. ERROR, WARN, INFO). Omit for all levels."),
    auth: AuthContext = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> InsightsResponse:
    return build_insights(
        db=db,
        project_id=auth.project_id,
        lookback_minutes=lookback_minutes,
        deep_analysis=deep_analysis,
        levels=levels,
    )


@router.get("/latest", response_model=LatestInsightResponse)
def get_latest_insight_route(
    auth: AuthContext = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> LatestInsightResponse:
    """Return the last analysis actually computed for this project (via GET /insights),
    without recomputing anything - no LLM call, no fresh query. Used by the Overview
    page and by the AI Insights page on load, so both always agree on "the last
    analysis" instead of each silently running its own.
    """
    return get_latest_insight(db, auth.project_id)


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
