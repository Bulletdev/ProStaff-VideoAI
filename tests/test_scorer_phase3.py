"""Phase 3 integration tests for pipeline/scorer.py.

Tests the Phase 3 signal integration (transcript_density, excitement_phrase)
and the graceful degradation when transcription fails at runtime.
All external calls mocked - no video files or whisper model needed.
"""

import sys
from unittest.mock import MagicMock, patch

# Stub heavy dependencies before any pipeline import.
# faster_whisper is stubbed so pipeline.transcriber imports cleanly;
# scenedetect/librosa are stubbed so scene_detector/audio_analyzer import cleanly.
for _mod in (
    "scenedetect",
    "scenedetect.detectors",
    "librosa",
    "librosa.feature",
    "numpy",
    "scipy",
    "cv2",
    "audioread",
    "soundfile",
    "numba",
    "faster_whisper",
):
    sys.modules.setdefault(_mod, MagicMock())

from pipeline.scorer import (  # noqa: E402
    PHRASE_WEIGHT,
    TRANSCRIPT_DENSITY_NORM,
    TRANSCRIPT_WEIGHT,
    _best_segment_score,
    score_highlights,
)


class TestPhase3Constants:
    def test_transcript_weight(self):
        assert TRANSCRIPT_WEIGHT == 0.20

    def test_phrase_weight(self):
        assert PHRASE_WEIGHT == 0.15

    def test_density_norm(self):
        assert TRANSCRIPT_DENSITY_NORM == 4.0


class TestGracefulDegradation:
    def test_disabled_by_default(self):
        # enable_transcription defaults to False - pipeline runs without ASR
        with (
            patch("pipeline.scorer.detect_scenes", return_value=[]),
            patch("pipeline.scorer.get_audio_energy_spikes", return_value=[(10.0, 0.9)]),
        ):
            results = score_highlights("fake.mp4")
        assert len(results) == 1
        assert "transcript_density" not in results[0]["reason"]
        assert "excitement_phrase" not in results[0]["reason"]

    def test_runtime_error_degrades_gracefully(self):
        # If transcription fails at runtime (e.g. model not loaded), pipeline continues.
        # The except Exception: pass in scorer catches and degraded to 2-signal scoring.
        with (
            patch("pipeline.scorer.detect_scenes", return_value=[]),
            patch("pipeline.scorer.get_audio_energy_spikes", return_value=[(10.0, 0.9)]),
            patch("pipeline.scorer.transcribe", side_effect=RuntimeError("model load failed")),
        ):
            results = score_highlights("fake.mp4", enable_transcription=True)
        assert len(results) == 1
        assert "transcript_density" not in results[0]["reason"]

    def test_oom_error_degrades_gracefully(self):
        # MemoryError during transcription (large VOD on low-RAM host)
        with (
            patch("pipeline.scorer.detect_scenes", return_value=[]),
            patch("pipeline.scorer.get_audio_energy_spikes", return_value=[(10.0, 0.9)]),
            patch("pipeline.scorer.transcribe", side_effect=MemoryError("OOM")),
        ):
            results = score_highlights("fake.mp4", enable_transcription=True)
        assert len(results) == 1


class TestTranscriptDensitySignal:
    def test_high_density_boosts_score(self):
        # Audio spike at 10.0 + high-density transcript segment → score increases.
        # audio contribution: 0.9 * 0.6 = 0.54
        # density contribution: min(8.0/4.0, 1.0) * 0.20 = 0.20
        # total: 0.74
        with (
            patch("pipeline.scorer.detect_scenes", return_value=[]),
            patch("pipeline.scorer.get_audio_energy_spikes", return_value=[(10.0, 0.9)]),
            patch("pipeline.scorer.transcribe", return_value=[]),
            patch("pipeline.scorer.score_segments", return_value=[]),
            patch("pipeline.scorer.compute_transcript_density", return_value=[(10.0, 8.0)]),
        ):
            results = score_highlights("fake.mp4", enable_transcription=True)

        assert len(results) == 1
        assert "transcript_density" in results[0]["reason"]
        assert results[0]["raw_score"] > 0.54

    def test_low_density_does_not_add_reason(self):
        # density=0 → no transcript_density reason added
        with (
            patch("pipeline.scorer.detect_scenes", return_value=[]),
            patch("pipeline.scorer.get_audio_energy_spikes", return_value=[(10.0, 0.9)]),
            patch("pipeline.scorer.transcribe", return_value=[]),
            patch("pipeline.scorer.score_segments", return_value=[]),
            patch("pipeline.scorer.compute_transcript_density", return_value=[]),
        ):
            results = score_highlights("fake.mp4", enable_transcription=True)

        assert len(results) == 1
        assert "transcript_density" not in results[0]["reason"]

    def test_density_capped_at_norm(self):
        # density=100 (extreme) → density_norm=1.0, adds exactly TRANSCRIPT_WEIGHT
        with (
            patch("pipeline.scorer.detect_scenes", return_value=[]),
            patch("pipeline.scorer.get_audio_energy_spikes", return_value=[(5.0, 0.9)]),
            patch("pipeline.scorer.transcribe", return_value=[]),
            patch("pipeline.scorer.score_segments", return_value=[]),
            patch("pipeline.scorer.compute_transcript_density", return_value=[(5.0, 100.0)]),
        ):
            results = score_highlights("fake.mp4", enable_transcription=True)

        # audio(0.54) + density(0.20) = 0.74
        assert abs(results[0]["raw_score"] - 0.74) < 0.01


class TestExcitementPhraseSignal:
    def test_excitement_phrase_boosts_score(self):
        with (
            patch("pipeline.scorer.detect_scenes", return_value=[]),
            patch("pipeline.scorer.get_audio_energy_spikes", return_value=[(20.0, 0.9)]),
            patch("pipeline.scorer.transcribe", return_value=[]),
            patch("pipeline.scorer.score_segments", return_value=[(20.0, 0.8)]),
            patch("pipeline.scorer.compute_transcript_density", return_value=[]),
        ):
            results = score_highlights("fake.mp4", enable_transcription=True)

        assert len(results) == 1
        assert "excitement_phrase" in results[0]["reason"]

    def test_reason_includes_both_phase3_signals(self):
        with (
            patch("pipeline.scorer.detect_scenes", return_value=[]),
            patch("pipeline.scorer.get_audio_energy_spikes", return_value=[(15.0, 0.9)]),
            patch("pipeline.scorer.transcribe", return_value=[]),
            patch("pipeline.scorer.score_segments", return_value=[(15.0, 1.0)]),
            patch("pipeline.scorer.compute_transcript_density", return_value=[(15.0, 5.0)]),
        ):
            results = score_highlights("fake.mp4", enable_transcription=True)

        reason = results[0]["reason"]
        assert "excitement_phrase" in reason
        assert "transcript_density" in reason

    def test_phrase_score_capped_at_phrase_weight(self):
        # phrase_score=10.0 → capped at 1.0 → adds exactly PHRASE_WEIGHT
        with (
            patch("pipeline.scorer.detect_scenes", return_value=[]),
            patch("pipeline.scorer.get_audio_energy_spikes", return_value=[(5.0, 0.9)]),
            patch("pipeline.scorer.transcribe", return_value=[]),
            patch("pipeline.scorer.score_segments", return_value=[(5.0, 10.0)]),
            patch("pipeline.scorer.compute_transcript_density", return_value=[]),
        ):
            results = score_highlights("fake.mp4", enable_transcription=True)

        # audio(0.54) + phrase(0.15) = 0.69
        assert abs(results[0]["raw_score"] - 0.69) < 0.01

    def test_excitement_phrase_segment_within_radius(self):
        # Phrase segment at 17.0, candidate at 15.0 - within SEGMENT_MATCH_RADIUS (3.0)
        with (
            patch("pipeline.scorer.detect_scenes", return_value=[]),
            patch("pipeline.scorer.get_audio_energy_spikes", return_value=[(15.0, 0.9)]),
            patch("pipeline.scorer.transcribe", return_value=[]),
            patch("pipeline.scorer.score_segments", return_value=[(17.0, 0.8)]),
            patch("pipeline.scorer.compute_transcript_density", return_value=[]),
        ):
            results = score_highlights("fake.mp4", enable_transcription=True)

        assert "excitement_phrase" in results[0]["reason"]

    def test_excitement_phrase_segment_outside_radius_ignored(self):
        # Phrase segment at 30.0, candidate at 15.0 - outside radius (>3.0) → ignored
        with (
            patch("pipeline.scorer.detect_scenes", return_value=[]),
            patch("pipeline.scorer.get_audio_energy_spikes", return_value=[(15.0, 0.9)]),
            patch("pipeline.scorer.transcribe", return_value=[]),
            patch("pipeline.scorer.score_segments", return_value=[(30.0, 0.8)]),
            patch("pipeline.scorer.compute_transcript_density", return_value=[]),
        ):
            results = score_highlights("fake.mp4", enable_transcription=True)

        assert "excitement_phrase" not in results[0]["reason"]


class TestBestSegmentScore:
    def test_exact_match(self):
        scored = [(10.0, 0.8), (20.0, 0.5)]
        assert _best_segment_score(10.0, scored) == 0.8

    def test_within_radius(self):
        scored = [(10.0, 0.8)]
        assert _best_segment_score(12.0, scored, radius=3.0) == 0.8

    def test_outside_radius_returns_zero(self):
        scored = [(10.0, 0.8)]
        assert _best_segment_score(15.0, scored, radius=3.0) == 0.0

    def test_returns_max_within_radius(self):
        scored = [(9.0, 0.5), (10.0, 0.9), (11.0, 0.3)]
        assert _best_segment_score(10.0, scored, radius=3.0) == 0.9

    def test_empty_scored_returns_zero(self):
        assert _best_segment_score(10.0, []) == 0.0
