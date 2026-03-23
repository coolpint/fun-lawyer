from __future__ import annotations

import argparse
import time
from collections import Counter

from .config import AppConfig
from .db import Repository
from .integrations.media_tools import MediaTools
from .integrations.openai_client import OpenAIService
from .integrations.teams import TeamsWebhookClient
from .integrations.youtube import YouTubeClient
from .models import JobType
from .qa_agent import QualityAgent
from .stages.article_builder import DocumentBuilder
from .stages.teams_publisher import TeamsPublisher
from .stages.transcript_worker import TranscriptWorker
from .stages.youtube_watcher import YoutubeWatcher


def build_services(cwd=None):
    config = AppConfig.from_env(cwd=cwd)
    config.ensure_directories()
    repository = Repository(config.db_path)
    repository.init_schema()
    qa_agent = QualityAgent(config)
    youtube_client = YouTubeClient(config)
    media_tools = MediaTools(config)
    openai_service = OpenAIService(config)
    teams_client = TeamsWebhookClient(config)
    return {
        "config": config,
        "repository": repository,
        "qa_agent": qa_agent,
        "youtube_watcher": YoutubeWatcher(repository, youtube_client, qa_agent),
        "transcript_worker": TranscriptWorker(config, repository, media_tools, openai_service, qa_agent),
        "document_builder": DocumentBuilder(config, repository, media_tools, openai_service, qa_agent),
        "teams_publisher": TeamsPublisher(config, repository, teams_client, qa_agent),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="fun-lawyer pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db")

    scan_parser = subparsers.add_parser("scan-youtube")
    scan_parser.add_argument("--max-results", type=int, default=5)

    run_stage = subparsers.add_parser("run-stage")
    run_stage.add_argument("stage", choices=["transcript", "document", "article", "publish"])

    run_once = subparsers.add_parser("run-once")
    run_once.add_argument("--max-results", type=int, default=5)

    run_loop = subparsers.add_parser("run-loop")
    run_loop.add_argument("--max-results", type=int, default=5)
    run_loop.add_argument("--interval-sec", type=int, default=900)

    subparsers.add_parser("show-status")
    return parser.parse_args()


def dispatch_job(services, job) -> None:
    repository = services["repository"]
    try:
        if job["job_type"] == JobType.TRANSCRIBE.value:
            services["transcript_worker"].process(int(job["entity_id"]))
        elif job["job_type"] in {JobType.BUILD_DOCUMENT.value, JobType.BUILD_ARTICLE.value}:
            services["document_builder"].process(int(job["entity_id"]))
        elif job["job_type"] == JobType.PUBLISH_TEAMS.value:
            services["teams_publisher"].process(int(job["entity_id"]))
        else:
            raise RuntimeError(f"Unsupported job type: {job['job_type']}")
        repository.complete_job(int(job["id"]))
        return None
    except Exception as exc:
        repository.fail_job(int(job["id"]), str(exc))
        print(f"job {job['id']} failed: {exc}")
        return {
            "job_id": int(job["id"]),
            "job_type": str(job["job_type"]),
            "entity_id": int(job["entity_id"]),
            "error": str(exc),
        }


def run_stage_jobs(services, job_type: str) -> tuple[int, list[dict], list[dict]]:
    repository = services["repository"]
    recovered = repository.recover_stale_jobs()
    processed = 0
    failures: list[dict] = []
    while True:
        job = repository.claim_next_job(job_type)
        if not job:
            break
        failure = dispatch_job(services, job)
        if failure:
            failures.append(failure)
        processed += 1
    return processed, failures, recovered


def print_status(services) -> None:
    repository = services["repository"]
    job_counter = Counter(job["status"] for job in repository.list_jobs())
    video_counter = Counter(video["status"] for video in repository.list_videos())
    transcript_counter = Counter(row["status"] for row in repository.list_transcripts())
    document_counter = Counter(row["status"] for row in repository.list_articles())
    delivery_counter = Counter(row["status"] for row in repository.list_deliveries())
    print("videos:", dict(video_counter))
    print("transcripts:", dict(transcript_counter))
    print("documents:", dict(document_counter))
    print("deliveries:", dict(delivery_counter))
    print("jobs:", dict(job_counter))


def notify_run_issues(services, failures: list[dict], recovered: list[dict]) -> None:
    if not failures and not recovered:
        return
    config = services["config"]
    if not config.teams_webhook_url:
        return

    lines: list[str] = []
    if recovered:
        lines.append(f"복구된 작업 {len(recovered)}건")
        for item in recovered[:10]:
            lines.append(f"- job {item['id']} / {item['job_type']} / entity {item['entity_id']}")
    if failures:
        lines.append(f"실패한 작업 {len(failures)}건")
        for item in failures[:10]:
            lines.append(f"- job {item['job_id']} / {item['job_type']} / {item['error']}")

    payload = services["teams_publisher"].teams_client.build_status_card(
        title="fun-lawyer 실행 경고",
        lines=lines,
    )
    try:
        services["teams_publisher"].teams_client.post(payload)
    except Exception as exc:  # pragma: no cover
        print(f"warning: failed to post run issues to Teams: {exc}")


def run_once_cycle(services, max_results: int) -> tuple[int, int, list[dict], list[dict]]:
    repository = services["repository"]
    recovered = repository.recover_stale_jobs()
    failures: list[dict] = []
    try:
        created = services["youtube_watcher"].scan(max_results=max_results)
    except Exception as exc:
        created = 0
        failures.append(
            {
                "job_id": 0,
                "job_type": "scan_youtube",
                "entity_id": 0,
                "error": str(exc),
            }
        )
        print(f"scan failed: {exc}")
    processed = 0
    while True:
        job = repository.claim_next_job()
        if not job:
            break
        failure = dispatch_job(services, job)
        if failure:
            failures.append(failure)
        processed += 1
    notify_run_issues(services, failures, recovered)
    return created, processed, failures, recovered


def main() -> None:
    args = parse_args()
    services = build_services()
    repository = services["repository"]

    if args.command == "init-db":
        repository.init_schema()
        print(f"initialized {services['config'].db_path}")
        return

    if args.command == "scan-youtube":
        created = services["youtube_watcher"].scan(max_results=args.max_results)
        print(f"queued {created} new videos")
        return

    if args.command == "run-stage":
        mapping = {
            "transcript": JobType.TRANSCRIBE.value,
            "document": JobType.BUILD_DOCUMENT.value,
            "article": JobType.BUILD_DOCUMENT.value,
            "publish": JobType.PUBLISH_TEAMS.value,
        }
        processed, failures, recovered = run_stage_jobs(services, mapping[args.stage])
        notify_run_issues(services, failures, recovered)
        print(f"processed {processed} jobs")
        return

    if args.command == "run-once":
        created, processed, _failures, _recovered = run_once_cycle(services, args.max_results)
        print(f"queued {created} new videos and processed {processed} jobs")
        return

    if args.command == "run-loop":
        try:
            while True:
                created, processed, _failures, _recovered = run_once_cycle(services, args.max_results)
                print(f"queued {created} new videos and processed {processed} jobs")
                time.sleep(args.interval_sec)
        except KeyboardInterrupt:
            print("stopped")
        return

    if args.command == "show-status":
        print_status(services)
        return


if __name__ == "__main__":
    main()
