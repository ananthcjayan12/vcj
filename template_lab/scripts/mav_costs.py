from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mav_schema import read_json, run_dir, write_json

_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _run_path() -> Path | None:
    run_id = os.getenv("MAV_RUN_ID", "").strip()
    if not run_id:
        return None
    return run_dir(run_id)


def _price_config() -> dict[str, Any]:
    raw = os.getenv("MAV_MODEL_PRICING_JSON", "").strip()
    if raw:
        try:
            payload = json.loads(raw)
            return payload if isinstance(payload, dict) else {}
        except json.JSONDecodeError:
            return {}
    path = os.getenv("MAV_MODEL_PRICING_PATH", "").strip()
    candidates = [Path(path)] if path else []
    candidates.append(Path(__file__).resolve().parents[1] / "model_pricing.json")
    for candidate in candidates:
        if candidate.exists():
            try:
                payload = read_json(candidate)
                return payload if isinstance(payload, dict) else {}
            except Exception:
                return {}
    return {}


def _model_price(provider: str, model: str) -> dict[str, float] | None:
    pricing = _price_config()
    models = pricing.get("models") if isinstance(pricing.get("models"), dict) else pricing
    keys = [f"{provider}:{model}", model, f"{provider}:*"]
    for key in keys:
        value = models.get(key) if isinstance(models, dict) else None
        if isinstance(value, dict):
            try:
                return {
                    "input_usd_per_million": float(value.get("input_usd_per_million", value.get("input", 0))),
                    "output_usd_per_million": float(value.get("output_usd_per_million", value.get("output", 0))),
                    "cached_input_usd_per_million": float(
                        value.get("cached_input_usd_per_million", value.get("cached_input", value.get("input_usd_per_million", value.get("input", 0))))
                    ),
                }
            except (TypeError, ValueError):
                return None
    return None


def _audio_price(provider: str, model: str) -> dict[str, float] | None:
    pricing = _price_config()
    audio = pricing.get("audio") if isinstance(pricing.get("audio"), dict) else {}
    keys = [f"{provider}:{model}", model, f"{provider}:*"]
    for key in keys:
        value = audio.get(key) if isinstance(audio, dict) else None
        if isinstance(value, dict):
            try:
                return {
                    "usd_per_1k_chars": float(value.get("usd_per_1k_chars", 0)),
                }
            except (TypeError, ValueError):
                return None
    return None


def _usage_int(usage: dict[str, Any], *keys: str) -> int:
    for key in keys:
        value = usage
        for part in key.split("."):
            value = value.get(part) if isinstance(value, dict) else None
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0
    return 0


def _ledger_path(run_path: Path) -> Path:
    return run_path / "costs" / "model_usage.json"


def _summary_path(run_path: Path) -> Path:
    return run_path / "costs" / "summary.json"


def _load_ledger(run_path: Path) -> dict[str, Any]:
    path = _ledger_path(run_path)
    if not path.exists():
        return {"version": "1.0", "records": []}
    try:
        payload = read_json(path)
        if isinstance(payload, dict) and isinstance(payload.get("records"), list):
            return payload
    except Exception:
        pass
    return {"version": "1.0", "records": []}


def _summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    priced_total = 0.0
    unpriced_records = 0
    by_task: dict[str, dict[str, Any]] = {}
    for record in records:
        task = str(record.get("task") or record.get("provider") or "unknown")
        item = by_task.setdefault(
            task,
            {
                "calls": 0,
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "audio_chars": 0,
                "estimated_cost_usd": 0.0,
                "unpriced_calls": 0,
            },
        )
        item["calls"] += 1
        item["input_tokens"] += int(record.get("input_tokens") or 0)
        item["cached_input_tokens"] += int(record.get("cached_input_tokens") or 0)
        item["output_tokens"] += int(record.get("output_tokens") or 0)
        item["audio_chars"] += int(record.get("audio_chars") or 0)
        cost = record.get("estimated_cost_usd")
        if cost is None:
            item["unpriced_calls"] += 1
            unpriced_records += 1
        else:
            item["estimated_cost_usd"] += float(cost)
            priced_total += float(cost)
    for item in by_task.values():
        item["estimated_cost_usd"] = round(float(item["estimated_cost_usd"]), 6)
    return {
        "version": "1.0",
        "updated_at": _now(),
        "estimated_cost_usd": round(priced_total, 6),
        "priced_records": len(records) - unpriced_records,
        "unpriced_records": unpriced_records,
        "by_task": by_task,
        "note": "Costs are estimates from configured pricing. Records remain useful for token/character accounting even when pricing is unconfigured.",
    }


def _write_ledger(run_path: Path, ledger: dict[str, Any]) -> None:
    records = ledger.get("records", [])
    ledger["updated_at"] = _now()
    ledger["summary"] = _summarize(records)
    write_json(_ledger_path(run_path), ledger)
    write_json(_summary_path(run_path), ledger["summary"])


def record_model_usage(
    *,
    task: str,
    provider: str,
    model: str,
    usage: dict[str, Any],
    response_id: str | None = None,
) -> None:
    run_path = _run_path()
    if run_path is None:
        return
    input_tokens = _usage_int(usage, "input_tokens", "prompt_tokens", "prompt_token_count")
    output_tokens = _usage_int(usage, "output_tokens", "completion_tokens", "candidates_token_count")
    total_tokens = _usage_int(usage, "total_tokens", "total_token_count") or input_tokens + output_tokens
    cached_tokens = _usage_int(
        usage,
        "cache_read_input_tokens",
        "cached_input_tokens",
        "prompt_tokens_details.cached_tokens",
        "cached_content_token_count",
    )
    price = _model_price(provider, model)
    estimated_cost = None
    if price:
        paid_input = max(0, input_tokens - cached_tokens)
        estimated_cost = (
            paid_input * price["input_usd_per_million"]
            + cached_tokens * price["cached_input_usd_per_million"]
            + output_tokens * price["output_usd_per_million"]
        ) / 1_000_000
    record = {
        "timestamp": _now(),
        "kind": "model",
        "task": task,
        "provider": provider,
        "model": model,
        "response_id": response_id,
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(estimated_cost, 6) if estimated_cost is not None else None,
        "pricing_configured": bool(price),
    }
    with _LOCK:
        ledger = _load_ledger(run_path)
        ledger["records"].append(record)
        _write_ledger(run_path, ledger)


def record_audio_usage(
    *,
    provider: str,
    model: str,
    voice_id: str,
    text: str,
    cache_reused: bool,
) -> None:
    run_path = _run_path()
    if run_path is None:
        return
    chars = len(text)
    price = _audio_price(provider, model)
    estimated_cost = 0.0 if cache_reused else (None if not price else chars / 1000 * price["usd_per_1k_chars"])
    record = {
        "timestamp": _now(),
        "kind": "audio",
        "task": "audio_generation",
        "provider": provider,
        "model": model,
        "voice_id": voice_id,
        "audio_chars": chars,
        "cache_reused": cache_reused,
        "estimated_cost_usd": round(estimated_cost, 6) if estimated_cost is not None else None,
        "pricing_configured": bool(price) or cache_reused,
    }
    with _LOCK:
        ledger = _load_ledger(run_path)
        ledger["records"].append(record)
        _write_ledger(run_path, ledger)


def cost_summary_for_run(run_path: Path) -> dict[str, Any] | None:
    path = _summary_path(run_path)
    if not path.exists():
        return None
    try:
        payload = read_json(path)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None
