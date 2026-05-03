"""
integrations.py — Cloud integration CRUD + webhook receiver routes.

Authenticated routes (require X-API-Key):
  POST   /api/v1/integrations                          — register a cloud connection
  GET    /api/v1/integrations                          — list connections for project
  DELETE /api/v1/integrations/{integration_id}         — remove a connection

Unauthenticated webhook receiver (cloud posts here):
  POST   /api/v1/integrations/webhook/{integration_id}?token=<webhook_token>
"""

import secrets
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import AuthContext, require_api_key
from app.db.session import get_db
from app.models.cloud_integration import CloudIntegration
from app.models.log import Log
from app.schemas.integration import (
    IntegrationCreate,
    IntegrationListResponse,
    IntegrationResponse,
    WebhookAckResponse,
)
from app.services.cloud_normalizer import normalize_webhook, normalize_aws, normalize_azure

router = APIRouter(prefix="/integrations", tags=["integrations"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_response(integration: CloudIntegration, base_url: str) -> IntegrationResponse:
    webhook_url = f"{base_url}/api/v1/integrations/webhook/{integration.id}"
    return IntegrationResponse(
        id=integration.id,
        project_id=integration.project_id,
        name=integration.name,
        provider=integration.provider,
        status=integration.status,
        webhook_url=webhook_url,
        webhook_token=integration.webhook_token,
        created_at=integration.created_at,
    )


def _base_url(request: Request) -> str:
    """Derive base URL (scheme + host) from the incoming request."""
    return str(request.base_url).rstrip("/")


# ---------------------------------------------------------------------------
# CRUD — require API key
# ---------------------------------------------------------------------------

@router.post("", response_model=IntegrationResponse, status_code=status.HTTP_201_CREATED)
def create_integration(
    payload: IntegrationCreate,
    request: Request,
    auth: AuthContext = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> IntegrationResponse:
    """Register a new cloud integration for this project.

    Returns the webhook URL and token that you must configure in AWS/Azure/GCP.
    """
    token = secrets.token_urlsafe(32)
    integration = CloudIntegration(
        project_id=auth.project_id,
        name=payload.name,
        provider=payload.provider,
        webhook_token=token,
        status="active",
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return _build_response(integration, _base_url(request))


@router.get("", response_model=IntegrationListResponse)
def list_integrations(
    request: Request,
    auth: AuthContext = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> IntegrationListResponse:
    rows = db.scalars(
        select(CloudIntegration)
        .where(CloudIntegration.project_id == auth.project_id)
        .order_by(CloudIntegration.created_at.desc())
    ).all()
    return IntegrationListResponse(
        items=[_build_response(r, _base_url(request)) for r in rows]
    )


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_integration(
    integration_id: uuid.UUID = Path(...),
    auth: AuthContext = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> None:
    row = db.scalar(
        select(CloudIntegration).where(
            CloudIntegration.id == integration_id,
            CloudIntegration.project_id == auth.project_id,
        )
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
    db.delete(row)
    db.commit()


# ---------------------------------------------------------------------------
# Webhook receiver — no API key, cloud posts here
# Auto-routes to correct parser based on source type hint and payload shape

@router.post("/webhook/{integration_id}", response_model=WebhookAckResponse)
async def receive_webhook(
    integration_id: uuid.UUID = Path(...),
    token: str = Query(..., description="Webhook token issued when integration was created"),
    source: str = Query(
        None,
        description=(
            "Optional parser hint. "
            "Examples: cloudwatch, cloudtrail, guardduty, rds, lambda, security_hub, eventbridge, "
            "azure_monitor, activity_log, app_insights, service_health, defender, aks, event_grid, "
            "gcp_logging, gcp_monitoring, security_command_center"
        ),
    ),
    request: Request = None,
    db: Session = Depends(get_db),
) -> WebhookAckResponse:
    """
    Cloud-facing webhook receiver. Auto-routes to correct parser.
    
    Supports:
      AWS: CloudWatch, CloudTrail, GuardDuty, RDS, Lambda, Security Hub
      Azure: Monitor Alerts, Activity Log, App Insights, Service Health, Defender
      GCP: Cloud Logging, Cloud Monitoring, Security Command Center
    
    Optional: use ?source=<service_hint> for explicit routing when payload auto-detect is ambiguous.
    """
    row = db.scalar(
        select(CloudIntegration).where(CloudIntegration.id == integration_id)
    )
    if not row or not secrets.compare_digest(row.webhook_token, token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if row.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Integration is inactive")

    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body")

    # Use universal normalizer with optional source hint
    log_rows = normalize_webhook(body, row.project_id, source_hint=source)

    if log_rows:
        db.add_all([Log(**r) for r in log_rows])
        db.commit()

    return WebhookAckResponse(
        accepted=len(log_rows),
        message=f"Accepted {len(log_rows)} log event(s) from {row.provider or 'unknown provider'}",
    )
