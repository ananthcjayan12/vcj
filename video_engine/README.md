# Manual Topic Video Engine

This package is the curriculum-control layer around the two repo-local video systems:

- `physics_animation_engine/`: 35 reusable deterministic physics scenes and example JSON compositions.
- `template_lab/`: script, voice, Whisper timing, V3 custom scenes, validation, preview, HyperFrames render, and FFmpeg audio muxing.

It does not schedule unattended daily jobs. You choose a topic, run generation, review the result, render it, and either publish through the Studio's explicitly confirmed YouTube queue or upload manually before updating coverage.

## First setup

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-video-engine.txt

cd physics_animation_engine
npm install
cd ..

cd template_lab
npm install
cd ..

python3 -m video_engine.cli init
python3 -m video_engine.cli doctor
```

Full MP4 rendering also requires Node 22.12+, npm, FFmpeg, and ffprobe. The renderer is installed from `template_lab/package-lock.json`; it does not fetch an unspecified HyperFrames release at render time. Copy `.env.example` to `.env` and add only the provider keys you intend to use. Paid calls are refused unless the generation command includes `--confirm-paid-api`.

## One-topic workflow

```bash
# 1. Inspect coverage and choose the next incomplete topic.
python3 -m video_engine.cli status
python3 -m video_engine.cli next-topic

# 2. Create a local grounded facts packet from the syllabus and private index aggregates.
python3 -m video_engine.cli prepare-topic 1.1

# 3. Generate an editable V3 lesson. This is the explicit paid/API step.
python3 template_lab/scripts/mav_generate.py \
  --run-id physics-1-1-v01 \
  --facts video_engine/topics/1.1/facts.json \
  --duration 480 \
  --v3 \
  --use-gemini \
  --use-gemini-tts \
  --confirm-paid-api

# 4. Preview and iterate locally.
python3 template_lab/scripts/mav_preview.py --run-id physics-1-1-v01

# 5. Render the approved composition to MP4.
python3 template_lab/scripts/mav_render.py --run-id physics-1-1-v01 --quality high

# 6. After human review, update progress deliberately.
python3 -m video_engine.cli set-status --topic 1.1 --status reviewed
python3 -m video_engine.cli set-status --topic 1.1 --status covered
```

`prepare-topic` never includes the raw past-paper text. It writes syllabus objectives plus aggregate command-word, question-type, difficulty, and visual-frequency patterns. The facts packet explicitly requires original questions, numbers, diagrams, and wording.

## YouTube publishing

The YouTube Data API is enabled in Google Cloud project `capture-3494f`. Create
an OAuth 2.0 **Desktop app** client in that project, download it to
`.youtube/client_secret.json`, and keep it local (the directory is gitignored).
The first real upload opens Google's browser consent flow and stores the refresh
token at `.youtube/token.json` with owner-only permissions.

Authorize and verify the target channel without uploading anything:

```bash
python3 template_lab/scripts/mav_youtube_publish.py --authorize-only
```

If the Google account owns multiple YouTube or Brand Accounts, choose again with:

```bash
python3 template_lab/scripts/mav_youtube_publish.py --authorize-only --reauthorize
```

For a guarded upload, pass the channel ID you expect. The command checks the
OAuth token and aborts before starting the upload if a different channel was
selected:

```bash
python3 template_lab/scripts/mav_youtube_publish.py \
  --run-id physics-1-7-1-v01 \
  --expected-channel-id YOUR_EXPECTED_CHANNEL_ID \
  --privacy private \
  --not-made-for-kids \
  --confirm-upload
```

Always inspect the exact request first:

```bash
python3 template_lab/scripts/mav_youtube_publish.py \
  --run-id physics-1-7-1-v01 \
  --privacy private \
  --not-made-for-kids \
  --dry-run
```

Then perform the resumable upload, apply the generated thumbnail, and write
`youtube/upload-result.json`:

```bash
python3 template_lab/scripts/mav_youtube_publish.py \
  --run-id physics-1-7-1-v01 \
  --privacy private \
  --not-made-for-kids \
  --confirm-upload
```

Use `--publish-at 2026-08-08T18:00:00+05:30` with private visibility for a
scheduled release. Repeat `--playlist-id PLAYLIST_ID` to add playlists. The
optional `--post-first-comment` posts the generated comment, but YouTube's Data
API cannot pin a comment; pin it later in YouTube Studio. Public and unlisted
uploads still require `--confirm-upload`, and subscriber notifications are off
unless `--notify-subscribers` is passed.

Generated topic packets and run outputs are ignored by Git. Curriculum, animation, video, original-question, and content-fingerprint registries are versioned so coverage and duplication control stay in this repository.
