"""Unit tests for pipeline/phrase_detector.py.

No external dependencies - phrase detection is pure Python.
"""

from pipeline.phrase_detector import (
    DENSITY_NORM,
    EXCITEMENT_PHRASES,
    compute_transcript_density,
    score_segments,
)


def _seg(start: float, end: float, text: str) -> dict:
    return {"start": start, "end": end, "text": text}


class TestScoreSegments:
    def test_empty_segments_returns_empty(self):
        assert score_segments([]) == []

    def test_no_excitement_returns_empty(self):
        segs = [_seg(0.0, 3.0, "o player farmou minions no bot")]
        assert score_segments(segs) == []

    def test_single_excitement_phrase_detected(self):
        segs = [_seg(10.0, 13.0, "que jogada incrivel do toplaner")]
        result = score_segments(segs)
        assert len(result) == 1
        ts, score = result[0]
        assert ts == 10.0
        assert score > 0

    def test_multiple_phrases_increase_score(self):
        segs = [_seg(5.0, 8.0, "pentakill absurdo inacreditável")]
        result = score_segments(segs)
        single = score_segments([_seg(5.0, 8.0, "pentakill")])
        assert result[0][1] > single[0][1]

    def test_score_capped_at_1_3(self):
        # Max: excitement capped at 1.0 + emphasis capped at 0.3 = 1.3
        segs = [_seg(0.0, 2.0, "pentakill absurdo inacreditável teamfight que carry!!??!!")]
        result = score_segments(segs)
        assert result[0][1] <= 1.3

    def test_emphasis_punctuation_detected(self):
        segs = [_seg(0.0, 2.0, "OLHA ISSO!!")]
        result = score_segments(segs)
        assert len(result) == 1
        assert result[0][1] > 0

    def test_single_exclamation_not_emphasis(self):
        # Single ! does not trigger emphasis regex (requires 2+)
        segs = [_seg(0.0, 2.0, "boa!")]
        assert score_segments(segs) == []

    def test_phrase_case_insensitive(self):
        segs = [_seg(0.0, 2.0, "QUE JOGADA")]
        result = score_segments(segs)
        assert len(result) == 1

    def test_timestamp_comes_from_segment_start(self):
        segs = [_seg(42.5, 45.0, "pentakill")]
        ts, _ = score_segments(segs)[0]
        assert ts == 42.5

    def test_known_bad_phrases_not_in_list(self):
        # "que isso" is too generic - must not be in EXCITEMENT_PHRASES
        assert "que isso" not in EXCITEMENT_PHRASES

    def test_multiple_segments_scored_independently(self):
        segs = [
            _seg(0.0, 3.0, "que jogada"),
            _seg(10.0, 13.0, "farmando tranquilo"),
            _seg(30.0, 33.0, "pentakill absurdo"),
        ]
        result = score_segments(segs)
        timestamps = [ts for ts, _ in result]
        assert 0.0 in timestamps
        assert 30.0 in timestamps
        assert 10.0 not in timestamps


class TestComputeTranscriptDensity:
    def test_empty_returns_empty(self):
        assert compute_transcript_density([]) == []

    def test_empty_text_skipped(self):
        segs = [_seg(0.0, 5.0, "")]
        assert compute_transcript_density(segs) == []

    def test_whitespace_only_skipped(self):
        segs = [_seg(0.0, 5.0, "   ")]
        assert compute_transcript_density(segs) == []

    def test_density_chars_per_sec(self):
        # 10 chars over 5s = 2.0 chars/sec
        segs = [_seg(0.0, 5.0, "abcdefghij")]
        result = compute_transcript_density(segs)
        assert len(result) == 1
        ts, density = result[0]
        assert ts == 0.0
        assert density == 2.0

    def test_high_density_fast_commentary(self):
        # Long text over short segment = high density
        text = "que jogada incrivel e o campeao virou completamente o teamfight"  # 64 chars
        segs = [_seg(5.0, 7.0, text)]  # 2s duration → ~32 chars/sec
        ts, density = compute_transcript_density(segs)[0]
        assert density > DENSITY_NORM  # above saturation point

    def test_density_normalization_constant(self):
        # DENSITY_NORM is the saturation point (score = 1.0 in scorer)
        assert DENSITY_NORM == 4.0

    def test_zero_duration_uses_minimum(self):
        # start == end → duration forced to 0.1s to avoid division by zero
        segs = [_seg(10.0, 10.0, "abc")]
        result = compute_transcript_density(segs)
        assert len(result) == 1
        _, density = result[0]
        assert density == round(3 / 0.1, 2)

    def test_timestamps_preserved(self):
        segs = [_seg(15.0, 18.0, "texto"), _seg(40.0, 43.0, "mais texto")]
        result = compute_transcript_density(segs)
        ts_list = [ts for ts, _ in result]
        assert 15.0 in ts_list
        assert 40.0 in ts_list
