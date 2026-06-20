import uuid

from sqlmodel import Field, SQLModel


class AnalysisJob(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    vod_review_id: str
    video_url: str
    status: str = "pending"  # pending | downloading | analyzing | done | failed
    progress: int = 0  # 0-100
    error_message: str | None = None
    suggested_timestamps: str | None = None  # JSON string


class ClipJob(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    video_url: str
    start_seconds: float
    end_seconds: float
    status: str = "pending"  # pending | processing | done | failed
    output_path: str | None = None
    error_message: str | None = None
