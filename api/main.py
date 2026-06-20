from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlmodel import Session, SQLModel, select

from .database import engine
from .models import AnalysisJob, ClipJob
from .routes import clips, jobs

IN_PROGRESS_STATUSES = ("downloading", "analyzing", "pending")


def _recover_interrupted_jobs():
    """On startup, mark any jobs that were in-progress as failed.

    These were interrupted by a server crash or restart and will never
    complete on their own. Marking them failed lets the Rails poller
    surface the error so the user can retry.
    """
    with Session(engine) as session:
        stuck = session.exec(
            select(AnalysisJob).where(AnalysisJob.status.in_(IN_PROGRESS_STATUSES))
        ).all()
        for job in stuck:
            job.status = "failed"
            job.error_message = "Job interrupted by server restart. Please try again."
            session.add(job)

        stuck_clips = session.exec(select(ClipJob).where(ClipJob.status == "pending")).all()
        for clip in stuck_clips:
            clip.status = "failed"
            clip.error_message = "Interrupted by server restart."
            session.add(clip)

        session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    _recover_interrupted_jobs()
    yield


app = FastAPI(title="ProStaff VideoAI", lifespan=lifespan)
app.include_router(jobs.router)
app.include_router(clips.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "prostaff-videoai"}
