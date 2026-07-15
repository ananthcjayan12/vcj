from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

from .constants import REQUIRED_ROOT_IDS
from .io_utils import sha256_text

CHAPTER_BLOCK_RE = re.compile(
    r"<!--\s*BEGIN CHAPTER (chapter_\d{2,3})\s*-->(.*?)<!--\s*END CHAPTER \1\s*-->",
    re.DOTALL,
)


@dataclass(frozen=True)
class ChapterBlock:
    chapter_id: str
    start: float
    end: float
    source: str
    full_source: str
    source_start: int
    source_end: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "chapter_id": self.chapter_id,
            "start": self.start,
            "end": self.end,
            "duration": self.end - self.start,
            "source_start": self.source_start,
            "source_end": self.source_end,
            "sha256": self.sha256,
        }


class ContractParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.tags: list[tuple[str, dict[str, str]]] = []
        self.scripts: list[tuple[dict[str, str], str]] = []
        self._script_attrs: dict[str, str] | None = None
        self._script_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value or "" for key, value in attrs}
        self.tags.append((tag, values))
        if values.get("id"):
            self.ids.append(values["id"])
        if tag == "script":
            self._script_attrs = values
            self._script_parts = []

    def handle_data(self, data: str) -> None:
        if self._script_attrs is not None:
            self._script_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._script_attrs is not None:
            self.scripts.append((self._script_attrs, "".join(self._script_parts)))
            self._script_attrs = None
            self._script_parts = []


def parse_document(html: str) -> ContractParser:
    parser = ContractParser()
    parser.feed(html)
    parser.close()
    return parser


def extract_chapter_blocks(html: str) -> list[ChapterBlock]:
    chapters: list[ChapterBlock] = []
    for match in CHAPTER_BLOCK_RE.finditer(html):
        chapter_id, source = match.group(1), match.group(2)
        tag_match = re.search(
            rf"<[^>]+data-chapter-id=[\"']{re.escape(chapter_id)}[\"'][^>]*>",
            source,
            flags=re.IGNORECASE,
        )
        if not tag_match:
            start = end = -1.0
        else:
            tag = tag_match.group(0)
            start_match = re.search(r"data-start=[\"']([0-9.]+)[\"']", tag)
            end_match = re.search(r"data-end=[\"']([0-9.]+)[\"']", tag)
            start = float(start_match.group(1)) if start_match else -1.0
            end = float(end_match.group(1)) if end_match else -1.0
        chapters.append(
            ChapterBlock(
                chapter_id=chapter_id,
                start=start,
                end=end,
                source=source,
                full_source=match.group(0),
                source_start=match.start(),
                source_end=match.end(),
                sha256=sha256_text(match.group(0)),
            )
        )
    return chapters


def missing_root_ids(parser: ContractParser) -> list[str]:
    present = set(parser.ids)
    return [root_id for root_id in REQUIRED_ROOT_IDS if root_id not in present]
