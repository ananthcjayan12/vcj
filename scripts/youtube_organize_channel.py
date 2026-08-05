#!/usr/bin/env python3
"""Create the IGCSE Physics course playlist and enrich uploaded descriptions."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


ROOT = Path(__file__).resolve().parents[1]
TOKEN = ROOT / ".youtube" / "token.json"
CHANNEL = ROOT / ".youtube" / "channel.json"
RESULT = ROOT / ".youtube" / "channel-organization-result.json"
SCOPES = (
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
)
PLAYLIST_TITLE = "Cambridge IGCSE Physics (0625) — Complete Course"
PLAYLIST_DESCRIPTION = (
    "Animated Cambridge IGCSE Physics (0625) lessons from IGCSE Visualised, "
    "arranged in syllabus learning order. Includes clear explanations, worked "
    "examples, exam skills and selected revision Shorts."
)


LESSONS: list[dict[str, Any]] = [
    {
        "video_id": "IjCG0Dr9zsA",
        "run": "physics-1-1-recipe-smoke",
        "label": "Physical Quantities & Measurement Techniques",
        "chapters": [
            ("paragraph_01", "Can you measure below one ruler division?"),
            ("paragraph_02", "Choosing measurement tools"),
            ("paragraph_03", "How to read a ruler"),
            ("paragraph_04", "Reading a measuring cylinder"),
            ("paragraph_05", "Limits of a single measurement"),
            ("paragraph_06", "Measuring the thickness of paper"),
            ("paragraph_07", "Measuring short time intervals"),
            ("paragraph_09", "Timing a pendulum accurately"),
            ("paragraph_11", "Magnitude and direction"),
            ("paragraph_12", "Scalars and vectors defined"),
            ("paragraph_13", "Examples of scalar quantities"),
            ("paragraph_14", "Examples of vector quantities"),
            ("paragraph_15", "Speed vs velocity"),
            ("paragraph_16", "How vector diagrams work"),
            ("paragraph_17", "Finding a resultant vector"),
            ("paragraph_18", "Worked example: 3–4–5 resultant"),
            ("paragraph_19", "Resultant-vector challenge"),
            ("paragraph_21", "Lesson summary"),
        ],
    },
    {
        "video_id": "Z2FedTD9k1E",
        "run": "physics-1-2-v01",
        "label": "Speed, Velocity & Acceleration",
        "chapters": [
            ("paragraph_01", "Why a skydiver stops accelerating"),
            ("paragraph_02", "What speed means"),
            ("paragraph_04", "The speed equation"),
            ("paragraph_05", "Speed vs velocity"),
            ("paragraph_07", "Average speed"),
            ("paragraph_08", "Worked example: average speed"),
            ("paragraph_09", "Distance–time graphs"),
            ("paragraph_10", "Gradient gives speed"),
            ("paragraph_12", "What curved graph lines mean"),
            ("paragraph_13", "Acceleration explained"),
            ("paragraph_14", "Speed–time graphs"),
            ("paragraph_15", "Gradient gives acceleration"),
            ("paragraph_16", "Deceleration and negative acceleration"),
            ("paragraph_18", "Area under a speed–time graph"),
            ("paragraph_20", "Acceleration of free fall"),
            ("paragraph_21", "Air resistance and terminal velocity"),
            ("paragraph_23", "Cyclist graph challenge"),
            ("paragraph_24", "Lesson summary"),
        ],
    },
    {
        "video_id": "DDGokv2JBCs",
        "run": "physics-1-3-v01",
        "label": "Mass vs Weight",
        "chapters": [
            ("paragraph_01", "Why astronauts jump higher on the Moon"),
            ("paragraph_02", "Kilograms and newtons"),
            ("paragraph_03", "Beam balance vs spring balance"),
            ("paragraph_05", "What mass means"),
            ("paragraph_06", "What weight means"),
            ("paragraph_08", "Gravitational fields"),
            ("paragraph_09", "Gravitational field strength: g = W/m"),
            ("paragraph_10", "g and free-fall acceleration"),
            ("paragraph_11", "Worked example: W = mg"),
            ("paragraph_12", "Finding gravitational field strength"),
            ("paragraph_13", "Why mass does not change on the Moon"),
            ("paragraph_14", "Measuring mass and weight"),
            ("paragraph_16", "Lesson summary"),
        ],
    },
    {
        "video_id": "H9rCG_5qw_o",
        "run": "physics-1-4-v01",
        "label": "Density",
        "chapters": [
            ("paragraph_01", "Same size, different mass"),
            ("paragraph_03", "Density as mass per unit volume"),
            ("paragraph_04", "The density equation: ρ = m/V"),
            ("paragraph_05", "Worked example: solid density"),
            ("paragraph_06", "Measuring the density of a liquid"),
            ("paragraph_07", "Density of a regular solid"),
            ("paragraph_08", "Volume of an irregular solid"),
            ("paragraph_10", "Worked example: displacement"),
            ("paragraph_11", "Mass is not the same as density"),
            ("paragraph_12", "Using density to predict floating"),
            ("paragraph_13", "Floating challenge"),
            ("paragraph_14", "How non-mixing liquids layer"),
            ("paragraph_16", "Choosing the correct practical method"),
            ("paragraph_17", "Lesson summary"),
        ],
    },
    {
        "video_id": "9mU6u_TtzhM",
        "run": "physics-1-5-1-v01",
        "label": "Resultant Forces, Friction & Springs",
        "chapters": [
            ("paragraph_01", "Do moving objects need a constant force?"),
            ("paragraph_02", "Resultant force"),
            ("paragraph_03", "Combining forces in a straight line"),
            ("paragraph_04", "How forces change velocity"),
            ("paragraph_05", "Newton’s second law: F = ma"),
            ("paragraph_06", "Balanced forces and constant velocity"),
            ("paragraph_07", "Forces in circular motion"),
            ("paragraph_08", "Force, speed, mass and radius"),
            ("paragraph_09", "Friction and drag"),
            ("paragraph_10", "Spring extension practical"),
            ("paragraph_11", "Load–extension graphs"),
            ("paragraph_12", "Spring constant: k = F/x"),
            ("paragraph_13", "Limit of proportionality"),
            ("paragraph_14", "Car-force challenge"),
        ],
    },
    {
        "video_id": "2vO3LAoAw7Q",
        "run": "physics-1-5-2-v01",
        "label": "Moments & Equilibrium",
        "chapters": [
            ("paragraph_01", "Why a door handle makes turning easier"),
            ("paragraph_03", "Turning effect and distance from a pivot"),
            ("paragraph_05", "Moment of a force"),
            ("paragraph_06", "Moment = force × perpendicular distance"),
            ("paragraph_07", "Reading a moments diagram"),
            ("paragraph_08", "Worked example: calculating a moment"),
            ("paragraph_09", "Why distance must be perpendicular"),
            ("paragraph_10", "The principle of moments"),
            ("paragraph_11", "Worked example: balanced beam"),
            ("paragraph_12", "Two conditions for equilibrium"),
            ("paragraph_14", "Several forces around one pivot"),
            ("paragraph_15", "Worked example: multiple moments"),
            ("paragraph_16", "Metre-rule practical"),
            ("paragraph_17", "Knowledge check"),
            ("paragraph_18", "Lesson summary"),
        ],
    },
    {
        "video_id": "beOg-6h0AEg",
        "run": "physics-1-5-3-v01",
        "label": "Centre of Gravity & Stability",
        "chapters": [
            ("paragraph_01", "Why a ruler balances at one point"),
            ("paragraph_02", "Gravity acts throughout an object"),
            ("paragraph_04", "Can the balance point lie outside an object?"),
            ("paragraph_05", "Centre of gravity defined"),
            ("paragraph_06", "Centre of gravity and turning effects"),
            ("paragraph_07", "The plumb-line method"),
            ("paragraph_08", "Finding the centre of gravity practically"),
            ("paragraph_09", "Centre of gravity outside the material"),
            ("paragraph_10", "Comparing stable and unstable objects"),
            ("paragraph_11", "Base width and centre-of-gravity height"),
            ("paragraph_12", "The condition for toppling"),
            ("paragraph_13", "Reading stability diagrams"),
            ("paragraph_14", "Sports car vs tall van"),
            ("paragraph_15", "Knowledge check"),
            ("paragraph_16", "Lesson summary"),
        ],
    },
    {
        "video_id": "aHuzobZzNu0",
        "run": "physics-1-6-v01",
        "label": "Momentum",
        "chapters": [
            ("paragraph_01", "Which vehicle is harder to stop?"),
            ("paragraph_02", "Mass and velocity"),
            ("paragraph_05", "Momentum defined"),
            ("paragraph_06", "The momentum equation: p = mv"),
            ("paragraph_07", "Worked example: car momentum"),
            ("paragraph_08", "Momentum is a vector"),
            ("paragraph_09", "Before and after a collision"),
            ("paragraph_10", "Conservation of momentum"),
            ("paragraph_11", "Reading collision diagrams"),
            ("paragraph_12", "Worked example: trolleys stick together"),
            ("paragraph_13", "Collision challenge"),
            ("paragraph_14", "Force changes momentum"),
            ("paragraph_15", "Impulse: FΔt = Δp"),
            ("paragraph_16", "Worked example: impulse and force"),
            ("paragraph_17", "Force as rate of momentum change"),
            ("paragraph_18", "F = Δp/Δt"),
            ("paragraph_20", "How crumple zones reduce force"),
            ("paragraph_21", "Lesson summary"),
        ],
    },
    {
        "video_id": "KT2QvmA0q1U",
        "run": "physics-1-7-1-v01",
        "label": "Energy Stores, Transfers & Conservation",
        "chapters": [
            ("paragraph_01", "Where does the extra motion come from?"),
            ("paragraph_02", "The law of conservation of energy"),
            ("paragraph_03", "Energy changes in a falling ball"),
            ("paragraph_04", "GPE decreases as kinetic energy increases"),
            ("paragraph_05", "The 7 main energy stores"),
            ("paragraph_06", "The 4 energy-transfer pathways"),
            ("paragraph_07", "How to read energy-flow diagrams"),
            ("paragraph_08", "Kinetic energy: Ek = ½mv²"),
            ("paragraph_09", "Gravitational potential energy: ΔEp = mgΔh"),
            ("paragraph_10", "Worked example: kinetic energy"),
            ("paragraph_11", "Worked example: GPE loss and KE gain"),
            ("paragraph_12", "Where ‘lost’ energy goes"),
            ("paragraph_13", "Energy in a closed system"),
            ("paragraph_14", "How to read Sankey diagrams"),
            ("paragraph_15", "Multi-stage lamp Sankey diagram"),
            ("paragraph_16", "Energy transfers in a kettle"),
            ("paragraph_17", "Motor lifting a load"),
            ("paragraph_18", "Lesson summary"),
        ],
    },
]

SHORT = {
    "video_id": "YzOQ56MRtHc",
    "full_lesson_id": "IjCG0Dr9zsA",
    "label": "Measure Below 1 mm With an Ordinary Ruler #Shorts",
    "chapters": [
        (0, "Why one page is too thin to measure"),
        (18, "Measure a stack of pages"),
        (28, "Divide to find one page’s thickness"),
    ],
}


def youtube_client() -> Any:
    credentials = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def timestamp(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def lesson_chapters(lesson: dict[str, Any]) -> list[tuple[int, str]]:
    timing_path = ROOT / "template_lab" / "runs" / lesson["run"] / "audio_word_timestamps.json"
    payload = json.loads(timing_path.read_text(encoding="utf-8"))
    starts: dict[str, float] = {}
    for word in payload.get("words", []):
        starts.setdefault(str(word["paragraph_id"]), float(word["start"]))
    chapters = []
    for paragraph_id, title in lesson["chapters"]:
        if paragraph_id not in starts:
            raise RuntimeError(f"Missing {paragraph_id} in {timing_path}")
        chapters.append((round(starts[paragraph_id]), title))
    if not chapters or chapters[0][0] != 0:
        raise RuntimeError(f"{lesson['run']} must start at 00:00")
    if any(b[0] - a[0] < 10 for a, b in zip(chapters, chapters[1:])):
        raise RuntimeError(f"{lesson['run']} contains chapters less than 10 seconds apart")
    return chapters


def strip_old_navigation_and_chapters(description: str) -> str:
    lines = description.replace("\r\n", "\n").splitlines()
    kept: list[str] = []
    skip_link = False
    for line in lines:
        stripped = line.strip()
        if stripped in {"— COURSE LINKS —", "— CHAPTERS —"}:
            break
        if re.match(r"^▶️?\s*(Previous|Next) lesson\b", stripped, re.I):
            skip_link = True
            continue
        if stripped.startswith("📘 Complete IGCSE Physics course:"):
            skip_link = True
            continue
        if stripped in {
            "[ADD PLAYLIST LINK]",
            "[ADD PREVIOUS VIDEO LINK]",
            "[ADD NEXT VIDEO LINK]",
            "[ADD FULL LESSON LINK]",
        }:
            continue
        if skip_link:
            if not stripped or re.match(r"^\[?https?://", stripped):
                continue
            skip_link = False
        if re.match(r"^\d{1,2}:\d{2}(?::\d{2})?\s+\S", stripped):
            continue
        kept.append(line.rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def description_for_lesson(
    existing: str,
    index: int,
    playlist_url: str,
    chapters: list[tuple[int, str]],
) -> str:
    links = ["— COURSE LINKS —", f"📚 Complete course playlist: {playlist_url}"]
    if index > 0:
        previous = LESSONS[index - 1]
        links.append(f"⬅ Previous lesson — {previous['label']}: https://youtu.be/{previous['video_id']}")
    if index + 1 < len(LESSONS):
        following = LESSONS[index + 1]
        links.append(f"➡ Next lesson — {following['label']}: https://youtu.be/{following['video_id']}")
    else:
        links.append("➡ Next lesson: coming soon")
    chapter_lines = ["— CHAPTERS —", *[f"{timestamp(sec)} {title}" for sec, title in chapters]]
    return "\n\n".join(
        [strip_old_navigation_and_chapters(existing), "\n".join(links), "\n".join(chapter_lines)]
    )


def description_for_short(existing: str, playlist_url: str) -> str:
    links = [
        "— COURSE LINKS —",
        f"🎬 Full lesson: https://youtu.be/{SHORT['full_lesson_id']}",
        f"📚 Complete course playlist: {playlist_url}",
    ]
    chapter_lines = [
        "— TIMELINE —",
        *[f"{timestamp(sec)} {title}" for sec, title in SHORT["chapters"]],
    ]
    return "\n\n".join(
        [strip_old_navigation_and_chapters(existing), "\n".join(links), "\n".join(chapter_lines)]
    )


def fetch_uploads(youtube: Any, uploads_id: str) -> dict[str, dict[str, Any]]:
    ids: list[str] = []
    page = None
    while True:
        response = youtube.playlistItems().list(
            part="contentDetails", playlistId=uploads_id, maxResults=50, pageToken=page
        ).execute()
        ids.extend(item["contentDetails"]["videoId"] for item in response.get("items", []))
        page = response.get("nextPageToken")
        if not page:
            break
    videos: dict[str, dict[str, Any]] = {}
    for start in range(0, len(ids), 50):
        response = youtube.videos().list(
            part="snippet,status", id=",".join(ids[start : start + 50]), maxResults=50
        ).execute()
        videos.update({item["id"]: item for item in response.get("items", [])})
    return videos


def find_playlist(youtube: Any, title: str) -> dict[str, Any] | None:
    page = None
    while True:
        response = youtube.playlists().list(
            part="snippet,status,contentDetails", mine=True, maxResults=50, pageToken=page
        ).execute()
        for item in response.get("items", []):
            if item.get("snippet", {}).get("title") == title:
                return item
        page = response.get("nextPageToken")
        if not page:
            return None


def update_video(youtube: Any, video: dict[str, Any], description: str) -> None:
    old = video["snippet"]
    snippet = {
        "title": old["title"],
        "description": description,
        "categoryId": old["categoryId"],
    }
    for key in ("tags", "defaultLanguage", "defaultAudioLanguage"):
        if key in old:
            snippet[key] = old[key]
    youtube.videos().update(part="snippet", body={"id": video["id"], "snippet": snippet}).execute()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Apply changes; otherwise print a dry run")
    args = parser.parse_args()

    youtube = youtube_client()
    expected = json.loads(CHANNEL.read_text(encoding="utf-8"))["channel_id"]
    channel = youtube.channels().list(part="snippet,contentDetails", mine=True).execute()["items"][0]
    if channel["id"] != expected:
        raise RuntimeError(f"Wrong channel: expected {expected}, got {channel['id']}")
    uploads_id = channel["contentDetails"]["relatedPlaylists"]["uploads"]
    videos = fetch_uploads(youtube, uploads_id)
    planned_ids = [lesson["video_id"] for lesson in LESSONS] + [SHORT["video_id"]]
    missing = [video_id for video_id in planned_ids if video_id not in videos]
    unexpected = [video_id for video_id in videos if video_id not in planned_ids]
    if missing or unexpected:
        raise RuntimeError(f"Upload inventory mismatch; missing={missing}, unexpected={unexpected}")

    playlist = find_playlist(youtube, PLAYLIST_TITLE)
    if not playlist and args.apply:
        playlist = youtube.playlists().insert(
            part="snippet,status",
            body={
                "snippet": {"title": PLAYLIST_TITLE, "description": PLAYLIST_DESCRIPTION},
                "status": {"privacyStatus": "public"},
            },
        ).execute()
    playlist_id = playlist["id"] if playlist else "<new-playlist-id>"
    playlist_url = (
        f"https://www.youtube.com/playlist?list={playlist_id}"
        if playlist
        else "https://www.youtube.com/playlist?list=<new-playlist-id>"
    )

    updates: list[dict[str, Any]] = []
    for index, lesson in enumerate(LESSONS):
        chapters = lesson_chapters(lesson)
        description = description_for_lesson(
            videos[lesson["video_id"]]["snippet"].get("description", ""),
            index,
            playlist_url,
            chapters,
        )
        if len(description) > 5000:
            raise RuntimeError(f"Description too long for {lesson['video_id']}: {len(description)}")
        updates.append(
            {
                "video_id": lesson["video_id"],
                "title": videos[lesson["video_id"]]["snippet"]["title"],
                "description_length": len(description),
                "chapters": [f"{timestamp(sec)} {title}" for sec, title in chapters],
                "description": description,
            }
        )
    short_description = description_for_short(
        videos[SHORT["video_id"]]["snippet"].get("description", ""), playlist_url
    )
    updates.append(
        {
            "video_id": SHORT["video_id"],
            "title": videos[SHORT["video_id"]]["snippet"]["title"],
            "description_length": len(short_description),
            "chapters": [f"{timestamp(sec)} {title}" for sec, title in SHORT["chapters"]],
            "description": short_description,
        }
    )

    if args.apply:
        existing_items: set[str] = set()
        # The API can return playlistNotFound when playlistItems.list is called
        # on a just-created, still-empty playlist. The playlist resource's item
        # count is authoritative, so skip that query until at least one item exists.
        if int(playlist.get("contentDetails", {}).get("itemCount", 0)) > 0:
            page = None
            while True:
                response = youtube.playlistItems().list(
                    part="contentDetails", playlistId=playlist_id, maxResults=50, pageToken=page
                ).execute()
                existing_items.update(
                    item["contentDetails"]["videoId"] for item in response.get("items", [])
                )
                page = response.get("nextPageToken")
                if not page:
                    break
        for position, video_id in enumerate(planned_ids):
            if video_id not in existing_items:
                youtube.playlistItems().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "playlistId": playlist_id,
                            "position": position,
                            "resourceId": {"kind": "youtube#video", "videoId": video_id},
                        }
                    },
                ).execute()
        for update in updates:
            update_video(youtube, videos[update["video_id"]], update["description"])

    result = {
        "mode": "applied" if args.apply else "dry-run",
        "channel_id": channel["id"],
        "channel_title": channel["snippet"]["title"],
        "playlist_id": playlist_id,
        "playlist_url": playlist_url,
        "playlist_order": planned_ids,
        "updates": updates,
    }
    if args.apply:
        RESULT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        try:
            RESULT.chmod(0o600)
        except OSError:
            pass
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
