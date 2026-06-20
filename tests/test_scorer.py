"""Unit tests for pipeline/scorer.py - Phase 2 behavior.

Phase 2 constants:
  SCENE_SCORE      = 0.35  (was 0.5 in Phase 1)
  AUDIO_WEIGHT     = 0.6
  CONVERGENCE_BONUS = 0.15
  MIN_SCORE        = 0.45

Key behavioral change from Phase 1:
  scene-only score = 0.35 < MIN_SCORE 0.45 → FILTERED
  audio-only (energy > 0.75): 0.45+ → passes
  scene + audio + convergence: 0.35 + audio + 0.15 → passes even with weak audio

Stubs out scenedetect and librosa so tests run without Docker.
"""

import sys
from unittest.mock import MagicMock, patch

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
):
    sys.modules.setdefault(_mod, MagicMock())

from pipeline.scorer import (  # noqa: E402
    AUDIO_WEIGHT,
    CONVERGENCE_BONUS,
    MIN_SCORE,
    SCENE_SCORE,
    score_highlights,
)


def _run(scenes=None, spikes=None, **kwargs):
    with (
        patch("pipeline.scorer.detect_scenes", return_value=scenes or []),
        patch("pipeline.scorer.get_audio_energy_spikes", return_value=spikes or []),
    ):
        return score_highlights("fake.mp4", **kwargs)


# ─── Constants ────────────────────────────────────────────────────────────────


class TestConstants:
    def test_min_score(self):
        assert MIN_SCORE == 0.45

    def test_scene_score_phase2(self):
        assert SCENE_SCORE == 0.35

    def test_audio_weight(self):
        assert AUDIO_WEIGHT == 0.6

    def test_convergence_bonus(self):
        assert CONVERGENCE_BONUS == 0.15


# ─── MIN_SCORE filter ─────────────────────────────────────────────────────────


class TestMinScore:
    def test_scene_only_filtered_phase2(self):
        # SCENE_SCORE 0.35 < MIN_SCORE 0.45 → filtered (key Phase 2 change)
        results = _run(scenes=[10.0])
        assert results == []

    def test_audio_below_threshold_filtered(self):
        # energy=0.74 → 0.74 * 0.6 = 0.444 < 0.45 → filtered
        results = _run(spikes=[(20.0, 0.74)])
        assert results == []

    def test_audio_just_above_threshold_passes(self):
        # energy=0.76 → 0.76 * 0.6 = 0.456 > 0.45 → passes
        results = _run(spikes=[(20.0, 0.76)])
        assert len(results) == 1

    def test_strong_audio_passes(self):
        results = _run(spikes=[(30.0, 0.9)])
        assert len(results) == 1

    def test_empty_returns_empty(self):
        assert _run() == []

    def test_scene_plus_weak_audio_passes_via_convergence(self):
        # scene (0.35) + audio (energy=0.62 → 0.372) + convergence (0.15) = 0.872 → passes
        # Both signals are weak individually; together they pass.
        results = _run(scenes=[15.0], spikes=[(15.0, 0.62)])
        assert len(results) == 1

    def test_scene_plus_audio_below_audio_threshold_still_filtered(self):
        # audio energy=0.0 → audio score 0.0 → no audio_spike registered in candidates
        # scene alone = 0.35 → filtered even with convergence (no convergence without audio)
        results = _run(scenes=[15.0], spikes=[])
        assert results == []


# ─── Convergence bonus ────────────────────────────────────────────────────────


class TestConvergencebonus:
    def test_convergence_bonus_added_to_score(self):
        # scene (0.35) + audio (energy=0.9 → 0.54) = 0.89 + bonus (0.15) = 1.04
        results = _run(scenes=[10.0], spikes=[(10.0, 0.9)])
        assert results[0]["raw_score"] > 1.0  # convergence pushed it past 1.0

    def test_convergence_reason_appended(self):
        results = _run(scenes=[10.0], spikes=[(10.0, 0.9)])
        assert "convergence" in results[0]["reason"]

    def test_no_convergence_for_audio_only(self):
        results = _run(spikes=[(10.0, 0.9)])
        assert "convergence" not in results[0]["reason"]

    def test_no_convergence_for_scene_only(self):
        # scene-only is filtered anyway, but confirm logic
        results = _run(scenes=[10.0], spikes=[])
        assert results == []

    def test_convergence_confidence_capped_at_one(self):
        results = _run(scenes=[10.0], spikes=[(10.0, 1.0)])
        assert results[0]["confidence"] == 1.0

    def test_convergence_raw_score_not_capped(self):
        # scene (0.35) + audio (1.0*0.6=0.6) + bonus (0.15) = 1.1
        results = _run(scenes=[10.0], spikes=[(10.0, 1.0)])
        assert results[0]["raw_score"] == round(0.35 + 0.6 + 0.15, 3)

    def test_reason_format_audio_plus_convergence(self):
        results = _run(spikes=[(10.0, 0.9)])
        reason = results[0]["reason"]
        assert "audio_spike" in reason
        assert "convergence" not in reason  # audio-only has no convergence

    def test_reason_format_combined(self):
        results = _run(scenes=[10.0], spikes=[(10.0, 0.9)])
        reason = results[0]["reason"]
        assert "audio_spike" in reason
        assert "scene_change" in reason
        assert "convergence" in reason


# ─── NMS ──────────────────────────────────────────────────────────────────────


class TestNMS:
    def _spike_scene(self, t: float, energy: float = 0.9):
        """Shorthand: scene + audio at the same timestamp."""
        return {"scenes": [t], "spikes": [(t, energy)]}

    def test_two_combined_within_20s_keeps_highest(self):
        # 10.0: scene+audio (0.9 energy), 15.0: scene+audio (0.7 energy)
        # 5s apart → same window → keep 10.0 (higher score)
        results = _run(scenes=[10.0, 15.0], spikes=[(10.0, 0.9), (15.0, 0.7)])
        assert len(results) == 1
        assert results[0]["start_seconds"] == 10.0

    def test_two_combined_beyond_20s_both_kept(self):
        results = _run(scenes=[10.0, 35.0], spikes=[(10.0, 0.9), (35.0, 0.9)])
        assert len(results) == 2

    def test_nms_selects_highest_within_window(self):
        # 10.0: audio only (energy=0.9 → 0.54)
        # 14.0: scene+audio (energy=0.9 → 0.35+0.54+0.15=1.04)
        # NMS: sorted by score desc → 14.0 wins
        results = _run(scenes=[14.0], spikes=[(10.0, 0.9), (14.0, 0.9)])
        assert len(results) == 1
        assert results[0]["start_seconds"] == 14.0

    def test_exactly_20s_apart_both_kept(self):
        results = _run(scenes=[10.0, 30.0], spikes=[(10.0, 0.9), (30.0, 0.9)])
        assert len(results) == 2

    def test_clustered_then_isolated(self):
        scenes = [5.0, 10.0, 15.0, 60.0]
        spikes = [(t, 0.9) for t in scenes]
        results = _run(scenes=scenes, spikes=spikes)
        assert len(results) == 2
        timestamps = {r["start_seconds"] for r in results}
        assert 60.0 in timestamps

    def test_audio_only_candidates_also_nms(self):
        # Two strong audio spikes 8s apart → NMS keeps only the strongest
        results = _run(spikes=[(10.0, 0.95), (18.0, 0.8)])
        assert len(results) == 1
        assert results[0]["start_seconds"] == 10.0


# ─── Output format ────────────────────────────────────────────────────────────


class TestOutputFormat:
    def test_results_chronological(self):
        scenes = [50.0, 30.0]
        spikes = [(50.0, 0.9), (30.0, 0.9)]
        results = _run(scenes=scenes, spikes=spikes)
        ts = [r["start_seconds"] for r in results]
        assert ts == sorted(ts)

    def test_result_has_required_keys(self):
        results = _run(spikes=[(10.0, 0.9)])
        r = results[0]
        for key in ("start_seconds", "confidence", "reason", "raw_score"):
            assert key in r

    def test_confidence_capped_at_one(self):
        results = _run(scenes=[10.0], spikes=[(10.0, 1.0)])
        assert results[0]["confidence"] == 1.0

    def test_raw_score_can_exceed_one(self):
        results = _run(scenes=[10.0], spikes=[(10.0, 1.0)])
        assert results[0]["raw_score"] > 1.0

    def test_max_suggestions_honored(self):
        scenes = [float(i * 30) for i in range(30)]
        spikes = [(t, 0.9) for t in scenes]
        results = _run(scenes=scenes, spikes=spikes)
        assert len(results) <= 15

    def test_confidence_rounded_to_3dp(self):
        results = _run(spikes=[(10.0, 0.9)])
        assert results[0]["confidence"] == round(results[0]["confidence"], 3)


# ─── max_seconds propagation ─────────────────────────────────────────────────


class TestMaxSeconds:
    def test_forwarded_to_detect_scenes(self):
        with (
            patch("pipeline.scorer.detect_scenes") as mock_detect,
            patch("pipeline.scorer.get_audio_energy_spikes", return_value=[]),
        ):
            mock_detect.return_value = []
            score_highlights("fake.mp4", max_seconds=5400.0)
            mock_detect.assert_called_once_with("fake.mp4", max_seconds=5400.0)

    def test_forwarded_to_audio_analyzer(self):
        with (
            patch("pipeline.scorer.detect_scenes", return_value=[]),
            patch("pipeline.scorer.get_audio_energy_spikes") as mock_audio,
        ):
            mock_audio.return_value = []
            score_highlights("fake.mp4", max_seconds=5400.0)
            mock_audio.assert_called_once_with("fake.mp4", max_seconds=5400.0)

    def test_default_is_5400(self):
        with (
            patch("pipeline.scorer.detect_scenes") as mock_detect,
            patch("pipeline.scorer.get_audio_energy_spikes", return_value=[]),
        ):
            mock_detect.return_value = []
            score_highlights("fake.mp4")
            _, kwargs = mock_detect.call_args
            assert kwargs.get("max_seconds") == 5400.0


# ─── Progress callback ────────────────────────────────────────────────────────


class TestProgressCallback:
    def test_called_at_60_80_90(self):
        # Phase 3 added a third stage: scenes(60) → audio(80) → asr/noop(90)
        calls = []
        _run(progress_callback=calls.append)
        assert 60 in calls
        assert 80 in calls
        assert 90 in calls

    def test_no_callback_does_not_raise(self):
        _run(spikes=[(10.0, 0.9)])
