import os
import subprocess  # nosemgrep: gitlab.bandit.B404 - subprocess is required for ffmpeg invocation
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, model_validator
from sqlmodel import Session

from ..auth import verify_token
from ..database import engine, get_session
from ..models import ClipJob

CLIPS_DIR = os.environ.get("CLIPS_DIR", "/tmp/videoai_clips")
os.makedirs(CLIPS_DIR, exist_ok=True)

MAX_CLIP_SECONDS = 600
FFMPEG_TIMEOUT = 120

router = APIRouter(prefix="/clips", tags=["clips"])


class CreateClipRequest(BaseModel):
    video_url: str
    start_seconds: float
    end_seconds: float

    @model_validator(mode="after")
    def check_request(self):
        parsed = urlparse(self.video_url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("video_url must use http or https")
        if self.start_seconds < 0:
            raise ValueError("start_seconds must be >= 0")
        if self.end_seconds <= self.start_seconds:
            raise ValueError("end_seconds must be greater than start_seconds")
        if self.end_seconds - self.start_seconds > MAX_CLIP_SECONDS:
            raise ValueError(f"clip too long (max {MAX_CLIP_SECONDS}s)")
        return self


def process_clip(clip_id: str, video_url: str, start: float, end: float):
    with Session(engine) as session:
        clip = session.get(ClipJob, clip_id)
        if not clip:
            return
        try:
            output_path = os.path.join(CLIPS_DIR, f"{clip_id}.mp4")
            cmd = [
                "ffmpeg",
                "-y",
                "-protocol_whitelist",
                "http,https,tcp,tls",
                "-ss",
                str(start),
                "-i",
                video_url,
                "-t",
                str(end - start),
                "-c",
                "copy",
                output_path,
            ]
            # URL already validated (http/https only); ffmpeg -protocol_whitelist; internal JWT.
            subprocess.run(
                cmd,  # nosemgrep
                check=True,
                capture_output=True,
                timeout=FFMPEG_TIMEOUT,
            )
            clip.status = "done"
            clip.output_path = output_path
            session.add(clip)
            session.commit()
        except subprocess.TimeoutExpired:
            clip.status = "failed"
            clip.error_message = "ffmpeg timed out"
            session.add(clip)
            session.commit()
        except subprocess.CalledProcessError as e:
            clip.status = "failed"
            stderr = e.stderr.decode(errors="replace") if e.stderr else ""
            clip.error_message = stderr[-2000:] or str(e)
            session.add(clip)
            session.commit()
        except Exception as e:
            clip.status = "failed"
            clip.error_message = str(e)
            session.add(clip)
            session.commit()


@router.post("", status_code=201, dependencies=[Depends(verify_token)])
def create_clip(
    body: CreateClipRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    clip = ClipJob(
        video_url=body.video_url,
        start_seconds=body.start_seconds,
        end_seconds=body.end_seconds,
    )
    session.add(clip)
    session.commit()
    session.refresh(clip)
    background_tasks.add_task(
        process_clip, clip.id, clip.video_url, clip.start_seconds, clip.end_seconds
    )
    return {"clip_id": clip.id, "status": clip.status}


@router.get("/{clip_id}", dependencies=[Depends(verify_token)])
def get_clip(clip_id: str, session: Session = Depends(get_session)):
    clip = session.get(ClipJob, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    return {
        "clip_id": clip.id,
        "status": clip.status,
        "download_url": f"/clips/{clip_id}/download" if clip.status == "done" else None,
        "error_message": clip.error_message,
    }


@router.get("/{clip_id}/download", dependencies=[Depends(verify_token)])
def download_clip(clip_id: str, session: Session = Depends(get_session)):
    clip = session.get(ClipJob, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    if clip.status != "done" or not clip.output_path:
        raise HTTPException(status_code=409, detail="Clip not ready")
    if not os.path.exists(clip.output_path):
        raise HTTPException(status_code=404, detail="Clip file not found on disk")
    return FileResponse(path=clip.output_path, media_type="video/mp4", filename=f"{clip_id}.mp4")
