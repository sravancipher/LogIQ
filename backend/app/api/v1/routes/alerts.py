from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import AuthContext, require_api_key
from app.db.session import get_db
from app.schemas.alert import AlertTestRequest, AlertTestResponse, InsightNotifyRequest, InsightNotifyResponse
from app.services.alert_service import send_insight_notify_email, send_test_alert
from app.services.insights_service import build_insights

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.post("/test", response_model=AlertTestResponse)
def test_alert_delivery(
    payload: AlertTestRequest,
    _: AuthContext = Depends(require_api_key),
) -> AlertTestResponse:
    return send_test_alert(payload)


@router.post("/insights/notify", response_model=InsightNotifyResponse)
def notify_from_insights(
    payload: InsightNotifyRequest,
    auth: AuthContext = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> InsightNotifyResponse:
    insights = build_insights(
        db=db,
        project_id=auth.project_id,
        lookback_minutes=payload.lookback_minutes,
        deep_analysis=payload.deep_analysis,
    )
    return send_insight_notify_email(insights, payload)
