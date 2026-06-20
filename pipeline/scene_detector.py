from scenedetect import SceneManager, open_video
from scenedetect.detectors import ContentDetector


def detect_scenes(video_path: str, max_seconds: float = 5400.0) -> list[float]:
    """Returns scene change timestamps (seconds), limited to first max_seconds."""
    video = open_video(video_path)
    manager = SceneManager()
    manager.add_detector(ContentDetector(threshold=22.0, min_scene_len=15))
    end_time = None
    try:
        from scenedetect import FrameTimecode

        end_time = FrameTimecode(timecode=max_seconds, fps=video.frame_rate)
    except Exception:  # noqa: S110 - FrameTimecode unavailable in older scenedetect; fallback to full scan
        pass
    manager.detect_scenes(video, end_time=end_time)
    scenes = manager.get_scene_list()
    return [s[0].get_seconds() for s in scenes if s[0].get_seconds() <= max_seconds]
