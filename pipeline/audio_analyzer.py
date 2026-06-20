import bisect

import librosa


def _local_normalize(
    raw: list[tuple[float, float]],
    window_sec: float = 300.0,
) -> list[tuple[float, float]]:
    """Normalize each sample by the 95th-percentile of its ±150s local window.

    Prevents a single extreme spike (e.g. crowd noise in the first teamfight)
    from suppressing all detections elsewhere via global normalization.
    Values above the local p95 get a result > 1.0 - intentional, they are the
    strongest candidates in their region and should pass the energy_threshold
    easily.
    """
    if not raw:
        return raw
    half = window_sec / 2
    timestamps = [t for t, _ in raw]
    energies = [e for _, e in raw]

    result = []
    for ts, e in raw:
        lo = bisect.bisect_left(timestamps, ts - half)
        hi = bisect.bisect_right(timestamps, ts + half)
        window_vals = sorted(energies[lo:hi])

        if not window_vals:
            result.append((ts, 0.0))
            continue

        # 95th-percentile of local window; fall back to local max if p95 is 0
        p95_idx = min(int(len(window_vals) * 0.95), len(window_vals) - 1)
        norm_factor = window_vals[p95_idx] or window_vals[-1]

        result.append((ts, round(e / norm_factor, 4) if norm_factor > 0 else 0.0))

    return result


def get_audio_energy_spikes(
    video_path: str,
    window_sec: float = 1.0,
    max_seconds: float = 5400.0,
    chunk_sec: float = 600.0,
    energy_threshold: float = 0.6,
    local_norm_window_sec: float = 300.0,
) -> list[tuple[float, float]]:
    """Return (timestamp, locally-normalised energy) pairs for high-energy moments.

    Two-pass approach:
      Pass 1 - chunk-load the audio to bound peak RAM (~283 MB per 600s chunk).
      Pass 2 - local normalisation (±150s, p95) so a single extreme spike does
               not suppress detections in quieter sections of the VOD.

    energy_threshold applies to locally-normalised values; spikes at or below
    threshold are silently dropped (dead zone documented in scorer.py).
    """
    sr = 22050
    hop_length = int(sr * window_sec)

    # Pass 1: accumulate raw RMS per chunk (only floats kept between chunks)
    raw: list[tuple[float, float]] = []
    offset = 0.0
    while offset < max_seconds:
        load_dur = min(chunk_sec, max_seconds - offset)
        y, _ = librosa.load(video_path, sr=sr, mono=True, offset=offset, duration=load_dur)
        if len(y) == 0:
            break
        chunk_rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
        for i, e in enumerate(chunk_rms):
            ts = offset + (i * hop_length) / sr
            if ts <= max_seconds:
                raw.append((ts, float(e)))
        offset += load_dur

    if not raw:
        return []

    # Pass 2: local normalization then threshold
    normalized = _local_normalize(raw, window_sec=local_norm_window_sec)
    return [(ts, round(e, 4)) for ts, e in normalized if e > energy_threshold]
