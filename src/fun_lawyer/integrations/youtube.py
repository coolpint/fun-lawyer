from __future__ import annotations

import json
import re
from typing import Any, Dict, List
from urllib.parse import urlencode
from urllib.request import urlopen

from ..config import AppConfig


_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?T?(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?$"
)


def parse_iso8601_duration(value: str) -> int:
    match = _DURATION_RE.match(value)
    if not match:
        return 0
    days = int(match.group("days") or 0)
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    return (((days * 24) + hours) * 60 + minutes) * 60 + seconds


class YouTubeClient:
    api_base = "https://www.googleapis.com/youtube/v3"

    def __init__(self, config: AppConfig):
        self.config = config

    def list_recent_uploads(self, max_results: int = 5) -> List[Dict[str, Any]]:
        uploads_playlist = self._resolve_uploads_playlist(self.config.youtube_channel_handle)
        playlist = self._get_json(
            "playlistItems",
            {
                "part": "contentDetails",
                "playlistId": uploads_playlist,
                "maxResults": str(max_results),
            },
        )
        video_ids = [item["contentDetails"]["videoId"] for item in playlist.get("items", [])]
        if not video_ids:
            return []

        details = self._get_json(
            "videos",
            {
                "part": "snippet,contentDetails",
                "id": ",".join(video_ids),
                "maxResults": str(max_results),
            },
        )
        items = []
        for item in details.get("items", []):
            snippet = item.get("snippet", {})
            content_details = item.get("contentDetails", {})
            title = snippet.get("title", "").strip()
            description = snippet.get("description", "")
            duration_sec = parse_iso8601_duration(content_details.get("duration", "PT0S"))
            text_for_shorts = f"{title}\n{description}".lower()
            is_short = duration_sec <= 180 and "#shorts" in text_for_shorts
            items.append(
                {
                    "youtube_video_id": item["id"],
                    "channel_handle": self.config.youtube_channel_handle,
                    "title": title,
                    "youtube_url": f"https://www.youtube.com/watch?v={item['id']}",
                    "published_at": snippet.get("publishedAt", ""),
                    "duration_sec": duration_sec,
                    "is_short": is_short,
                    "raw_json": item,
                }
            )
        items.sort(key=lambda row: row["published_at"], reverse=True)
        return items

    def _resolve_uploads_playlist(self, handle: str) -> str:
        payload = self._get_json(
            "channels",
            {
                "part": "contentDetails",
                "forHandle": handle.lstrip("@"),
            },
        )
        items = payload.get("items", [])
        if not items:
            raise RuntimeError(f"Unable to resolve YouTube channel handle: {handle}")
        return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

    def _get_json(self, resource: str, params: Dict[str, str]) -> Dict[str, Any]:
        api_key = self.config.require("youtube_api_key")
        query = urlencode({**params, "key": api_key})
        with urlopen(f"{self.api_base}/{resource}?{query}") as response:
            return json.loads(response.read().decode("utf-8"))
