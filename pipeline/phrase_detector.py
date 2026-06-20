"""PT-BR phrase detection and transcript density scoring.

Signals extracted from ASR segments:
  1. excitement_phrase  - recognized LoL/CBLOL excitement terms (weight in scorer)
  2. emphasis           - repeated !! / ?? punctuation
  3. word_repetition    - immediate word repeats ("vai vai vai", "matou matou")
  4. transcript_density - chars/sec per segment (fast speech = exciting moment)

Phrase list tuned for PT-BR broadcasting (CBLOL casters, streamers):
  - no generic fillers ("que isso")
  - no interjections whisper-tiny transcribes inconsistently ("aaah", "uoooh")
  - matched on whole-word boundaries, so "ace" won't fire inside "aceitou"
"""

import re

EXCITEMENT_PHRASES = [
    # core mechanical / objective callouts
    "que jogada",
    "absurdo",
    "inacreditável",
    "pentakill",
    "quadrakill",
    "triplekill",
    "baron steal",
    "não acredito",
    "que carry",
    "dragon soul",
    "ace",
    "teamfight",
    "que flash",
    "outplay",
    "clutch",
    "virou",
    "virada",
    # objectives / map (PT-BR casters)
    "nashor",
    "baron",
    "dragão",
    "arauto",
    "torre",
    "inibidor",
    "nexus",
    "backdoor",
    "splitpush",
    # combat callouts very common in narration
    "matou",
    "pegou",
    "morreu",
    "fugiu",
    "segurou",
    "stun",
    "engage",
    "que pick",
    "que troca",
    "que roubo",
    "que ult",
    "que defesa",
    "que mecânica",
    "first blood",
    "double kill",
    "que reação",
    "que recall",
    "tá morto",
    "acabou",
    "fechou",
    "olha isso",
    "meu deus",
    "sensacional",
    "espetacular",
    # CBLOL caster / scene catchphrases (bordões)
    "rexpeita",
    "obliterado",
    "mitológico",
    "rato",
    "que time",
    "vamo",
    "vai vai vai",
]

# Two or more consecutive ! or ? - indicates emphasis, not casual speech
_EMPHASIS_RE = re.compile(r"[!?]{2,}")

# Immediate word repetition: "vai vai", "matou matou matou", etc.
_REPEAT_RE = re.compile(r"\b(\w+)(?:\s+\1\b)+", re.IGNORECASE)

# Whole-word matchers so short tokens ("ace", "stun") don't match substrings.
_PHRASE_RES = [re.compile(rf"\b{re.escape(p)}\b", re.IGNORECASE) for p in EXCITEMENT_PHRASES]

# Normalization factor: chars/sec at which density score reaches 1.0.
# Typical LoL caster during teamfight: ~4-6 chars/sec.
# CANONICAL SOURCE - scorer.py imports this constant instead of redefining it.
DENSITY_NORM = 4.0


def score_segments(segments: list[dict]) -> list[tuple[float, float]]:
    """Return (segment_start, phrase_score) for segments with detectable excitement.

    phrase_score = min(excitement_hits / 2.0, 1.0)
                 + min(emphasis_groups * 0.1, 0.3)
                 + min(repetition_groups * 0.1, 0.2)

    Only segments with score > 0 are returned.
    """
    result: list[tuple[float, float]] = []
    for seg in segments:
        text = seg.get("text", "")
        excitement_hits = sum(bool(rx.search(text)) for rx in _PHRASE_RES)
        emphasis_groups = len(_EMPHASIS_RE.findall(text))
        repetition_groups = len(_REPEAT_RE.findall(text))
        score = (
            min(excitement_hits / 2.0, 1.0)
            + min(emphasis_groups * 0.1, 0.3)
            + min(repetition_groups * 0.1, 0.2)
        )
        if score > 0:
            result.append((seg["start"], round(score, 3)))
    return result


def compute_transcript_density(segments: list[dict]) -> list[tuple[float, float]]:
    """Return (segment_start, chars_per_sec) for each non-empty segment.

    High chars/sec indicates fast commentary, correlated with exciting moments.
    Divide by DENSITY_NORM in the scorer to get a [0, 1] signal.
    """
    result: list[tuple[float, float]] = []
    for seg in segments:
        text = seg.get("text", "").strip()
        if not text:
            continue
        duration = max(seg["end"] - seg["start"], 0.1)
        density = len(text) / duration
        result.append((seg["start"], round(density, 2)))
    return result


def combine_signals(
    segments: list[dict],
    w_phrase: float = 0.6,
    w_density: float = 0.4,
) -> list[tuple[float, float]]:
    """Merge phrase and density signals into one [0, 1]-ish score per segment.

    Returns (segment_start, combined_score) for every segment, ordered as input.

    WARNING: the weights here (w_phrase=0.6, w_density=0.4) are NOT the same as
    PHRASE_WEIGHT/TRANSCRIPT_WEIGHT in scorer.py (0.15/0.20). Those are additive
    contributions on top of a scene+audio base score. This function produces a
    standalone combined signal in [0, 1] - a different scale entirely. Do not
    mix the two without re-tuning the weights.

    NOTE: not currently wired into scorer.py. If you add a consumer, add tests
    before shipping - the formula will silently diverge from scorer behavior.
    """
    phrase = dict(score_segments(segments))
    density = dict(compute_transcript_density(segments))
    out: list[tuple[float, float]] = []
    for seg in segments:
        start = seg["start"]
        p = min(phrase.get(start, 0.0), 1.0)
        d = min(density.get(start, 0.0) / DENSITY_NORM, 1.0)
        out.append((start, round(w_phrase * p + w_density * d, 3)))
    return out
