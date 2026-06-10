# ClipForge

Local YouTube → TikTok clipping machine for content clipping campaigns (Whop etc.).

Paste a YouTube link → ClipForge downloads it, transcribes it with word-level
timestamps, asks Claude to find the most viral-worthy 20–60s moments, renders each
one as a polished 9:16 TikTok-ready clip (smart face-centered crop, animated
CapCut-style captions, hook headline, −14 LUFS audio), then lets you post to TikTok
or export with one click.

```
YouTube URL ──▶ yt-dlp ──▶ faster-whisper ──▶ Claude scoring ──▶ ffmpeg render ──▶ Review dashboard ──▶ TikTok / Export
                (cached)      (cached)       (+ audio energy)    (1080×1920)
```

## Stack

- **Backend:** Python / FastAPI, asyncio job queue (no Redis needed), SQLite
- **Frontend:** React + Vite + Tailwind single-page dashboard
- **Video:** yt-dlp + ffmpeg, OpenCV face detection for smart cropping
- **Transcription:** faster-whisper (local, free), word timestamps, disk-cached
- **Clip selection:** Anthropic API (`claude-opus-4-8` by default)

---

## Setup

### 1. Install ffmpeg

| OS | Command |
|---|---|
| macOS | `brew install ffmpeg` |
| Ubuntu/Debian | `sudo apt install ffmpeg` |
| Windows | `winget install ffmpeg` (or download from ffmpeg.org and add to PATH) |

Verify: `ffmpeg -version`

### 2. Backend

**macOS / Linux:**

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp ../.env.example .env
# edit .env: set ANTHROPIC_API_KEY (required)
```

**Windows (PowerShell):**

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy ..\.env.example .env
notepad .env   # set ANTHROPIC_API_KEY (required)
```

> If activation fails with "running scripts is disabled on this system", run
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` once,
> then activate again. Your prompt shows `(.venv)` when it worked.

> First transcription downloads the Whisper model (~500MB for `small`). On a
> machine without a GPU, set `WHISPER_MODEL=base` in `.env` for speed.

### 3. Smoke-test the pipeline (do this first)

Process one video end-to-end from the CLI, no UI needed:

```bash
cd backend
python scripts/run_one.py https://www.youtube.com/watch?v=YOUR_TEST_VIDEO
# long video? only process minutes 10-25:
python scripts/run_one.py <url> --range 10 25
```

Rendered clips land in `backend/data/clips/`. If this works, everything works.

### 4. Run the app

```bash
# terminal 1 — API
cd backend && source .venv/bin/activate
uvicorn app.main:app --port 8000

# terminal 2 — UI
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**.

---

## TikTok posting (Direct Post API)

ClipForge integrates TikTok's Content Posting API. Setup walkthrough:

1. Go to **https://developers.tiktok.com** → *Manage apps* → *Connect an app*.
2. Fill in the app details (any name/icon works for personal use).
3. Add the **Login Kit** and **Content Posting API** products.
4. Under Login Kit, set the redirect URI to exactly
   `http://localhost:8000/api/tiktok/callback`.
5. Request the scopes `user.info.basic` and `video.publish`.
6. Copy the **Client key** and **Client secret** into `backend/.env`
   (`TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`).
7. In ClipForge → Settings → **Connect TikTok account**.

> ⚠️ **Unaudited apps:** until TikTok approves your app (submit it for review in
> the developer portal — this takes days/weeks, apply early), Direct Post is
> restricted: posts can only be **private (SELF_ONLY) or drafts**. ClipForge
> detects this automatically, posts at the best allowed privacy level, and shows
> the status in Settings and after each post. Until you're approved, the
> **Export** button is the fast path: it downloads the MP4 and copies the chosen
> caption to your clipboard in one click — paste into the TikTok app/web upload.

YouTube Shorts and Instagram Reels are stubbed behind the same `Poster`
interface (`backend/app/posting/`) so they're easy to add later.

---

## Whop clipping features

- **Campaign profiles** — save rule presets: required hashtags, required
  @mentions, required caption text/phrases, banned words, min/max clip length,
  watermark image + position.
  Every post/export is validated against the clip's campaign and you're warned
  (and blocked, unless you confirm) before posting a non-compliant clip.
- **Clip tracker** — every clip is logged in SQLite (source video, timestamps,
  campaign, post date, post URL) with manual views/earnings fields so you can
  see which source videos and hook styles earn the most.
- **Duplicate protection** — posting a segment that overlaps (>50%) one you
  already posted from the same video triggers a warning.
- **Hook A/B helper** — Claude generates 3 hook variants per clip
  (curiosity-gap / bold-claim / emotional). Click a variant chip, hit Apply, and
  only the text layer re-renders (seconds, not minutes) — post the same moment
  with different hooks across accounts.

## Quality of life

- **Batch mode** — paste multiple URLs, they queue up.
- **Upload mode** — feed it a video file from your computer (mp4/mov/mkv/webm/avi)
  instead of a YouTube URL; same pipeline, no download step. Files are
  content-hashed so re-uploading the same file hits every cache.
- **Time-range mode** — process only minutes X–Y of a long video (required for
  videos over 3 hours).
- **Aggressive caching** — downloads, transcripts, and Claude analyses are all
  cached by video ID; re-processing a video is instant. Hook edits reuse a
  cached textless base render.
- **Blurred background mode** — full-width video centered over a blurred copy,
  instead of the face-tracked crop.
- **Settings page** — caption font/colors/highlight, default hashtags,
  watermark position, blur default.

## Where things live

```
backend/
  app/
    pipeline/     ingest (yt-dlp) → transcribe (whisper) → highlights (Claude)
                  → captions (ASS) → facetrack (OpenCV) → render (ffmpeg)
    posting/      TikTok Direct Post + OAuth, YT/IG stubs
    api/          FastAPI routes
    jobqueue.py   asyncio job queue + websocket progress
    db.py         SQLite models (videos, clips, campaigns, accounts, settings)
  scripts/run_one.py   CLI end-to-end smoke test
  data/           downloads, rendered clips, caches, sqlite db (gitignored)
frontend/         React + Tailwind dashboard
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ffmpeg is not installed` | Install ffmpeg and make sure it's on PATH |
| Age-restricted / region-locked video | Surfaced as a clear error; pick another video or configure yt-dlp cookies |
| `ANTHROPIC_API_KEY is not set` | Put your key in `backend/.env` |
| Transcription very slow | Use a smaller `WHISPER_MODEL` (`base`/`tiny`) or a CUDA GPU |
| TikTok post lands as private | Your TikTok app hasn't passed audit yet — expected; use Export meanwhile |
| Captions show wrong font | The font must be installed system-wide for ffmpeg/libass to find it |

## Rights note

Whop campaigns grant clipping permission from the creator — stick to campaign
content. Clipping arbitrary YouTube videos outside a campaign risks copyright
strikes that kill accounts.
