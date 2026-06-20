import json
import tempfile

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from filelock import FileLock
from pydantic import BaseModel
from sqlmodel import Session

from pipeline.downloader import download_video
from pipeline.scorer import score_highlights

from ..auth import verify_token
from ..database import engine, get_session
from ..models import AnalysisJob

router = APIRouter(prefix="/jobs", tags=["jobs"])

# Cross-process lock - FileLock works between Uvicorn workers (unlike threading.Lock).
# Serializes the CPU/RAM-heavy analysis step; downloads remain parallel.
_ANALYSIS_LOCK_PATH = "/tmp/videoai_analysis.lock"


def _set_progress(job_id: str, pct: int) -> None:
    """Update job progress using an isolated session to avoid sharing state with process_job."""
    with Session(engine) as s:
        job = s.get(AnalysisJob, job_id)
        if job:
            job.progress = pct
            s.add(job)
            s.commit()


class CreateJobRequest(BaseModel):
    vod_review_id: str
    video_url: str


def process_job(job_id: str):
    """Runs synchronously in thread pool via BackgroundTasks."""
    with Session(engine) as session:
        job = session.get(AnalysisJob, job_id)
        if not job:
            return
        try:
            job.status = "downloading"
            job.progress = 10
            session.add(job)
            session.commit()

            with tempfile.TemporaryDirectory() as tmpdir:
                video_path = download_video(job.video_url, tmpdir)

                # timeout=3600: a job can wait up to 1h for the lock - covers
                # a 90min VOD being analyzed by a concurrent job.
                with FileLock(_ANALYSIS_LOCK_PATH, timeout=3600):  # nosemgrep
                    job.status = "analyzing"
                    job.progress = 50
                    session.add(job)
                    session.commit()

                    suggestions = score_highlights(
                        video_path,
                        progress_callback=lambda pct: _set_progress(job_id, pct),
                    )

                job.status = "done"
                job.progress = 100
                job.suggested_timestamps = json.dumps(suggestions)
                session.add(job)
                session.commit()

        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            session.add(job)
            session.commit()


@router.post("", status_code=201, dependencies=[Depends(verify_token)])
def create_job(
    body: CreateJobRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    job = AnalysisJob(vod_review_id=body.vod_review_id, video_url=body.video_url)
    session.add(job)
    session.commit()
    session.refresh(job)
    background_tasks.add_task(process_job, job.id)
    return {"job_id": job.id, "status": job.status}


@router.get("/{job_id}", dependencies=[Depends(verify_token)])
def get_job(job_id: str, session: Session = Depends(get_session)):
    job = session.get(AnalysisJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    suggested = None
    if job.status == "done" and job.suggested_timestamps:
        suggested = json.loads(job.suggested_timestamps)

    return {
        "job_id": job.id,
        "status": job.status,
        "progress": job.progress,
        "suggested_timestamps": suggested,
        "error_message": job.error_message,
    }
