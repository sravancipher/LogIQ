from pydantic import BaseModel


class PartitionMaintenanceResponse(BaseModel):
    partitions_ensured: list[str]
    partitions_dropped: list[str]
