# fun-lawyer

`fun-lawyer` is a modular batch pipeline for the `@lawfun_official` YouTube channel.

The current scaffold separates the work into four workers:

1. `youtube_watcher`: finds newly uploaded non-Shorts videos and writes `video` records.
2. `transcript_worker`: downloads captions or audio, generates a transcript, and stores it.
3. `article_builder`: turns the transcript into an article package with three capture frames.
4. `teams_publisher`: sends the stored article package to a Teams incoming webhook.

Each stage is reviewed by `qa_agent` before the next stage can continue. Failures stay isolated inside the stage that produced them.

For GitHub Actions runs, persistent state lives under `state/` so the runner can pick up where the last run stopped.

## Setup

1. Create a virtual environment.
2. Install the project with `pip install -e .`.
3. Copy `.env.example` to `.env` and fill in the required keys.
4. Install external binaries if you want live media processing:
   - `yt-dlp`
   - `ffmpeg`
   - `ffprobe`
5. If you want capture images to appear in Teams, expose `APP_STORAGE_DIR` through a public HTTPS base URL and set `APP_PUBLIC_MEDIA_BASE_URL`.

## Commands

Initialize the database:

```bash
fun-lawyer init-db
```

Run one full pass:

```bash
fun-lawyer run-once
```

Run a single stage worker:

```bash
fun-lawyer run-stage transcript
fun-lawyer run-stage article
fun-lawyer run-stage publish
```

Inspect job and entity state:

```bash
fun-lawyer show-status
```

## Environment

See `.env.example`.

## GitHub Actions

The repository includes `.github/workflows/run-fun-lawyer.yml`, which runs hourly and can also be triggered manually.

Expected repository secrets:

- `YOUTUBE_API_KEY`
- `TEAMS_WEBHOOK_URL`
- `APP_PUBLIC_MEDIA_BASE_URL` (optional override)
- `OPENAI_API_KEY` (optional)
- `OPENAI_ARTICLE_MODEL` (optional override)
- `OPENAI_QA_MODEL` (optional override)
- `OPENAI_TRANSCRIBE_MODEL` (optional override)
- `LOCAL_TRANSCRIBE_MODEL` (optional override)
- `LOCAL_TRANSCRIBE_COMPUTE_TYPE` (optional override)
- `YT_DLP_COOKIES_B64` (optional, recommended on GitHub-hosted runners)

The workflow stores its SQLite database and generated article assets in `state/`, commits them to `main`, then sends Teams messages after the capture images are reachable at their final public URLs.

## Notes

- Teams incoming webhooks can render image URLs, not local file paths.
- The publisher therefore expects each capture to have a `public_url` before it can pass preflight QA.
- The current scaffold is ready for a scheduler, but it only ships a `run-once` CLI for now.
- If you do not set `APP_PUBLIC_MEDIA_BASE_URL`, the workflow falls back to GitHub raw URLs under `state/storage`. That works only if the repo path is publicly reachable from Teams.
- If `OPENAI_API_KEY` is missing, the pipeline falls back to local transcription with `faster-whisper` and a rule-based article writer. Quality is lower than the OpenAI path, but the workflow still runs.
- GitHub-hosted runners are often rate-limited by YouTube. If downloads fail with `HTTP Error 429` or `Sign in to confirm you’re not a bot`, add a `YT_DLP_COOKIES_B64` secret containing a base64-encoded Netscape-format cookies file, or move the workflow to a self-hosted runner.
