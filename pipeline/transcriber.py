"""ASR transcription using faster-whisper (CTranslate2 backend).

Runs on CPU with int8 quantization. Expected throughput on a shared VPS:
  ~3-5x real-time with tiny model (45 min VOD → 10-15 min transcription)

Uses 16 kHz mono audio - separate sample rate from the energy pipeline (22050 Hz).
"""

WHISPER_MODEL_SIZE = "tiny"
WHISPER_SAMPLE_RATE = 16000  # ASR-optimized; energy pipeline uses 22050 Hz


def transcribe(
    video_path: str,
    max_seconds: float = 5400.0,
    language: str = "pt",
) -> list[dict]:
    """Transcribe audio from a video file using faster-whisper.

    Returns a list of segments:
      [{"start": float, "end": float, "text": str}, ...]

    Raises ImportError if faster-whisper is not installed.
    Raises RuntimeError if transcription fails (caller should catch and degrade).
    """
    from faster_whisper import WhisperModel

    model = WhisperModel(
        WHISPER_MODEL_SIZE,
        device="cpu",
        compute_type="int8",
    )

    segments_iter, _ = model.transcribe(
        video_path,
        language=language,
        beam_size=1,  # greedy decoding - fastest on CPU
        vad_filter=True,  # skip silent sections
        max_new_tokens=128,  # cap per segment to prevent runaway
    )

    result: list[dict] = []
    for seg in segments_iter:
        if seg.start > max_seconds:
            break
        result.append(
            {
                "start": round(seg.start, 2),
                "end": round(min(seg.end, max_seconds), 2),
                "text": seg.text.strip(),
            }
        )

    return result
