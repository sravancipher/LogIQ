from fastapi import APIRouter, Depends

from app.core.security import AuthContext, require_api_key
from app.schemas.alert import AlertTestRequest, AlertTestResponse
from app.services.alert_service import send_test_alert

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.post("/test", response_model=AlertTestResponse)
def test_alert_delivery(
    payload: AlertTestRequest,
    _: AuthContext = Depends(require_api_key),
) -> AlertTestResponse:
    return send_test_alert(payload)
