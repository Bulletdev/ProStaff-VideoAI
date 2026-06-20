"""Unit tests for pipeline/audio_analyzer._local_normalize.

Tests the local normalization function in isolation - no librosa calls,
no video files needed. get_audio_energy_spikes is not tested here because
it requires an actual audio file (exercise in Docker with validate_ram_peak.py).
"""

import sys
from unittest.mock import MagicMock

for _mod in ("librosa", "librosa.feature", "numpy", "scipy", "audioread", "soundfile", "numba"):
    sys.modules.setdefault(_mod, MagicMock())

from pipeline.audio_analyzer import _local_normalize  # noqa: E402


class TestLocalNormalize:
    def test_empty_returns_empty(self):
        assert _local_normalize([]) == []

    def test_single_value_normalizes_to_one(self):
        # Only value is its own p95 → normalized to 1.0
        result = _local_normalize([(0.0, 0.5)])
        assert len(result) == 1
        assert result[0][1] == 1.0

    def test_uniform_values_all_normalize_to_one(self):
        raw = [(float(i), 0.5) for i in range(10)]
        result = _local_normalize(raw)
        for _, e in result:
            assert e == 1.0

    def test_timestamps_preserved(self):
        raw = [(0.0, 0.3), (10.0, 0.6), (20.0, 0.9)]
        result = _local_normalize(raw)
        assert [t for t, _ in result] == [0.0, 10.0, 20.0]

    def test_outlier_does_not_suppress_distant_values(self):
        # Extreme spike at t=0, quieter section at t=600 (beyond 300s window)
        # Global normalization would make t=600 nearly invisible.
        # Local normalization: each region normalized independently.
        raw = [(0.0, 10.0)] + [(float(600 + i * 2), 0.3) for i in range(10)]
        result = _local_normalize(raw, window_sec=300.0)

        # Values at t≥600 should be normalized relative to their local window
        # (which does NOT include the spike at t=0), so they should be ~1.0
        distant_values = [e for t, e in result if t >= 600.0]
        assert all(e >= 0.9 for e in distant_values), f"Distant values suppressed: {distant_values}"

    def test_outlier_gets_value_above_one(self):
        # A value above the local p95 gets locally-normalized value > 1.0.
        # With 21 values: 20 quiet (0.1) + 1 extreme spike (5.0).
        # sorted[0..19] = 0.1, sorted[20] = 5.0
        # p95_idx = int(21 * 0.95) = 19 → norm_factor = 0.1
        # spike normalized = 5.0 / 0.1 = 50.0 >> 1.0
        raw = [(float(i), 0.1) for i in range(20)] + [(20.0, 5.0)]
        result = _local_normalize(raw, window_sec=300.0)
        spike_val = [e for t, e in result if t == 20.0][0]
        assert spike_val > 1.0

    def test_window_boundary_isolation(self):
        # Two groups separated by more than window_sec (300s)
        # Each group should normalize relative to itself only
        group_a = [(float(i), 0.5) for i in range(5)]  # t=0..4, energy=0.5
        group_b = [(float(400 + i), 0.1) for i in range(5)]  # t=400..404, energy=0.1
        raw = group_a + group_b
        result = _local_normalize(raw, window_sec=300.0)

        result_dict = dict(result)
        # Both groups should normalize independently - each ~1.0 at their max
        a_values = [result_dict[float(i)] for i in range(5)]
        b_values = [result_dict[float(400 + i)] for i in range(5)]
        assert all(abs(v - 1.0) < 0.01 for v in a_values), f"Group A: {a_values}"
        assert all(abs(v - 1.0) < 0.01 for v in b_values), f"Group B: {b_values}"

    def test_returns_rounded_to_4_decimal_places(self):
        raw = [(0.0, 0.33333), (1.0, 0.66666)]
        result = _local_normalize(raw)
        for _, e in result:
            assert e == round(e, 4)
