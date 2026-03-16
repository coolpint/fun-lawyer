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
5. If you do not use `OPENAI_API_KEY`, install `faster-whisper`.
6. If YouTube blocks downloads on your machine, set either `YT_DLP_COOKIES_PATH` or `YT_DLP_COOKIES_FROM_BROWSER`.
7. If you want capture images to render inside Teams, expose `APP_STORAGE_DIR` through a public HTTPS base URL and set `APP_PUBLIC_MEDIA_BASE_URL`.

## Commands

Initialize the database:

```bash
fun-lawyer init-db
```

Run one full pass:

```bash
fun-lawyer run-once
```

Run the local worker loop:

```bash
fun-lawyer run-loop --interval-sec 900
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

- Default local state lives under `.data/`. GitHub 저장소를 상태 저장소로 쓰지 않는다.
- Teams incoming webhook은 로컬 파일 경로를 직접 렌더링하지 못한다. 그래서 `APP_PUBLIC_MEDIA_BASE_URL`이 없으면 기사 본문은 전송되지만 캡처 이미지는 카드에서 생략된다.
- 캡처 3장은 항상 로컬에 저장된다. 나중에 공개 URL만 연결하면 같은 구조로 Teams 카드에 붙일 수 있다.
- `OPENAI_API_KEY`가 없으면 전사는 `faster-whisper`, 기사 작성은 규칙 기반 fallback으로 처리한다.
- `YT_DLP_COOKIES_FROM_BROWSER=chrome` 같은 값으로 로컬 브라우저 쿠키를 직접 읽게 할 수 있다.
