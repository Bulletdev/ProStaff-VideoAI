"""
Validate peak RAM usage of the chunked audio loader.

Run inside Docker with a real video file:
  docker exec prostaff-videoai python scripts/validate_ram_peak.py /path/to/video.mp4

Exit code 1 if peak exceeds the warning threshold (400 MB per chunk).
This script must be run before changing chunk_sec in production.
"""

import sys
import tracemalloc


def measure(video_path: str, chunk_sec: float = 600.0) -> tuple[float, float]:
    """Return (current_mb, peak_mb) for a single chunk load."""
    import librosa

    tracemalloc.start()
    librosa.load(video_path, sr=22050, mono=True, offset=0.0, duration=chunk_sec)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return current / 1e6, peak / 1e6


def main() -> None:
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <video_path> [chunk_sec=600]")
        sys.exit(1)

    video_path = sys.argv[1]
    chunk_sec = float(sys.argv[2]) if len(sys.argv) > 2 else 600.0
    warning_mb = 400.0

    print(f"Measuring RAM for chunk_sec={chunk_sec}s on: {video_path}")
    current_mb, peak_mb = measure(video_path, chunk_sec)

    print(f"  Current: {current_mb:.1f} MB")
    print(f"  Peak:    {peak_mb:.1f} MB  (warning threshold: {warning_mb:.0f} MB)")

    if peak_mb > warning_mb:
        print(
            f"  WARNING: peak {peak_mb:.1f} MB exceeds {warning_mb:.0f} MB"
            " - reduce chunk_sec before deploying"
        )
        sys.exit(1)
    else:
        print("  OK: within safe range for this VPS")


if __name__ == "__main__":
    main()
