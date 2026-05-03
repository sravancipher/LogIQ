from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.api_key import ApiKey
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectCreateResponse

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectCreateResponse, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> ProjectCreateResponse:
    project = Project(name=payload.name, description=payload.description)
    db.add(project)
    db.flush()

    raw_key = ApiKey.generate_raw_key()
    api_key = ApiKey(
        project_id=project.id,
        key_hash=ApiKey.hash_key(raw_key),
        key_prefix=ApiKey.get_prefix(raw_key),
    )
    db.add(api_key)
    db.commit()

    return ProjectCreateResponse(project_id=project.id, api_key=raw_key)
