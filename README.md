
```
>  ██╗   ██╗██╗██████╗ ███████╗ ██████╗  █████╗ ██╗
>  ██║   ██║██║██╔══██╗██╔════╝██╔═══██╗██╔══██╗██║
>  ██║   ██║██║██║  ██║█████╗  ██║   ██║███████║██║
>  ╚██╗ ██╔╝██║██║  ██║██╔══╝  ██║   ██║██╔══██║██║
>   ╚████╔╝ ██║██████╔╝███████╗╚██████╔╝██║  ██║██║
>    ╚═══╝  ╚═╝╚═════╝ ╚══════╝ ╚═════╝ ╚═╝  ╚═╝╚═╝
              VideoAI - VOD Analysis Pipeline - ProStaff.gg
```

<div align="center">

[![Python](https://img.shields.io/badge/python-3.11-3776AB?logo=python)](https://python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Bandit](https://img.shields.io/badge/security-bandit-yellow)](https://bandit.readthedocs.io/)
[![License: Proprietary](https://img.shields.io/badge/License-Proprietary-red.svg)](#)

</div>

---

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  PROSTAFF VIDEOAI - Python 3.11 / FastAPI (Standalone Microservice)          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  VOD analysis pipeline for the ProStaff.gg platform.                         ║
║  Downloads a video, runs a multi-signal pipeline, returns highlight stamps.  ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

---

<details>
<summary><kbd>▶ Key Features (click to expand)</kbd></summary>

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  [■] Scene Detection       - ContentDetector (threshold 22, min_scene 15)   │
│  [■] Audio Energy          - librosa RMS, 1s hop, local p95 normalization   │
│  [■] Convergence Bonus     - +0.15 when scene + audio fire on same second   │
│  [■] ASR Transcription     - faster-whisper tiny, PT-BR (optional, slow)    │
│  [■] Excitement Phrases    - 15 validated PT-BR LoL terms + emphasis regex  │
│  [■] Transcript Density    - chars/sec signal (fast commentary detection)   │
│  [■] Non-Maximum Suppression - 20s window, deduplicates same-fight events   │
│  [■] Chunked Audio Load    - 600s chunks, ~283MB peak RAM per chunk         │
│  [■] Clip Export           - FFmpeg seek+cut, async, download endpoint      │
│  [■] FileLock              - OS advisory lock, cross-process job serializer │
│  [■] JWT Auth              - Internal HS256 token, shared with prostaff-api │
│  [■] SQLite persistence    - Job state, progress (0-100), error messages    │
│  [■] Graceful degradation  - Each signal is independent; none blocks others │
│  [■] Max 90min VOD support - max_seconds=5400 across all pipeline stages    │
└─────────────────────────────────────────────────────────────────────────────┘
```

</details>

---

## Table of Contents

```
┌──────────────────────────────────────────────────────┐
│  01 · Quick Start                                    │
│  02 · Technology Stack                               │
│  03 · Architecture                                   │
│  04 · Pipeline Internals                             │
│  05 · API Endpoints                                  │
│  06 · Authentication                                 │
│  07 · Environment Variables                          │
│  08 · Testing                                        │
│  09 · Performance & Limits                           │
│  10 · Integration with ProStaff                      │
│  11 · Deployment                                     │
│  12 · Code Quality & Security                        │
└──────────────────────────────────────────────────────┘
```

---

## 01 · Quick Start

<details>
<summary><kbd>▶ Option 1: Docker (Recommended)</kbd></summary>

```bash
# Copy and configure environment
cp .env.example .env
# Set INTERNAL_JWT_SECRET to the same value used in prostaff-api

# Start the service (port 8001)
docker compose up -d

# Check health
curl http://localhost:8001/health
```

</details>

<details>
<summary><kbd>▶ Option 2: Local (development)</kbd></summary>

```bash
# Install FFmpeg (required for clip export)
sudo apt install ffmpeg

# Create virtualenv and install dependencies
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env

# Start with hot-reload
uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload
```

</details>

---

## 02 · Technology Stack

```
┌─────────────────────┬────────────────────────────────────────────────────────┐
│ Runtime             │ Python 3.11                                            │
│ API Framework       │ FastAPI 0.111 + uvicorn (single worker, FileLock)      │
│ ORM / Database      │ SQLModel 0.0.19 + SQLite (job state + clip jobs)       │
│ Video Download      │ yt-dlp (YouTube, Twitch, and 1000+ sites)              │
│ Scene Detection     │ PySceneDetect 0.6.4 + OpenCV (ContentDetector)         │
│ Audio Analysis      │ librosa 0.10.2 + numpy (RMS energy, chunked load)      │
│ ASR (Phase 3)       │ faster-whisper 1.0+ - tiny model, CPU int8 (optional)  │
│ Clip Export         │ FFmpeg (seek + cut, MP4, async background task)        │
│ Auth                │ python-jose HS256 JWT (internal service token)         │
│ Cross-process lock  │ filelock (OS advisory lock - safe against SIGKILL)     │
│ Container           │ Docker + Docker Compose                                │
└─────────────────────┴────────────────────────────────────────────────────────┘
```

---

## 03 · Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         REQUEST FLOW                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  prostaff-api ──JWT──► POST /jobs ──► SQLite (status=pending)               │
│                                           │                                 │
│                                    BackgroundTask                           │
│                                           │                                 │
│                              ┌────────────▼────────────┐                    │
│                              │   FileLock (OS-level)   │                    │
│                              │  /tmp/videoai_analysis  │                    │
│                              └────────────┬────────────┘                    │
│                                           │                                 │
│                                    yt-dlp download                          │
│                                    (progress: 10%)                          │
│                                           │                                 │
│                         ┌─────────────────┼─────────────────┐               │
│                         ▼                 ▼                  ▼              │
│                  scene_detector    audio_analyzer       transcriber         │
│                  (progress: 60%)   (progress: 80%)   (progress: 90%)        │
│                    [Format 1]        [Format 2]        [optional]           │
│                         │                 │                  │              │
│                         └─────────────────┼──────────────────┘              │
│                                           ▼                                 │
│                                        scorer                               │
│                              [Format 3 → 4 → NMS]                           │
│                                           │                                 │
│                              ┌────────────▼────────────┐                    │
│                              │  SQLite (status=done)   │                    │
│                              │  suggested_timestamps[] │                    │
│                              └─────────────────────────┘                    │
│                                                                             │
│  GET /jobs/{id} ◄──────────────── prostaff-api polls progress               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CLIP EXPORT FLOW                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  POST /clips ──► SQLite (status=pending)                                    │
│                          │                                                  │
│                   BackgroundTask                                            │
│                          │                                                  │
│             FFmpeg seek+cut (timeout 120s)                                  │
│                          │                                                  │
│         CLIPS_DIR/{clip_id}.mp4 ──► status=done                             │
│                                                                             │
│  GET /clips/{id}/download ──► FileResponse (MP4)                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 04 · Pipeline Internals

### Signal Pipeline (3 Phases)

```
Phase 1/2: Core signals (always active)
┌──────────────────────────────────────────────────────────────────────────┐
│  scene_detector  →  list[float]            (Format 1: scene timestamps)  │
│  audio_analyzer  →  list[tuple[float,float]] (Format 2: ts + energy)     │
│                                                                          │
│  scorer builds Format 3 (candidates dict) then Format 4 (results list)   │
│                                                                          │
│  Score = SCENE_SCORE (0.35) + energy × AUDIO_WEIGHT (0.6)                │
│        + CONVERGENCE_BONUS (+0.15, if both signals fire)                 │
│  MIN_SCORE = 0.45  (scene-only 0.35 is filtered; scene+audio 0.50 passes)│
│  NMS window = 20s  (keeps highest-score candidate per LoL teamfight)     │
└──────────────────────────────────────────────────────────────────────────┘

Phase 2: Tuned thresholds
┌──────────────────────────────────────────────────────────────────────────┐
│  ContentDetector  threshold=22.0, min_scene_len=15                       │
│  audio_analyzer   window_sec=1.0, local p95 normalization (±150s window) │
│  Dead zone: audio energy 0.6-0.75 → scorer score 0.36-0.45 → filtered    │
│  (intentional: lower energy_threshold if recall is too low)              │
└──────────────────────────────────────────────────────────────────────────┘

Phase 3: ASR signals (enable_transcription=True, slow - ~3-5x real-time)
┌──────────────────────────────────────────────────────────────────────────┐
│  transcriber  →  list[dict]  {"start", "end", "text"}  (16 kHz)          │
│  phrase_detector:                                                        │
│    score_segments        → (ts, phrase_score)  excitement phrases        │
│    compute_density       → (ts, chars/sec)     commentary speed          │
│                                                                          │
│  Score += min(density / 4.0, 1.0) × TRANSCRIPT_WEIGHT (0.20)             │
│        += min(phrase_score, 1.0) × PHRASE_WEIGHT (0.15)                  │
│  Segment lookup: ±3s radius from candidate timestamp                     │
│  Degrades gracefully if faster-whisper is not installed                  │
└──────────────────────────────────────────────────────────────────────────┘
```

### Scoring Examples

```
Audio-only strong hit:    energy=0.90 → score=0.54  → confidence=0.540
Scene + weak audio:       0.35 + 0.24 + 0.15(bonus) → score=0.74  → confidence=0.740
Full Phase 3 hit:         0.60 + 0.35 + 0.15 + 0.20 + 0.15 → score=1.45 → confidence=1.000
```

### Memory Profile

```
Audio (22050 Hz, chunked):  600s chunk × 22050 × 4 bytes ≈  53 MB  mono resample buffer
                           + 600s chunk × 48000 × 2ch × 4 bytes ≈ 230 MB source buffer
                           = ~283 MB peak per chunk (two buffers coexist during resample)

ASR (16000 Hz, faster-whisper tiny):  ~200 MB model + audio buffer
Total worst-case (Phase 3 active):    ~500 MB
```

---

## 05 · API Endpoints

All endpoints require `Authorization: Bearer <internal_jwt>` (see [Authentication](#06--authentication)).

### Health

```
GET /health
```

```json
{ "status": "ok", "service": "prostaff-videoai" }
```

---

### Analysis Jobs

#### Create job

```
POST /jobs
Content-Type: application/json
```

```json
{
  "vod_review_id": "550e8400-e29b-41d4-a716-446655440000",
  "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
}
```

Response `201`:
```json
{ "job_id": "550e8400-...", "status": "pending" }
```

Job lifecycle: `pending` → `downloading` → `analyzing` → `done` | `failed`

#### Get job status

```
GET /jobs/{job_id}
```

Response when `done`:
```json
{
  "job_id": "550e8400-...",
  "status": "done",
  "progress": 100,
  "suggested_timestamps": [
    {
      "start_seconds": 312,
      "confidence": 0.87,
      "reason": "audio_spike+scene_change+convergence",
      "raw_score": 1.05
    }
  ],
  "error_message": null
}
```

`suggested_timestamps` is `null` while the job is still running.

#### Reason values

```
audio_spike            - RMS energy above threshold (normalized locally)
scene_change           - content cut detected (threshold 22)
convergence            - both signals fired within the same second (+0.15 bonus)
transcript_density     - fast commentary (chars/sec > 4.0, Phase 3 only)
excitement_phrase      - PT-BR excitement term detected (Phase 3 only)
```

---

### Clip Export

#### Create clip

```
POST /clips
Content-Type: application/json
```

```json
{
  "video_url": "https://...",
  "start_seconds": 310.0,
  "end_seconds": 330.0
}
```

Response `201`:
```json
{ "clip_id": "uuid", "status": "pending" }
```

Constraints: `start >= 0`, `end > start`, `end - start <= 600s`

#### Get clip status

```
GET /clips/{clip_id}
```

```json
{
  "clip_id": "uuid",
  "status": "done",
  "download_url": "/clips/uuid/download",
  "error_message": null
}
```

#### Download clip

```
GET /clips/{clip_id}/download
```

Returns `video/mp4` binary. Only available when `status == "done"`.

---

## 06 · Authentication

All endpoints use internal service authentication - not user JWT tokens.

```
Authorization: Bearer <internal_jwt>
```

Token must be signed with `INTERNAL_JWT_SECRET` using HS256. This secret is **shared** with:
- `prostaff-api` - calls `/jobs` after user triggers analysis
- `prostaff-riot-gateway` - same shared secret for internal service mesh

Example token generation (Ruby, prostaff-api side):
```ruby
payload = { sub: "prostaff-api", iat: Time.now.to_i }
token = JWT.encode(payload, ENV["INTERNAL_JWT_SECRET"], "HS256")
```

Example token generation (Python):
```python
import time
from jose import jwt
token = jwt.encode({"sub": "prostaff-api", "iat": int(time.time())}, SECRET, "HS256")
```

---

## 07 · Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `INTERNAL_JWT_SECRET` | Yes | - | Shared secret with prostaff-api (HS256) |
| `DATABASE_URL` | No | `sqlite:///./videoai.db` | SQLite database path |
| `CLIPS_DIR` | No | `/tmp/videoai_clips` | Directory for exported MP4 clips |

---

## 08 · Testing

```bash
# Run full test suite (no Docker, no video files required - all external deps mocked)
cd /home/bullet/PROJETOS/ProStaff-VideoAI
python3 -m pytest tests/ -v
```

```
Tests: 82 total, 82 passing
  test_audio_analyzer.py   -  8 tests  (_local_normalize isolation)
  test_phrase_detector.py  - 19 tests  (score_segments + compute_density)
  test_scorer.py           - 36 tests  (Phase 1/2: MIN_SCORE, NMS, convergence, output)
  test_scorer_phase3.py    - 19 tests  (Phase 3: degradation, density, phrase, radius)
```

All external dependencies (scenedetect, librosa, faster-whisper) are stubbed via
`sys.modules` before import - no video files, no model downloads needed.

```bash
# Validate peak RAM for a specific video (requires Docker + real video)
docker exec prostaff-videoai python scripts/validate_ram_peak.py /path/to/video.mp4
# Warns if peak > 400 MB per chunk
```

---

## 09 · Performance & Limits

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Phase 1/2 (scene + audio only)                                             │
│  ─────────────────────────────                                              │
│  45 min VOD (2700s):  scene ~30s  + audio ~60-90s  = ~2 min total           │
│  Peak RAM: ~283 MB per 600s audio chunk(two buffers coexist during resample)│
│                                                                             │
│  Phase 3 (+ASR)  - enable_transcription=True                                │
│  ──────────────                                                             │
│  45 min VOD: +10-15 min (tiny model, 3-5x real-time on shared VPS CPU)      │
│  Peak RAM: +~200 MB (whisper tiny model)                                    │
│  Disabled by default - enable only when commentary quality is reliable      │
│                                                                             │
│  Max VOD duration:  5400s (90 min) across all pipeline stages               │
│  Max clip duration: 600s per clip export request                            │
│  Concurrency: single worker (--workers 1), FileLock serializes analysis     │
│  Job timeout: FileLock 3600s - aborts if analysis stalls for 1h             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 10 · Integration with ProStaff

This service is called internally by `prostaff-api` from the VOD Review module.
The `INTERNAL_JWT_SECRET` must match across all three services.

```
prostaff-api (Rails)  ──HTTPS/internal──►  prostaff-videoai (FastAPI)
                                                      │
                         ◄──── progress polling ──────┘
                                (GET /jobs/{id})
```

prostaff-api trigger (Ruby):
```ruby
# app/modules/vod_reviews/controllers/vod_reviews_controller.rb
payload = { sub: "prostaff-api", iat: Time.now.to_i }
token   = JWT.encode(payload, ENV["INTERNAL_JWT_SECRET"], "HS256")

response = HTTParty.post(
  "#{ENV['VIDEOAI_URL']}/jobs",
  headers: { "Authorization" => "Bearer #{token}", "Content-Type" => "application/json" },
  body:    { vod_review_id: @vod_review.id, video_url: @vod_review.video_url }.to_json
)
```

Result import: the `import_from_job` action in `VodReviewsController` polls `/jobs/{id}`,
maps `start_seconds` to `VodTimestamp`, and formats `reason` via `gsub('+', ' e ').humanize`.

---

## 11 · Deployment

### Docker Compose (production)

```bash
# Start service
docker compose -f docker-compose.yml up -d

# View logs
docker logs prostaff-videoai --tail 50 -f

# Restart
docker compose restart
```

### Key deployment notes

```
- MUST run with --workers 1 (FileLock is OS-level but same-process assumption in queue)
- CLIPS_DIR must be a persistent volume (clips survive container restarts)
- DATABASE_URL should point to a persistent path, not /tmp
- faster-whisper model is downloaded on first use (~75 MB for tiny) - pre-warm in Dockerfile
  if cold-start latency is unacceptable
- FileLock path /tmp/videoai_analysis.lock is released automatically on SIGKILL
  (OS closes fd when process dies - no stale lock risk)
```

### Directory structure

```
ProStaff-VideoAI/
├── api/
│   ├── main.py            # FastAPI app + lifespan (startup job recovery)
│   ├── auth.py            # JWT verification (INTERNAL_JWT_SECRET)
│   ├── database.py        # SQLModel engine + get_session
│   ├── models.py          # AnalysisJob + ClipJob (SQLite tables)
│   └── routes/
│       ├── jobs.py        # POST/GET /jobs, FileLock, _set_progress
│       └── clips.py       # POST/GET /clips, FFmpeg, FileResponse
├── pipeline/
│   ├── scene_detector.py  # PySceneDetect ContentDetector (threshold 22, min_scene 15)
│   ├── audio_analyzer.py  # librosa RMS, chunked load, local p95 normalization
│   ├── transcriber.py     # faster-whisper tiny, 16 kHz, PT-BR (Phase 3)
│   ├── phrase_detector.py # PT-BR excitement phrases + transcript density (Phase 3)
│   └── scorer.py          # Combines all signals: Format 1→2→3→4, NMS, MIN_SCORE
├── tests/
│   ├── test_audio_analyzer.py   # _local_normalize unit tests
│   ├── test_phrase_detector.py  # score_segments + compute_density unit tests
│   ├── test_scorer.py           # Phase 1/2 scorer tests
│   └── test_scorer_phase3.py    # Phase 3 integration tests
├── scripts/
│   ├── validate_ram_peak.py     # tracemalloc peak RAM validator (run in Docker)
│   ├── lint.sh                  # Ruff format + lint check (--fix to auto-fix)
│   ├── security_audit.sh        # Bandit + Semgrep audit
│   └── full_audit.sh            # lint + security (pre-PR gate)
├── .github/
│   └── workflows/
│       └── ci.yml               # CI: lint / security / tests in parallel
├── pyproject.toml               # Ruff, Bandit, pytest config
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## 12 · Code Quality & Security

### Toolchain

```
┌──────────────┬──────────────────────────────────────────────────────────────┐
│ Tool         │ Role                                                         │
├──────────────┼──────────────────────────────────────────────────────────────┤
│ Ruff 0.15    │ Format (Black-compatible) + lint (isort, Flake8, Bugbear,    │
│              │ pyupgrade, simplify, naming, security subset, perflint)      │
│ Bandit 1.9   │ AST-based security analysis - subprocess, crypto, injection  │
│ Semgrep      │ Pattern-based rules (p/python + p/bandit, 239 rules)         │
└──────────────┴──────────────────────────────────────────────────────────────┘
```

Config in `pyproject.toml` - single source for all tools.

### Running locally

```bash
# Format + lint check (CI mode)
./scripts/lint.sh

# Auto-fix safe violations
./scripts/lint.sh --fix

# Security audit (Bandit + Semgrep)
./scripts/security_audit.sh

# Full pre-PR gate (lint + security)
./scripts/full_audit.sh
```

### CI (GitHub Actions)

Three jobs run in parallel on every push/PR:

```
ci.yml
├── lint      - ruff format --check + ruff check
├── security  - bandit + semgrep (p/python + p/bandit)
└── test      - pytest tests/
```

### Documented suppressions

| Location | Rule | Reason |
|---|---|---|
| `clips.py` import | `gitlab.bandit.B404` | subprocess required for ffmpeg invocation |
| `clips.py` subprocess.run | `dangerous-subprocess-use-tainted-env-args` | URL validated (http/https), ffmpeg `-protocol_whitelist`, internal JWT |
| `jobs.py` FileLock | hardcoded-tmp | Fixed path required for cross-worker advisory lock |
| `scene_detector.py` except | `S110` | FrameTimecode unavailable in older scenedetect - fallback to full scan |
| `scorer.py` except | `S110` | Transcription is optional; failure degrades to 2-signal pipeline |

Security finding fixed during setup: `clips.py` was passing `video_url` to ffmpeg without scheme validation. Added `urlparse` check rejecting anything other than `http/https`.

---

**Last Updated**: 2026-06-20
**Pipeline**: Phase 1 (chunked audio, FileLock, NMS) + Phase 2 (threshold 22, local norm, convergence) + Phase 3 (faster-whisper ASR, PT-BR phrases)
**Tests**: 82 passing (pytest, all mocked - no Docker required)
**Integration**: prostaff-api VOD Review module → import_from_job → VodTimestamp
**Code Quality**: Ruff 0 violations, Bandit 0 issues, Semgrep 0 findings
