import os
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import yt_dlp


def _strip_playlist(url: str) -> str:
    """Remove list= param so yt-dlp downloads only the single video."""
    parsed = urlparse(url)
    if parsed.hostname and "youtube" in parsed.hostname:
        qs = parse_qs(parsed.query, keep_blank_values=True)
        qs.pop("list", None)
        qs.pop("index", None)
        new_query = urlencode({k: v[0] for k, v in qs.items()})
        return urlunparse(parsed._replace(query=new_query))
    return url


def download_video(url: str, output_dir: str) -> str:
    """Downloads video at analysis quality (360p) and returns local file path.

    Uses the Android YouTube client to avoid CDN 403s.
    360p is sufficient for scene detection and audio analysis.
    """
    url = _strip_playlist(url)

    errors = []

    ydl_opts = {
        # 360p cap - enough for scene detection + audio, much smaller download
        "format": (
            "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]"
            "/best[height<=360][ext=mp4]"
            "/best[height<=360]"
            "/worst[ext=mp4]/worst"
        ),
        "outtmpl": os.path.join(output_dir, "video.%(ext)s"),
        "merge_output_format": "mp4",
        "no_playlist": True,
        "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
        "logger": _SilentLogger(errors),
        "ignoreerrors": False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ret = ydl.download([url])
        if ret != 0:
            raise RuntimeError(f"yt-dlp failed (code {ret}): {'; '.join(errors[-3:])}")

    candidates = [
        f for f in os.listdir(output_dir) if f.startswith("video.") and not f.endswith(".part")
    ]
    if not candidates:
        detail = "; ".join(errors[-3:]) if errors else "unknown error"
        raise FileNotFoundError(f"yt-dlp produced no output file: {detail}")

    return os.path.join(output_dir, candidates[0])


class _SilentLogger:
    def __init__(self, errors: list):
        self._errors = errors

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        self._errors.append(msg)
