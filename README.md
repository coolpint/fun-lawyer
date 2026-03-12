# fun-lawyer

`fun-lawyer` is a modular batch pipeline for the `@lawfun_official` YouTube channel.

The current scaffold separates the work into four workers:

1. `youtube_watcher`: finds newly uploaded non-Shorts videos and writes `video` records.
2. `transcript_worker`: downloads captions or audio, generates a transcript, and stores it.
3. `article_builder`: turns the transcript into an article package with three capture frames.
4. `teams_publisher`: sends the stored article package to a Teams incoming webhook.

Each stage is reviewed by `qa_agent` before the next stage can continue. Failures stay isolated inside the stage that produced them.

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

## Notes

- Teams incoming webhooks can render image URLs, not local file paths.
- The publisher therefore expects each capture to have a `public_url` before it can pass preflight QA.
- The current scaffold is ready for a scheduler, but it only ships a `run-once` CLI for now.
