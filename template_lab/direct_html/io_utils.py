from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(payload: Any) -> str:
    return sha256_text(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def sync_direct_cost_records(run_path: Path) -> dict[str, Any]:
    """Mirror direct-HTML model usage into the direct_html artifact tree.

    The authoritative run-level ledger remains untouched.  This filtered copy makes
    a direct composition self-contained for comparisons with the legacy route.
    """
    source = read_json(run_path / "costs" / "model_usage.json", {}) or {}
    records = [
        record
        for record in source.get("records", [])
        if str(record.get("task", "")).startswith("direct_html_")
    ]
    total_cost = sum(float(record.get("estimated_cost_usd") or 0) for record in records)
    unpriced = sum(1 for record in records if record.get("estimated_cost_usd") is None)
    by_task: dict[str, dict[str, Any]] = {}
    for record in records:
        task = str(record.get("task") or "unknown")
        item = by_task.setdefault(
            task,
            {
                "calls": 0,
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "estimated_cost_usd": 0.0,
                "unpriced_calls": 0,
            },
        )
        item["calls"] += 1
        for key in ("input_tokens", "cached_input_tokens", "output_tokens", "total_tokens"):
            item[key] += int(record.get(key) or 0)
        if record.get("estimated_cost_usd") is None:
            item["unpriced_calls"] += 1
        else:
            item["estimated_cost_usd"] += float(record["estimated_cost_usd"])
    for item in by_task.values():
        item["estimated_cost_usd"] = round(item["estimated_cost_usd"], 6)
    summary = {
        "version": "1.0",
        "updated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "calls": len(records),
        "input_tokens": sum(int(record.get("input_tokens") or 0) for record in records),
        "cached_input_tokens": sum(int(record.get("cached_input_tokens") or 0) for record in records),
        "output_tokens": sum(int(record.get("output_tokens") or 0) for record in records),
        "total_tokens": sum(int(record.get("total_tokens") or 0) for record in records),
        "estimated_cost_usd": round(total_cost, 6),
        "priced_records": len(records) - unpriced,
        "unpriced_records": unpriced,
        "by_task": by_task,
    }
    ledger = {
        "version": "1.0",
        "records": records,
        "summary": summary,
        "source": "../../costs/model_usage.json",
    }
    write_json(run_path / "direct_html" / "costs" / "model_usage.json", ledger)
    write_json(run_path / "direct_html" / "costs" / "summary.json", summary)
    return summary
