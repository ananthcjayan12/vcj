"""Upload a rendered MAV lesson and its generated assets to YouTube."""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import random
import re
import socket
import ssl
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mav_schema import read_json, run_dir, write_json

YOUTUBE_SCOPES = (
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
)
RETRIABLE_STATUS_CODES = {500, 502, 503, 504}
RETRIABLE_EXCEPTIONS = (OSError, TimeoutError, socket.timeout, ssl.SSLError)
DEFAULT_CLIENT_SECRETS = Path(".youtube/client_secret.json")
DEFAULT_TOKEN = Path(".youtube/token.json")
DEFAULT_COURSE_PLAYLIST_TITLE = "Cambridge IGCSE Physics (0625) — Complete Course"
DEFAULT_COURSE_PLAYLIST_DESCRIPTION = (
    "Animated Cambridge IGCSE Physics (0625) lessons from IGCSE Visualised, "
    "arranged in syllabus learning order, with worked examples, exam skills and revision Shorts."
)
COURSE_LINKS_START = "— COURSE LINKS —"
COURSE_LINKS_END = "— END COURSE LINKS —"


def _clean_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _fit_tags(tags: list[str], limit: int = 500) -> list[str]:
    """Keep generated tags in priority order while honoring YouTube's limit."""
    fitted: list[str] = []
    for tag in tags:
        candidate = [*fitted, tag]
        if len(",".join(candidate)) <= limit:
            fitted.append(tag)
    if len(fitted) < len(tags):
        print(
            f"YouTube tag limit: keeping {len(fitted)} of {len(tags)} generated tags",
            file=sys.stderr,
        )
    return fitted


def _chapter_block(metadata: dict[str, Any]) -> str:
    chapters = metadata.get("chapters")
    if not isinstance(chapters, list):
        return ""
    lines = [
        f"{str(item.get('timestamp') or '').strip()} {str(item.get('title') or '').strip()}".strip()
        for item in chapters
        if isinstance(item, dict)
    ]
    return "\n".join(line for line in lines if line)


def _description(metadata: dict[str, Any]) -> str:
    description = str(metadata.get("description") or "").strip()
    additions: list[str] = []
    chapters = _chapter_block(metadata)
    if chapters and chapters not in description:
        additions.append(chapters)
    hashtags = " ".join(
        item if item.startswith("#") else f"#{item}"
        for item in _clean_strings(metadata.get("hashtags"))
    )
    if hashtags and hashtags not in description:
        additions.append(hashtags)
    return "\n\n".join(part for part in (description, *additions) if part)


def _strip_old_course_links(description: str) -> str:
    """Remove generated/legacy navigation while preserving lesson copy and chapters."""
    lines = description.replace("\r\n", "\n").splitlines()
    kept: list[str] = []
    in_managed_block = False
    skip_legacy_target = False
    for line in lines:
        stripped = line.strip()
        if stripped == COURSE_LINKS_START:
            in_managed_block = True
            continue
        if in_managed_block:
            if stripped == COURSE_LINKS_END:
                in_managed_block = False
                continue
            # Support the first version of the organizer, whose block ended at
            # the next section marker rather than an explicit end marker.
            if stripped in {"— CHAPTERS —", "— TIMELINE —"}:
                in_managed_block = False
                kept.append(line.rstrip())
            continue
        if re.match(r"^▶️?\s*(Previous|Next) (lesson|video|Short)\b", stripped, re.I):
            skip_legacy_target = True
            continue
        if stripped.startswith("📘 Complete IGCSE Physics course:"):
            skip_legacy_target = True
            continue
        if stripped in {
            "[ADD PLAYLIST LINK]",
            "[ADD PREVIOUS VIDEO LINK]",
            "[ADD NEXT VIDEO LINK]",
            "[ADD FULL LESSON LINK]",
        }:
            continue
        if skip_legacy_target:
            if not stripped or re.match(r"^\[?https?://", stripped):
                continue
            skip_legacy_target = False
        kept.append(line.rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def _course_description(
    description: str,
    *,
    playlist_url: str,
    previous: dict[str, str] | None,
    following: dict[str, str] | None,
    content_kind: str,
    full_lesson_video_id: str | None = None,
) -> str:
    noun = "lesson" if content_kind == "longform" else "Short"
    links = [COURSE_LINKS_START, f"📚 Complete course playlist: {playlist_url}"]
    if content_kind == "short" and full_lesson_video_id:
        links.append(f"🎬 Full lesson: https://youtu.be/{full_lesson_video_id}")
    if previous:
        links.append(
            f"⬅ Previous {noun} — {previous['title']}: https://youtu.be/{previous['video_id']}"
        )
    if following:
        links.append(
            f"➡ Next {noun} — {following['title']}: https://youtu.be/{following['video_id']}"
        )
    else:
        links.append(f"➡ Next {noun}: coming soon")
    links.append(COURSE_LINKS_END)
    result = "\n\n".join(part for part in (_strip_old_course_links(description), "\n".join(links)) if part)
    if len(result) > 5_000:
        raise ValueError(f"YouTube description is {len(result)} characters after course links; maximum is 5000")
    return result


def _full_lesson_id_from_description(description: str) -> str | None:
    match = re.search(
        r"🎬\s*Full lesson:\s*https?://(?:www\.)?(?:youtu\.be/|youtube\.com/watch\?v=)([A-Za-z0-9_-]{6,})",
        description,
    )
    return match.group(1) if match else None


def _owned_playlist(youtube: Any, title: str) -> dict[str, Any] | None:
    page_token = None
    while True:
        response = youtube.playlists().list(
            part="snippet,status,contentDetails",
            mine=True,
            maxResults=50,
            pageToken=page_token,
        ).execute()
        for item in response.get("items", []):
            if str(item.get("snippet", {}).get("title") or "") == title:
                return item
        page_token = response.get("nextPageToken")
        if not page_token:
            return None


def _ensure_course_playlist(youtube: Any, title: str) -> dict[str, Any]:
    existing = _owned_playlist(youtube, title)
    if existing:
        return existing
    return youtube.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {"title": title, "description": DEFAULT_COURSE_PLAYLIST_DESCRIPTION},
            "status": {"privacyStatus": "public"},
        },
    ).execute()


def _playlist_entries(youtube: Any, playlist: dict[str, Any]) -> list[dict[str, str]]:
    if int(playlist.get("contentDetails", {}).get("itemCount", 0)) == 0:
        return []
    entries: list[dict[str, str]] = []
    page_token = None
    while True:
        response = youtube.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=playlist["id"],
            maxResults=50,
            pageToken=page_token,
        ).execute()
        for item in response.get("items", []):
            video_id = str(item.get("contentDetails", {}).get("videoId") or "")
            if video_id:
                entries.append(
                    {
                        "video_id": video_id,
                        "title": str(item.get("snippet", {}).get("title") or video_id),
                    }
                )
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    by_id: dict[str, dict[str, Any]] = {}
    for start in range(0, len(entries), 50):
        details = youtube.videos().list(
            part="snippet,contentDetails",
            id=",".join(item["video_id"] for item in entries[start : start + 50]),
            maxResults=50,
        ).execute()
        by_id.update({str(item["id"]): item for item in details.get("items", [])})
    for entry in entries:
        video = by_id.get(entry["video_id"], {})
        title = str(video.get("snippet", {}).get("title") or entry["title"])
        duration = str(video.get("contentDetails", {}).get("duration") or "")
        match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
        seconds = 0
        if match:
            seconds = int(match.group(1) or 0) * 3600 + int(match.group(2) or 0) * 60 + int(match.group(3) or 0)
        entry["title"] = title
        entry["is_short"] = str("#shorts" in title.lower() or (0 < seconds <= 180)).lower()
    return entries


def _looks_like_short(entry: dict[str, str]) -> bool:
    return entry.get("is_short") == "true" or "#shorts" in entry.get("title", "").lower()


def _video_snippets(youtube: Any, video_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not video_ids:
        return {}
    response = youtube.videos().list(part="snippet", id=",".join(video_ids), maxResults=50).execute()
    return {str(item["id"]): item for item in response.get("items", [])}


def _update_video_description(youtube: Any, video: dict[str, Any], description: str) -> None:
    old = video["snippet"]
    snippet: dict[str, Any] = {
        "title": old["title"],
        "description": description,
        "categoryId": old["categoryId"],
    }
    for key in ("tags", "defaultLanguage", "defaultAudioLanguage"):
        if key in old:
            snippet[key] = old[key]
    youtube.videos().update(part="snippet", body={"id": video["id"], "snippet": snippet}).execute()


def organize_course_upload(
    youtube: Any,
    *,
    video_id: str,
    video_title: str,
    content_kind: str,
    course_playlist_title: str,
    full_lesson_video_id: str | None,
) -> dict[str, Any]:
    """Add an upload to the course and repair navigation for it and its neighbors."""
    playlist = _ensure_course_playlist(youtube, course_playlist_title)
    entries = _playlist_entries(youtube, playlist)
    if any(item["video_id"] == video_id for item in entries):
        position = next(index for index, item in enumerate(entries) if item["video_id"] == video_id)
    else:
        if content_kind == "longform":
            position = next(
                (index for index, item in enumerate(entries) if _looks_like_short(item)),
                len(entries),
            )
        else:
            position = len(entries)
        youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist["id"],
                    "position": position,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            },
        ).execute()
        entries.insert(
            position,
            {
                "video_id": video_id,
                "title": video_title,
                "is_short": str(content_kind == "short").lower(),
            },
        )

    same_kind = [
        item
        for item in entries
        if (_looks_like_short(item) if content_kind == "short" else not _looks_like_short(item))
    ]
    current_index = next(index for index, item in enumerate(same_kind) if item["video_id"] == video_id)
    affected = same_kind[max(0, current_index - 1) : current_index + 2]
    snippets = _video_snippets(youtube, [item["video_id"] for item in affected])
    playlist_url = f"https://www.youtube.com/playlist?list={playlist['id']}"
    updated_ids: list[str] = []
    for item in affected:
        item_index = next(index for index, entry in enumerate(same_kind) if entry["video_id"] == item["video_id"])
        previous = same_kind[item_index - 1] if item_index > 0 else None
        following = same_kind[item_index + 1] if item_index + 1 < len(same_kind) else None
        video = snippets.get(item["video_id"])
        if not video:
            continue
        existing_description = str(video["snippet"].get("description") or "")
        linked_full_lesson = (
            full_lesson_video_id
            if item["video_id"] == video_id
            else _full_lesson_id_from_description(existing_description)
        )
        description = _course_description(
            existing_description,
            playlist_url=playlist_url,
            previous=previous,
            following=following,
            content_kind=content_kind,
            full_lesson_video_id=linked_full_lesson,
        )
        _update_video_description(youtube, video, description)
        updated_ids.append(item["video_id"])
    return {
        "playlist_id": playlist["id"],
        "playlist_url": playlist_url,
        "playlist_position": position,
        "content_kind": content_kind,
        "navigation_updated_video_ids": updated_ids,
        "full_lesson_video_id": full_lesson_video_id,
    }


def build_video_body(
    metadata: dict[str, Any],
    *,
    privacy: str,
    publish_at: str | None,
    made_for_kids: bool,
    category_id: str,
) -> dict[str, Any]:
    title = str(metadata.get("video_title") or metadata.get("title") or "").strip()
    description = _description(metadata)
    tags = _fit_tags(_clean_strings(metadata.get("tags")))
    if not title:
        raise ValueError("YouTube metadata must contain video_title or title")
    if len(title) > 100:
        raise ValueError(f"YouTube title is {len(title)} characters; maximum is 100")
    if len(description) > 5_000:
        raise ValueError(f"YouTube description is {len(description)} characters; maximum is 5000")
    if publish_at and privacy != "private":
        raise ValueError("Scheduled publishing requires --privacy private")

    status: dict[str, Any] = {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": made_for_kids,
        "embeddable": True,
        "license": "youtube",
    }
    if publish_at:
        status["publishAt"] = normalize_publish_at(publish_at)
    return {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": str(category_id),
        },
        "status": status,
    }


def normalize_publish_at(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("--publish-at must include a timezone, such as 2026-08-06T18:00:00+05:30")
    parsed = parsed.astimezone(timezone.utc)
    if parsed <= datetime.now(timezone.utc):
        raise ValueError("--publish-at must be in the future")
    return parsed.isoformat().replace("+00:00", "Z")


def resolve_assets(args: argparse.Namespace) -> tuple[Path, Path, Path | None]:
    if args.run_id:
        root = run_dir(args.run_id)
        video = Path(args.video) if args.video else root / "motion_canvas" / "final.mp4"
        metadata = Path(args.metadata) if args.metadata else root / "youtube" / "metadata.json"
        thumbnail = Path(args.thumbnail) if args.thumbnail else root / "youtube" / "thumbnail.jpg"
    else:
        if not args.video or not args.metadata:
            raise ValueError("Provide --run-id, or provide both --video and --metadata")
        video = Path(args.video)
        metadata = Path(args.metadata)
        thumbnail = Path(args.thumbnail) if args.thumbnail else metadata.parent / "thumbnail.jpg"

    video = video.expanduser().resolve()
    metadata = metadata.expanduser().resolve()
    thumbnail = thumbnail.expanduser().resolve() if thumbnail else None
    if not video.is_file():
        raise FileNotFoundError(f"Rendered video not found: {video}")
    if not metadata.is_file():
        raise FileNotFoundError(f"YouTube metadata not found: {metadata}")
    if thumbnail and not thumbnail.is_file():
        if args.thumbnail:
            raise FileNotFoundError(f"Thumbnail not found: {thumbnail}")
        thumbnail = None
    return video, metadata, thumbnail


def _topic_ref(run_path: Path) -> str | None:
    for relative in ("studio_run.json", "input.json", "reel_pack.json"):
        path = run_path / relative
        if not path.is_file():
            continue
        payload = read_json(path)
        value = str(payload.get("topic_ref") or "").strip()
        if value:
            return value
        match = re.match(r"^(\d+(?:\.\d+)+)\b", str(payload.get("topic") or "").strip())
        if match:
            return match.group(1)
    return None


def infer_full_lesson_video_id(metadata_path: Path) -> str | None:
    """Match a Short metadata file to a locally receipted lesson by syllabus topic."""
    reel_run = next((parent for parent in metadata_path.parents if (parent / "reel_pack.json").is_file()), None)
    if not reel_run:
        return None
    topic_ref = _topic_ref(reel_run)
    if not topic_ref:
        return None
    for candidate in reel_run.parent.iterdir():
        if not candidate.is_dir() or candidate == reel_run or (candidate / "reel_pack.json").is_file():
            continue
        if _topic_ref(candidate) != topic_ref:
            continue
        receipt_path = candidate / "youtube" / "upload-result.json"
        if not receipt_path.is_file():
            continue
        receipt = read_json(receipt_path)
        video_id = str(receipt.get("video_id") or "").strip()
        if receipt.get("status") == "uploaded" and video_id:
            return video_id
    return None


def oauth_credentials(client_secrets: Path, token_path: Path, *, reauthorize: bool = False) -> Any:
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:
        raise RuntimeError(
            "YouTube publishing dependencies are missing. Run "
            "`python -m pip install -r requirements-video-engine.txt`."
        ) from exc

    credentials = None
    if token_path.is_file() and not reauthorize:
        credentials = Credentials.from_authorized_user_file(str(token_path), YOUTUBE_SCOPES)
    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    if not credentials or not credentials.valid:
        if not client_secrets.is_file():
            raise FileNotFoundError(
                f"OAuth desktop client file not found: {client_secrets}. "
                "Create a Desktop app OAuth client in project capture-3494f and save its JSON there."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), YOUTUBE_SCOPES)
        credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json() + "\n", encoding="utf-8")
    try:
        token_path.chmod(0o600)
    except OSError:
        pass
    return credentials


def authorize_channel(
    client_secrets: Path,
    token_path: Path,
    *,
    reauthorize: bool = False,
    expected_channel_id: str | None = None,
) -> dict[str, Any]:
    """Run OAuth without uploading and identify the selected YouTube channel."""
    try:
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "YouTube publishing dependencies are missing. Run "
            "`python -m pip install -r requirements-video-engine.txt`."
        ) from exc
    credentials = oauth_credentials(client_secrets, token_path, reauthorize=reauthorize)
    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    response = youtube.channels().list(part="snippet", mine=True).execute()
    items = response.get("items") or []
    if not items:
        raise RuntimeError("The authorized Google account has no selectable YouTube channel")
    channel = items[0]
    result = {
        "status": "authorized",
        "channel_id": channel.get("id"),
        "channel_title": (channel.get("snippet") or {}).get("title"),
        "token_path": str(token_path),
    }
    if expected_channel_id and result["channel_id"] != expected_channel_id:
        raise RuntimeError(
            f"Wrong YouTube channel selected: expected {expected_channel_id}, "
            f"got {result['channel_id']} ({result['channel_title']})"
        )
    write_json(token_path.parent / "channel.json", result)
    return result


def _resumable_upload(request: Any, *, max_retries: int = 10) -> dict[str, Any]:
    response = None
    retries = 0
    while response is None:
        try:
            progress, response = request.next_chunk()
            if progress:
                print(f"Upload progress: {round(progress.progress() * 100)}%", file=sys.stderr)
        except Exception as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)
            if status not in RETRIABLE_STATUS_CODES and not isinstance(exc, RETRIABLE_EXCEPTIONS):
                raise
            retries += 1
            if retries > max_retries:
                raise RuntimeError("YouTube upload failed after retry limit") from exc
            delay = random.uniform(0, min(2**retries, 64))
            print(f"Retriable upload error; retrying in {delay:.1f}s", file=sys.stderr)
            time.sleep(delay)
    if not response.get("id"):
        raise RuntimeError(f"YouTube returned an unexpected upload response: {response}")
    return response


def publish(
    *,
    video: Path,
    metadata_path: Path,
    thumbnail: Path | None,
    body: dict[str, Any],
    client_secrets: Path,
    token_path: Path,
    playlist_ids: list[str],
    auto_organize_course: bool,
    course_playlist_title: str,
    content_kind: str,
    full_lesson_video_id: str | None,
    notify_subscribers: bool,
    post_first_comment: bool,
    expected_channel_id: str | None,
) -> dict[str, Any]:
    try:
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError as exc:
        raise RuntimeError(
            "YouTube publishing dependencies are missing. Run "
            "`python -m pip install -r requirements-video-engine.txt`."
        ) from exc

    metadata = read_json(metadata_path)
    credentials = oauth_credentials(client_secrets, token_path)
    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    channel_response = youtube.channels().list(part="snippet", mine=True).execute()
    channels = channel_response.get("items") or []
    if not channels:
        raise RuntimeError("The OAuth token does not resolve to a YouTube channel")
    selected_channel = channels[0]
    selected_channel_id = selected_channel.get("id")
    selected_channel_title = (selected_channel.get("snippet") or {}).get("title")
    if expected_channel_id and selected_channel_id != expected_channel_id:
        raise RuntimeError(
            f"Wrong YouTube channel selected: expected {expected_channel_id}, "
            f"got {selected_channel_id} ({selected_channel_title}). No upload was started."
        )
    mime_type = mimetypes.guess_type(video.name)[0] or "video/*"
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(video), mimetype=mime_type, chunksize=8 * 1024 * 1024, resumable=True),
        notifySubscribers=notify_subscribers,
    )
    response = _resumable_upload(request)
    video_id = response["id"]

    thumbnail_set = False
    if thumbnail:
        thumbnail_mime = mimetypes.guess_type(thumbnail.name)[0] or "image/jpeg"
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(str(thumbnail), mimetype=thumbnail_mime, resumable=False),
        ).execute()
        thumbnail_set = True

    course_organization = None
    if auto_organize_course:
        course_organization = organize_course_upload(
            youtube,
            video_id=video_id,
            video_title=body["snippet"]["title"],
            content_kind=content_kind,
            course_playlist_title=course_playlist_title,
            full_lesson_video_id=full_lesson_video_id,
        )

    added_playlists: list[str] = []
    course_playlist_id = course_organization.get("playlist_id") if course_organization else None
    for playlist_id in dict.fromkeys(playlist_ids):
        if playlist_id == course_playlist_id:
            continue
        youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            },
        ).execute()
        added_playlists.append(playlist_id)

    comment_posted = False
    pinned_comment = str(metadata.get("pinned_comment") or "").strip()
    if post_first_comment and pinned_comment:
        youtube.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {"snippet": {"textOriginal": pinned_comment}},
                }
            },
        ).execute()
        comment_posted = True

    receipt = {
        "status": "uploaded",
        "video_id": video_id,
        "url": f"https://youtu.be/{video_id}",
        "channel_id": selected_channel_id,
        "channel_title": selected_channel_title,
        "privacy": body["status"]["privacyStatus"],
        "publish_at": body["status"].get("publishAt"),
        "thumbnail_set": thumbnail_set,
        "playlist_ids": added_playlists,
        "course_organization": course_organization,
        "first_comment_posted": comment_posted,
        "note": "The YouTube Data API can post the generated comment but cannot pin it.",
        "uploaded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    write_json(metadata_path.parent / "upload-result.json", receipt)
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publish a rendered MAV lesson to YouTube with metadata and thumbnail."
    )
    parser.add_argument("--run-id", help="MAV run ID; auto-resolves final.mp4 and youtube assets")
    parser.add_argument("--video", help="Explicit video path (overrides the run video)")
    parser.add_argument("--metadata", help="Explicit metadata.json path (overrides run metadata)")
    parser.add_argument("--thumbnail", help="Explicit thumbnail path (overrides run thumbnail)")
    parser.add_argument("--privacy", choices=("private", "unlisted", "public"), default="private")
    parser.add_argument("--publish-at", help="Future ISO-8601 time with timezone; requires private privacy")
    parser.add_argument("--category-id", default="27", help="YouTube category ID (27 is Education)")
    audience = parser.add_mutually_exclusive_group()
    audience.add_argument("--made-for-kids", action="store_true")
    audience.add_argument("--not-made-for-kids", action="store_true")
    parser.add_argument("--playlist-id", action="append", default=[], help="Playlist ID; repeat as needed")
    parser.add_argument(
        "--course-playlist-title",
        default=os.getenv("YOUTUBE_COURSE_PLAYLIST_TITLE", DEFAULT_COURSE_PLAYLIST_TITLE),
        help="Owned course playlist to create/reuse and maintain automatically",
    )
    parser.add_argument(
        "--content-kind",
        choices=("auto", "longform", "short"),
        default="auto",
        help="Controls playlist placement and lesson/Short navigation",
    )
    parser.add_argument(
        "--full-lesson-video-id",
        help="For a Short, link the corresponding uploaded full lesson when known",
    )
    parser.add_argument(
        "--skip-course-organization",
        action="store_true",
        help="Do not auto-manage the course playlist or previous/next links",
    )
    parser.add_argument("--notify-subscribers", action="store_true")
    parser.add_argument(
        "--post-first-comment",
        action="store_true",
        help="Post metadata.pinned_comment (the API cannot pin it)",
    )
    parser.add_argument(
        "--client-secrets",
        default=os.getenv("YOUTUBE_CLIENT_SECRETS", str(DEFAULT_CLIENT_SECRETS)),
        help="OAuth Desktop app client JSON",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("YOUTUBE_TOKEN_PATH", str(DEFAULT_TOKEN)),
        help="Private OAuth refresh-token cache",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate and print the request without OAuth/upload")
    parser.add_argument(
        "--confirm-upload",
        action="store_true",
        help="Required for a real upload, including private uploads",
    )
    parser.add_argument(
        "--authorize-only",
        action="store_true",
        help="Complete OAuth and verify the selected channel without uploading",
    )
    parser.add_argument(
        "--reauthorize",
        action="store_true",
        help="Ignore the cached token and choose a channel again; use with --authorize-only",
    )
    parser.add_argument(
        "--expected-channel-id",
        default=os.getenv("YOUTUBE_EXPECTED_CHANNEL_ID"),
        help="Abort before upload if OAuth selected a different YouTube channel",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        client_secrets = Path(args.client_secrets).expanduser().resolve()
        token_path = Path(args.token).expanduser().resolve()
        if args.reauthorize and not args.authorize_only:
            parser.error("--reauthorize must be used with --authorize-only")
        if args.authorize_only:
            authorization = authorize_channel(
                client_secrets,
                token_path,
                reauthorize=args.reauthorize,
                expected_channel_id=args.expected_channel_id,
            )
            print(json.dumps(authorization, indent=2, ensure_ascii=False))
            return 0
        video, metadata_path, thumbnail = resolve_assets(args)
        metadata = read_json(metadata_path)
        content_kind = args.content_kind
        if content_kind == "auto":
            content_kind = (
                "short"
                if metadata.get("reel_id") or "short" in video.name.lower()
                else "longform"
            )
        full_lesson_video_id = args.full_lesson_video_id
        if content_kind == "short" and not full_lesson_video_id:
            full_lesson_video_id = infer_full_lesson_video_id(metadata_path)
        made_for_kids = bool(args.made_for_kids)
        body = build_video_body(
            metadata,
            privacy=args.privacy,
            publish_at=args.publish_at,
            made_for_kids=made_for_kids,
            category_id=args.category_id,
        )
        plan = {
            "project": "capture-3494f",
            "video": str(video),
            "metadata": str(metadata_path),
            "thumbnail": str(thumbnail) if thumbnail else None,
            "playlist_ids": args.playlist_id,
            "auto_organize_course": not args.skip_course_organization,
            "course_playlist_title": args.course_playlist_title,
            "content_kind": content_kind,
            "full_lesson_video_id": full_lesson_video_id,
            "notify_subscribers": args.notify_subscribers,
            "post_first_comment": args.post_first_comment,
            "request": body,
        }
        if args.dry_run:
            print(json.dumps(plan, indent=2, ensure_ascii=False))
            return 0
        if not args.confirm_upload:
            parser.error("a real upload requires --confirm-upload (use --dry-run to inspect first)")
        receipt = publish(
            video=video,
            metadata_path=metadata_path,
            thumbnail=thumbnail,
            body=body,
            client_secrets=client_secrets,
            token_path=token_path,
            playlist_ids=args.playlist_id,
            auto_organize_course=not args.skip_course_organization,
            course_playlist_title=args.course_playlist_title,
            content_kind=content_kind,
            full_lesson_video_id=full_lesson_video_id,
            notify_subscribers=args.notify_subscribers,
            post_first_comment=args.post_first_comment,
            expected_channel_id=args.expected_channel_id,
        )
        print(json.dumps(receipt, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"YouTube publish failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
