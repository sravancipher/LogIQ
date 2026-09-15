from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import AuthContext, require_api_key
from app.db.session import get_db
from app.schemas.maintenance import PartitionMaintenanceResponse
from app.services.partition_service import run_partition_maintenance

router = APIRouter(prefix="/maintenance", tags=["maintenance"])


@router.post("/partitions", response_model=PartitionMaintenanceResponse)
def run_partitions_maintenance(
    auth: AuthContext = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> PartitionMaintenanceResponse:
    """
    Ensure upcoming daily `logs` partitions exist and drop ones past the
    system-wide retention window (`LOG_RETENTION_DAYS`).

    This is a global, cross-tenant operation - it is not scoped to the calling
    project (`X-API-Key` is used only to authenticate the caller, same as every
    other route). Call it on a schedule from an external cron/uptime-monitor if
    you don't run the standalone queue worker, which performs the same
    maintenance on its own timer.
    """
    result = run_partition_maintenance(db)
    db.commit()
    return PartitionMaintenanceResponse(**result)
