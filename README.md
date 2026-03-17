# fun-lawyer

`fun-lawyer` is a local batch pipeline for the `@lawfun_official` YouTube channel.

The current flow is intentionally simple:

1. `youtube_watcher`: finds newly uploaded non-Shorts videos and writes `video` records.
2. `transcript_worker`: downloads captions or audio, generates a transcript, and stores it.
3. `document_builder`: turns the transcript into a readable script document.
4. `teams_publisher`: sends the stored script document to a Teams incoming webhook.

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
fun-lawyer run-stage document
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
- Teams 메시지는 기사 대신 스크립트 문서를 보낸다. 마지막에 유튜브 링크를 붙인다.
- 긴 스크립트는 Teams payload 제한을 넘지 않도록 여러 카드로 나눠 보낸다.
- `OPENAI_API_KEY`가 없으면 전사는 `faster-whisper` fallback으로 처리한다.
- `YT_DLP_COOKIES_FROM_BROWSER=chrome` 같은 값으로 로컬 브라우저 쿠키를 직접 읽게 할 수 있다.
- `launchd/com.coolpint.fun-lawyer.daily.plist`와 `scripts/run_daily.sh`를 쓰면 맥이 켜져 있을 때 하루 1회 자동 점검할 수 있다.
