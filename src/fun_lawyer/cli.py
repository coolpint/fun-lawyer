from __future__ import annotations

import argparse
from collections import Counter

from .config import AppConfig
from .db import Repository
from .integrations.media_tools import MediaTools
from .integrations.openai_client import OpenAIService
from .integrations.teams import TeamsWebhookClient
from .integrations.youtube import YouTubeClient
from .models import JobType
from .qa_agent import QualityAgent
from .stages.article_builder import ArticleBuilder
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
        "article_builder": ArticleBuilder(config, repository, media_tools, openai_service, qa_agent),
        "teams_publisher": TeamsPublisher(config, repository, teams_client, qa_agent),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="fun-lawyer pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db")

    scan_parser = subparsers.add_parser("scan-youtube")
    scan_parser.add_argument("--max-results", type=int, default=5)

    run_stage = subparsers.add_parser("run-stage")
    run_stage.add_argument("stage", choices=["transcript", "article", "publish"])

    run_once = subparsers.add_parser("run-once")
    run_once.add_argument("--max-results", type=int, default=5)

    subparsers.add_parser("show-status")
    return parser.parse_args()


def dispatch_job(services, job) -> None:
    repository = services["repository"]
    try:
        if job["job_type"] == JobType.TRANSCRIBE.value:
            services["transcript_worker"].process(int(job["entity_id"]))
        elif job["job_type"] == JobType.BUILD_ARTICLE.value:
            services["article_builder"].process(int(job["entity_id"]))
        elif job["job_type"] == JobType.PUBLISH_TEAMS.value:
            services["teams_publisher"].process(int(job["entity_id"]))
        else:
            raise RuntimeError(f"Unsupported job type: {job['job_type']}")
        repository.complete_job(int(job["id"]))
    except Exception as exc:
        repository.fail_job(int(job["id"]), str(exc))
        print(f"job {job['id']} failed: {exc}")


def run_stage_jobs(services, job_type: str) -> int:
    repository = services["repository"]
    processed = 0
    while True:
        job = repository.claim_next_job(job_type)
        if not job:
            break
        dispatch_job(services, job)
        processed += 1
    return processed


def print_status(services) -> None:
    repository = services["repository"]
    job_counter = Counter(job["status"] for job in repository.list_jobs())
    video_counter = Counter(video["status"] for video in repository.list_videos())
    transcript_counter = Counter(row["status"] for row in repository.list_transcripts())
    article_counter = Counter(row["status"] for row in repository.list_articles())
    delivery_counter = Counter(row["status"] for row in repository.list_deliveries())
    print("videos:", dict(video_counter))
    print("transcripts:", dict(transcript_counter))
    print("articles:", dict(article_counter))
    print("deliveries:", dict(delivery_counter))
    print("jobs:", dict(job_counter))


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
            "article": JobType.BUILD_ARTICLE.value,
            "publish": JobType.PUBLISH_TEAMS.value,
        }
        processed = run_stage_jobs(services, mapping[args.stage])
        print(f"processed {processed} jobs")
        return

    if args.command == "run-once":
        created = services["youtube_watcher"].scan(max_results=args.max_results)
        processed = 0
        while True:
            job = repository.claim_next_job()
            if not job:
                break
            dispatch_job(services, job)
            processed += 1
        print(f"queued {created} new videos and processed {processed} jobs")
        return

    if args.command == "show-status":
        print_status(services)
        return


if __name__ == "__main__":
    main()
