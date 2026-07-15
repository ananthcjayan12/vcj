from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .html_contract import extract_chapter_blocks
from .io_utils import write_json


def build_chapter_index(master_path: Path, *, repair_state: dict[str, Any] | None = None) -> dict[str, Any]:
    html = master_path.read_text(encoding="utf-8")
    repair_state = repair_state or {}
    chapters = []
    for block in extract_chapter_blocks(html):
        paragraph_ids = sorted(set(re.findall(r"paragraph_\d{2,3}", block.source)))
        objective_ids = sorted(set(re.findall(r"\b\d+_\d+_[A-Z]\d{2}\b", block.source)))
        chapters.append(
            {
                **block.to_dict(),
                "paragraph_ids": paragraph_ids,
                "objective_ids": objective_ids,
                "repair_count": int((repair_state.get(block.chapter_id) or {}).get("repair_count", 0)),
                "status": (repair_state.get(block.chapter_id) or {}).get("status", "uninspected"),
            }
        )
    payload = {"version": "1.0", "master": str(master_path), "chapter_count": len(chapters), "chapters": chapters}
    write_json(master_path.parent / "chapter_index.json", payload)
    return payload
