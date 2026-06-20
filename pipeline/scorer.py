from .audio_analyzer import get_audio_energy_spikes
from .scene_detector import detect_scenes

# ── Phase 3 imports (optional - degrade gracefully if not installed) ───────────
try:
    from .phrase_detector import DENSITY_NORM as TRANSCRIPT_DENSITY_NORM
    from .phrase_detector import compute_transcript_density, score_segments
    from .transcriber import transcribe

    _PHASE3_AVAILABLE = True
except ImportError:
    transcribe = score_segments = compute_transcript_density = None  # type: ignore[assignment]
    TRANSCRIPT_DENSITY_NORM = 4.0  # fallback when phrase_detector is not available
    _PHASE3_AVAILABLE = False

# ── Phase 1/2 constants ───────────────────────────────────────────────────────

# Minimum raw score (after all bonuses) to include a candidate.
# Scene-only = SCENE_SCORE 0.35 < MIN_SCORE 0.45 → filtered.
# Scene+audio receives CONVERGENCE_BONUS → combined weak signals can pass.
MIN_SCORE = 0.45

# Phase 2: lowered from 0.5 so scene-only is filtered; NMS handles clustering.
SCENE_SCORE = 0.35
AUDIO_WEIGHT = 0.6

# Additive bonus when scene_change and audio_spike both fire on the same timestamp.
# Fixed value avoids disproportionate reward for already-loud audio.
CONVERGENCE_BONUS = 0.15

# ── Phase 3 constants ─────────────────────────────────────────────────────────

# TRANSCRIPT_DENSITY_NORM is imported from phrase_detector.DENSITY_NORM (canonical source).
# The fallback literal above only activates when phrase_detector is not installed.

# Additive contribution from ASR signals (enabled only when enable_transcription=True).
TRANSCRIPT_WEIGHT = 0.20  # transcript_density signal
PHRASE_WEIGHT = 0.15  # excitement_phrase signal

# Search radius (seconds) to match a candidate timestamp to a transcript segment.
# Segments can start up to SEGMENT_MATCH_RADIUS before or after the candidate.
SEGMENT_MATCH_RADIUS = 3.0


def _apply_nms(results: list[dict], window_sec: float = 20.0) -> list[dict]:
    """Non-maximum suppression over results sorted by raw_score descending.

    Operates on Format 4 dicts - requires 'start_seconds' and 'raw_score' keys.
    Keeps the highest-scoring candidate within each 20s window; drops the rest.
    LoL teamfights last 10-30s, so 20s prevents same-fight duplicates while
    allowing consecutive fights separated by ~30s.
    """
    kept: list[dict] = []
    for c in results:
        too_close = any(abs(c["start_seconds"] - k["start_seconds"]) < window_sec for k in kept)
        if not too_close:
            kept.append(c)
    return kept


def _best_segment_score(
    ts: float,
    scored_segments: list[tuple[float, float]],
    radius: float = SEGMENT_MATCH_RADIUS,
) -> float:
    """Return the max score from segments within ±radius seconds of ts.

    ASR segments are variable-length and may not align to 1s hop boundaries.
    This tolerant lookup avoids false misses from timing drift.
    """
    candidates = [score for seg_ts, score in scored_segments if abs(seg_ts - ts) <= radius]
    return max(candidates) if candidates else 0.0


def score_highlights(
    video_path: str,
    max_suggestions: int = 15,
    max_seconds: float = 5400.0,
    progress_callback=None,
    enable_transcription: bool = False,
    language: str = "pt",
) -> list[dict]:
    """Combine scene, audio, and (optionally) ASR signals into highlight suggestions.

    Internal data flow (four formats):
      Format 1 - scene timestamps:    list[float]
      Format 2 - audio spikes:        list[tuple[float, float]]  (ts, energy)
      Format 3 - internal candidates: dict[float, dict]           keyed by rounded ts
      Format 4 - output results:      list[dict]  with start_seconds/confidence/reason/raw_score

    Phase 3 (enable_transcription=True): adds transcript_density and excitement_phrase
    signals from faster-whisper. Degrades gracefully if faster-whisper is not installed
    (checked at import time via _PHASE3_AVAILABLE) or if transcription fails at runtime.

    progress_callback(pct: int) called after each pipeline stage.
    """
    # Format 1
    scenes = detect_scenes(video_path, max_seconds=max_seconds)
    if progress_callback:
        progress_callback(60)

    # Format 2
    spikes = get_audio_energy_spikes(video_path, max_seconds=max_seconds)
    if progress_callback:
        progress_callback(80)

    # Phase 3: transcription (slow, optional - ~3-5x real-time on CPU)
    phrase_by_ts: list[tuple[float, float]] = []
    density_by_ts: list[tuple[float, float]] = []

    if enable_transcription and _PHASE3_AVAILABLE:
        try:
            segments = transcribe(video_path, max_seconds=max_seconds, language=language)
            phrase_by_ts = score_segments(segments)
            density_by_ts = compute_transcript_density(segments)
        except Exception:  # noqa: S110 - transcription is optional; failure degrades to 2-signal pipeline
            pass

    if progress_callback:
        progress_callback(90)

    # Build Format 3
    candidates: dict[float, dict] = {}

    for t in scenes:
        key = round(t, 1)
        if key not in candidates:
            candidates[key] = {"score": 0.0, "reasons": []}
        candidates[key]["score"] += SCENE_SCORE
        candidates[key]["reasons"].append("scene_change")

    for t, energy in spikes:
        key = round(t, 1)
        if key not in candidates:
            candidates[key] = {"score": 0.0, "reasons": []}
        candidates[key]["score"] += energy * AUDIO_WEIGHT
        candidates[key]["reasons"].append("audio_spike")

    # Convergence bonus: scene + audio on the same timestamp
    for data in candidates.values():
        reasons = set(data["reasons"])
        if "scene_change" in reasons and "audio_spike" in reasons:
            data["score"] += CONVERGENCE_BONUS
            data["reasons"].append("convergence")

    # Phase 3: ASR signals (if available)
    for key, data in candidates.items():
        density = _best_segment_score(key, density_by_ts)
        if density > 0:
            density_norm = min(density / TRANSCRIPT_DENSITY_NORM, 1.0)
            data["score"] += density_norm * TRANSCRIPT_WEIGHT
            data["reasons"].append("transcript_density")

        phrase = _best_segment_score(key, phrase_by_ts)
        if phrase > 0:
            phrase_norm = min(phrase, 1.0)
            data["score"] += phrase_norm * PHRASE_WEIGHT
            data["reasons"].append("excitement_phrase")

    # Convert to Format 4, apply MIN_SCORE filter
    results: list[dict] = []
    for ts, data in candidates.items():
        raw = data["score"]
        if raw < MIN_SCORE:
            continue
        # Build reason string: non-convergence signals first, then convergence
        core_reasons = sorted({r for r in data["reasons"] if r != "convergence"})
        reason = "+".join(core_reasons)
        if "convergence" in data["reasons"]:
            reason += "+convergence"
        results.append(
            {
                "start_seconds": ts,
                "confidence": round(min(raw, 1.0), 3),
                "reason": reason,
                "raw_score": round(raw, 3),
            }
        )

    # Sort descending by score, apply NMS, then cap at max_suggestions
    results.sort(key=lambda x: x["raw_score"], reverse=True)
    results = _apply_nms(results)
    results = results[:max_suggestions]

    # Return chronologically ordered
    return sorted(results, key=lambda x: x["start_seconds"])
