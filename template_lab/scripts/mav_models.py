from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mav_schema import LAB_ROOT
from mav_costs import record_model_usage

PROMPT_MODEL_MAPPING_PATH = LAB_ROOT / "prompts" / "prompt_model_mapping.json"
DEFAULT_MODEL_MAX_TOKENS = 64000
GEMINI_TIMEOUT_MILLISECONDS = 600_000
DEFAULT_MODEL_TIMEOUT_SECONDS = 600
ZAI_CHAT_COMPLETIONS_URL = "https://api.z.ai/api/paas/v4/chat/completions"
MOONSHOT_CHAT_COMPLETIONS_URL = "https://api.moonshot.ai/v1/chat/completions"
SUPPORTED_MODEL_PROVIDERS = {"anthropic", "gemini", "zai", "moonshot"}
GEMINI_JSON_SCHEMA_KEYS = {
    "$id",
    "$defs",
    "$ref",
    "$anchor",
    "type",
    "format",
    "title",
    "description",
    "enum",
    "items",
    "prefixItems",
    "minItems",
    "maxItems",
    "minimum",
    "maximum",
    "anyOf",
    "oneOf",
    "properties",
    "additionalProperties",
    "required",
    "propertyOrdering",
}
GEMINI_MAX_SCHEMA_ENUM_VALUES = 20


@dataclass(frozen=True)
class ResolvedModelConfig:
    task: str
    provider: str
    model: str
    max_tokens: int


def load_env() -> None:
    for path in (LAB_ROOT / ".env", LAB_ROOT.parent / ".env"):
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _prompt_model_mapping() -> dict[str, Any]:
    if not PROMPT_MODEL_MAPPING_PATH.exists():
        return {}
    payload = json.loads(PROMPT_MODEL_MAPPING_PATH.read_text(encoding="utf-8"))
    return payload.get("tasks", {})


def configured_models() -> dict[str, Any]:
    return _prompt_model_mapping()


def _normalize_provider(provider: str | None) -> str:
    normalized = (provider or "").strip().lower()
    aliases = {
        "google": "gemini",
        "google-gemini": "gemini",
        "claude": "anthropic",
        "glm": "zai",
        "z.ai": "zai",
        "zhipu": "zai",
        "bigmodel": "zai",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in SUPPORTED_MODEL_PROVIDERS:
        raise RuntimeError(
            f"Unsupported model provider {provider!r}. "
            f"Supported providers: {', '.join(sorted(SUPPORTED_MODEL_PROVIDERS))}"
        )
    return normalized


def _provider_for_task(task: str) -> str:
    config = configured_models().get(task)
    if not config:
        raise KeyError(f"No model configured for task {task}")

    task_env = config.get("provider_env_var") or f"MAV_{task.upper()}_PROVIDER"
    provider = os.getenv(task_env) or os.getenv("MAV_MODEL_PROVIDER") or config.get("provider") or "anthropic"
    return _normalize_provider(provider)


def _model_for_task(task: str, provider: str) -> str:
    config = configured_models().get(task)
    if not config:
        raise KeyError(f"No model configured for task {task}")

    env_var = config.get("env_var") or f"MAV_{task.upper()}_MODEL"
    provider_model_env = f"MAV_{task.upper()}_{provider.upper()}_MODEL"
    env_model = os.getenv(provider_model_env) or os.getenv(env_var)
    if env_model:
        _raise_if_model_provider_mismatch(env_model, provider, provider_model_env if os.getenv(provider_model_env) else env_var)
        return env_model

    provider_models = config.get("provider_models")
    if isinstance(provider_models, dict) and provider_models.get(provider):
        return provider_models[provider]
    if isinstance(provider_models, dict) and provider not in provider_models:
        raise RuntimeError(f"No {provider} model configured for task {task}")
    return config["model"]


def _raise_if_model_provider_mismatch(model: str, provider: str, source: str) -> None:
    normalized = model.strip().lower()
    if provider == "gemini" and not (normalized.startswith("gemini-") or normalized.startswith("models/gemini-")):
        raise RuntimeError(f"{source}={model!r} does not look like a Gemini model while provider is gemini")
    if provider == "anthropic" and not normalized.startswith("claude-"):
        raise RuntimeError(f"{source}={model!r} does not look like a Claude model while provider is anthropic")
    if provider == "zai" and not normalized.startswith("glm-"):
        raise RuntimeError(f"{source}={model!r} does not look like a Z.AI GLM model while provider is zai")


def _positive_int(value: Any, label: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{label} must be a positive integer") from exc
    if parsed <= 0:
        raise RuntimeError(f"{label} must be a positive integer")
    return parsed


def _max_tokens_for_task(task: str, provider: str, requested: int | None) -> int:
    task_env = f"MAV_{task.upper()}_MAX_TOKENS"
    provider_env = f"MAV_{provider.upper()}_MAX_TOKENS"
    env_vars = [task_env, "MAV_MODEL_MAX_TOKENS", provider_env]
    if provider == "anthropic":
        env_vars.append("MAV_ANTHROPIC_MAX_TOKENS")
    for env_var in env_vars:
        if os.getenv(env_var):
            return _positive_int(os.environ[env_var], env_var)

    config = configured_models().get(task, {})
    if config.get("max_tokens"):
        return _positive_int(config["max_tokens"], f"max_tokens for {task}")
    return max(requested or 0, DEFAULT_MODEL_MAX_TOKENS)


def model_config_for_task(task: str, *, requested_max_tokens: int | None = None) -> ResolvedModelConfig:
    provider = _provider_for_task(task)
    return ResolvedModelConfig(
        task=task,
        provider=provider,
        model=_model_for_task(task, provider),
        max_tokens=_max_tokens_for_task(task, provider, requested_max_tokens),
    )


def model_timeout_seconds(resolved: ResolvedModelConfig) -> int:
    task_env = f"MAV_{resolved.task.upper()}_TIMEOUT_SECONDS"
    provider_env = f"MAV_{resolved.provider.upper()}_TIMEOUT_SECONDS"
    for env_var in (task_env, "MAV_MODEL_TIMEOUT_SECONDS", provider_env):
        if os.getenv(env_var):
            return _positive_int(os.environ[env_var], env_var)
    configured = configured_models().get(resolved.task, {}).get("timeout_seconds")
    if configured:
        return _positive_int(configured, f"timeout_seconds for {resolved.task}")
    return DEFAULT_MODEL_TIMEOUT_SECONDS


def _api_key_for_provider(provider: str) -> str | None:
    load_env()
    if provider == "anthropic":
        return os.getenv("ANTHROPIC_API_KEY")
    if provider == "gemini":
        return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if provider == "zai":
        return os.getenv("ZAI_API_KEY") or os.getenv("ZHIPU_API_KEY") or os.getenv("BIGMODEL_API_KEY")
    if provider == "moonshot":
        return os.getenv("MOONSHOT_API_KEY")
    raise RuntimeError(f"Unsupported model provider {provider!r}")


def _api_key_hint(provider: str) -> str:
    if provider == "anthropic":
        return "ANTHROPIC_API_KEY"
    if provider == "gemini":
        return "GEMINI_API_KEY or GOOGLE_API_KEY"
    if provider == "zai":
        return "ZAI_API_KEY, ZHIPU_API_KEY, or BIGMODEL_API_KEY"
    if provider == "moonshot":
        return "MOONSHOT_API_KEY"
    return "provider API key"


def provider_available(provider: str) -> bool:
    return bool(_api_key_for_provider(_normalize_provider(provider)))


def anthropic_available() -> bool:
    return provider_available("anthropic")


def gemini_available() -> bool:
    return provider_available("gemini")


def zai_available() -> bool:
    return provider_available("zai")


def _extract_json(text: str, task: str, provider: str, output_schema: dict[str, Any] | None) -> dict[str, Any]:
    text = text.strip()
    if not text:
        raise RuntimeError(f"{provider.title()} {task} call returned no text")

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        if output_schema is not None:
            raise RuntimeError(f"{provider.title()} {task} structured output was not valid JSON") from None
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def call_model_json(
    *,
    task: str,
    system: str,
    user: str,
    max_tokens: int | None = None,
    output_schema: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Call the configured provider for one structured JSON object."""
    resolved = model_config_for_task(task, requested_max_tokens=max_tokens)
    if not provider_available(resolved.provider):
        raise RuntimeError(
            f"{resolved.provider.title()} provider selected for {task}, but {_api_key_hint(resolved.provider)} is not set"
        )
    if resolved.provider == "anthropic":
        return _call_anthropic_json(resolved, system=system, user=user, output_schema=output_schema)
    if resolved.provider == "gemini":
        return _call_gemini_json(resolved, system=system, user=user, output_schema=output_schema)
    if resolved.provider == "zai":
        return _call_zai_json(resolved, system=system, user=user, output_schema=output_schema)
    if resolved.provider == "moonshot":
        return _call_moonshot_json(resolved, system=system, user=user)
    raise RuntimeError(f"Unsupported model provider {resolved.provider!r}")


def call_model_text(
    *,
    task: str,
    system: str,
    user: str,
    max_tokens: int | None = None,
) -> str | None:
    """Call the configured provider and return raw text instead of JSON."""
    resolved = model_config_for_task(task, requested_max_tokens=max_tokens)
    if not provider_available(resolved.provider):
        raise RuntimeError(
            f"{resolved.provider.title()} provider selected for {task}, but {_api_key_hint(resolved.provider)} is not set"
        )
    if resolved.provider == "anthropic":
        return _call_anthropic_text(resolved, system=system, user=user)
    if resolved.provider == "gemini":
        return _call_gemini_text(resolved, system=system, user=user)
    if resolved.provider == "zai":
        return _call_zai_text(resolved, system=system, user=user)
    if resolved.provider == "moonshot":
        return _call_moonshot_text(resolved, system=system, user=user)
    raise RuntimeError(f"Unsupported model provider {resolved.provider!r}")


def call_anthropic_json(
    *,
    task: str,
    system: str,
    user: str,
    max_tokens: int | None = None,
    output_schema: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Backward-compatible wrapper for older imports."""
    if not anthropic_available():
        return None
    resolved = ResolvedModelConfig(
        task=task,
        provider="anthropic",
        model=_model_for_task(task, "anthropic"),
        max_tokens=_max_tokens_for_task(task, "anthropic", max_tokens),
    )
    return _call_anthropic_json(resolved, system=system, user=user, output_schema=output_schema)


def _call_anthropic_json(
    resolved: ResolvedModelConfig,
    *,
    system: str,
    user: str,
    output_schema: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = {
        "model": resolved.model,
        "max_tokens": resolved.max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    if output_schema is not None:
        payload["output_config"] = {
            "format": {
                "type": "json_schema",
                "schema": output_schema,
            }
        }
    request = urllib.request.Request(
        os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/") + "/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        },
        method="POST",
    )
    timeout_seconds = model_timeout_seconds(resolved)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Anthropic {resolved.task} call failed with HTTP {exc.code}: {detail}") from exc
    except TimeoutError as exc:
        raise RuntimeError(f"Anthropic {resolved.task} call timed out after {timeout_seconds} seconds") from exc

    stop_reason = data.get("stop_reason")
    if stop_reason in {"max_tokens", "refusal"}:
        raise RuntimeError(
            f"Anthropic {resolved.task} call stopped with {stop_reason}; "
            "refusing to use incomplete/non-schema output"
        )

    record_model_usage(
        task=resolved.task,
        provider=resolved.provider,
        model=resolved.model,
        usage=data.get("usage") or {},
        response_id=data.get("id"),
    )
    text = "\n".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")
    return _extract_json(text, resolved.task, "anthropic", output_schema)


def _call_anthropic_text(
    resolved: ResolvedModelConfig,
    *,
    system: str,
    user: str,
) -> str:
    payload = {
        "model": resolved.model,
        "max_tokens": resolved.max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    request = urllib.request.Request(
        os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/") + "/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
        },
        method="POST",
    )
    timeout_seconds = model_timeout_seconds(resolved)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Anthropic {resolved.task} call failed with HTTP {exc.code}: {detail}") from exc
    except TimeoutError as exc:
        raise RuntimeError(f"Anthropic {resolved.task} call timed out after {timeout_seconds} seconds") from exc

    stop_reason = data.get("stop_reason")
    if stop_reason in {"max_tokens", "refusal"}:
        raise RuntimeError(f"Anthropic {resolved.task} call stopped with {stop_reason}")

    record_model_usage(
        task=resolved.task,
        provider=resolved.provider,
        model=resolved.model,
        usage=data.get("usage") or {},
        response_id=data.get("id"),
    )
    return "\n".join(block.get("text", "") for block in data.get("content", []) if block.get("type") == "text")


def _zai_reasoning_effort(resolved: ResolvedModelConfig) -> str:
    task_env = f"MAV_{resolved.task.upper()}_REASONING_EFFORT"
    env_value = os.getenv(task_env) or os.getenv("MAV_ZAI_REASONING_EFFORT")
    if env_value:
        return env_value.strip().lower()

    config = configured_models().get(resolved.task, {})
    configured = str(config.get("reasoning_effort") or config.get("effort") or "high").strip().lower()
    return {"xhigh": "max", "medium": "high", "low": "high"}.get(configured, configured)


def _zai_payload(
    resolved: ResolvedModelConfig,
    *,
    system: str,
    user: str,
    json_mode: bool,
) -> dict[str, Any]:
    reasoning_effort = _zai_reasoning_effort(resolved)
    payload: dict[str, Any] = {
        "model": resolved.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "max_tokens": resolved.max_tokens,
        "temperature": float(os.getenv("MAV_ZAI_TEMPERATURE", "1.0")),
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if reasoning_effort in {"none", "minimal"}:
        payload["thinking"] = {"type": "disabled"}
        payload["reasoning_effort"] = reasoning_effort
    else:
        payload["thinking"] = {"type": os.getenv("MAV_ZAI_THINKING", "enabled")}
        payload["reasoning_effort"] = reasoning_effort
    return payload


def _zai_response_text(data: dict[str, Any], task: str) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"Z.AI {task} call returned no choices")

    finish_reason = choices[0].get("finish_reason")
    if finish_reason in {"length", "sensitive", "model_context_window_exceeded", "network_error"}:
        raise RuntimeError(f"Z.AI {task} call stopped with {finish_reason}")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    return ""


def _log_zai_usage(task: str, data: dict[str, Any]) -> None:
    usage = data.get("usage") or {}
    if not usage:
        return
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    cached_tokens = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
    if prompt_tokens is None and completion_tokens is None and cached_tokens is None:
        return
    print(
        f"Z.AI {task} usage: prompt={prompt_tokens or 0} "
        f"cached={cached_tokens or 0} completion={completion_tokens or 0}",
        file=sys.stderr,
        flush=True,
    )


def _zai_chat_completions_url() -> str:
    explicit = os.getenv("ZAI_CHAT_COMPLETIONS_URL")
    if explicit:
        return explicit
    base = os.getenv("ZAI_BASE_URL")
    if not base:
        return ZAI_CHAT_COMPLETIONS_URL
    base = base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/api/paas/v4/chat/completions"


def _call_zai(
    resolved: ResolvedModelConfig,
    *,
    system: str,
    user: str,
    json_mode: bool,
) -> dict[str, Any]:
    request = urllib.request.Request(
        _zai_chat_completions_url(),
        data=json.dumps(_zai_payload(resolved, system=system, user=user, json_mode=json_mode)).encode("utf-8"),
        headers={
            "accept-language": "en-US,en",
            "authorization": f"Bearer {_api_key_for_provider('zai')}",
            "content-type": "application/json",
        },
        method="POST",
    )
    timeout_seconds = model_timeout_seconds(resolved)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Z.AI {resolved.task} call failed with HTTP {exc.code}: {detail}") from exc
    except TimeoutError as exc:
        raise RuntimeError(f"Z.AI {resolved.task} call timed out after {timeout_seconds} seconds") from exc
    _log_zai_usage(resolved.task, data)
    record_model_usage(
        task=resolved.task,
        provider=resolved.provider,
        model=resolved.model,
        usage=data.get("usage") or {},
        response_id=data.get("id"),
    )
    return data


def _call_zai_json(
    resolved: ResolvedModelConfig,
    *,
    system: str,
    user: str,
    output_schema: dict[str, Any] | None,
) -> dict[str, Any]:
    data = _call_zai(resolved, system=system, user=user, json_mode=True)
    return _extract_json(_zai_response_text(data, resolved.task), resolved.task, "zai", output_schema)


def _call_zai_text(
    resolved: ResolvedModelConfig,
    *,
    system: str,
    user: str,
) -> str:
    data = _call_zai(resolved, system=system, user=user, json_mode=False)
    return _zai_response_text(data, resolved.task)


def _call_moonshot(
    resolved: ResolvedModelConfig,
    *,
    system: str,
    user: str,
    json_mode: bool,
) -> dict[str, Any]:
    """Call Moonshot AI (Kimi K2) via their OpenAI-compatible REST API."""
    payload: dict[str, Any] = {
        "model": resolved.model,
        "max_tokens": resolved.max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if not resolved.model.strip().lower().startswith(("kimi-k2.6", "kimi-k2.7")):
        payload["temperature"] = 0.2
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    request = urllib.request.Request(
        MOONSHOT_CHAT_COMPLETIONS_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {_api_key_for_provider('moonshot')}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    timeout_seconds = model_timeout_seconds(resolved)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Moonshot {resolved.task} call failed with HTTP {exc.code}: {detail}") from exc
    except TimeoutError as exc:
        raise RuntimeError(f"Moonshot {resolved.task} call timed out after {timeout_seconds} seconds") from exc
    usage = data.get("usage", {})
    print(
        f"Moonshot {resolved.task} usage: prompt={usage.get('prompt_tokens', '?')} "
        f"completion={usage.get('completion_tokens', '?')}",
        file=sys.stderr,
        flush=True,
    )
    record_model_usage(
        task=resolved.task,
        provider=resolved.provider,
        model=resolved.model,
        usage=usage,
        response_id=data.get("id"),
    )
    return data


def _call_moonshot_text(
    resolved: ResolvedModelConfig,
    *,
    system: str,
    user: str,
) -> str:
    data = _call_moonshot(resolved, system=system, user=user, json_mode=False)
    return _moonshot_response_text(data, resolved.task)


def _call_moonshot_json(
    resolved: ResolvedModelConfig,
    *,
    system: str,
    user: str,
) -> dict[str, Any]:
    data = _call_moonshot(resolved, system=system, user=user, json_mode=True)
    text = _moonshot_response_text(data, resolved.task)
    return _extract_json(text, resolved.task, "moonshot", None)


def _moonshot_response_text(data: dict[str, Any], task: str) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"Moonshot {task} call returned no choices")
    finish_reason = choices[0].get("finish_reason")
    if finish_reason not in {None, "stop"}:
        raise RuntimeError(f"Moonshot {task} call stopped with {finish_reason}; refusing incomplete output")
    text = str((choices[0].get("message") or {}).get("content") or "").strip()
    if not text:
        raise RuntimeError(f"Moonshot {task} call returned no text")
    return text


def _gemini_response_text(response: Any) -> str:
    text = (getattr(response, "text", None) or "").strip()
    if text:
        return text

    parts: list[str] = []
    for candidate in getattr(response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            part_text = getattr(part, "text", None)
            if part_text:
                parts.append(part_text)
    return "\n".join(parts).strip()


def _gemini_finish_reasons(response: Any) -> list[str]:
    reasons = []
    for candidate in getattr(response, "candidates", []) or []:
        reason = getattr(candidate, "finish_reason", None)
        if reason is not None:
            reasons.append(str(reason))
    return reasons


def _gemini_usage(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage_metadata", None) or getattr(response, "usageMetadata", None)
    if usage is None:
        return {}
    payload: dict[str, Any] = {}
    for source, target in (
        ("prompt_token_count", "prompt_token_count"),
        ("candidates_token_count", "candidates_token_count"),
        ("total_token_count", "total_token_count"),
        ("cached_content_token_count", "cached_content_token_count"),
    ):
        value = getattr(usage, source, None)
        if value is not None:
            payload[target] = value
    if isinstance(usage, dict):
        payload.update(usage)
    return payload


def _gemini_compatible_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Return the documented Gemini JSON-Schema subset at safe complexity.

    The animation registry is also our authoritative local validator, so large
    classification enums and unsupported presentation constraints can be
    removed from the provider schema without weakening the pipeline boundary.
    """

    def clean(node: Any) -> Any:
        if isinstance(node, list):
            return [clean(item) for item in node]
        if not isinstance(node, dict):
            return node

        compatible: dict[str, Any] = {}
        for key, value in node.items():
            if key not in GEMINI_JSON_SCHEMA_KEYS:
                continue
            if key in {"properties", "$defs"} and isinstance(value, dict):
                compatible[key] = {name: clean(child) for name, child in value.items()}
                continue
            if key == "enum" and isinstance(value, list) and len(value) > GEMINI_MAX_SCHEMA_ENUM_VALUES:
                continue
            compatible[key] = clean(value)
        return compatible

    return clean(schema)


def _is_gemini_invalid_argument(exc: Exception) -> bool:
    message = str(exc).upper()
    return "INVALID_ARGUMENT" in message or "INVALID ARGUMENT" in message


def _call_gemini_json(
    resolved: ResolvedModelConfig,
    *,
    system: str,
    user: str,
    output_schema: dict[str, Any] | None,
) -> dict[str, Any]:
    from google import genai
    from google.genai import types

    http_options = types.HttpOptions(timeout=model_timeout_seconds(resolved) * 1000)
    config_payload: dict[str, Any] = {
        "system_instruction": system,
        "response_mime_type": "application/json",
        "max_output_tokens": resolved.max_tokens,
        "http_options": http_options,
    }
    if output_schema is not None:
        config_payload["response_json_schema"] = _gemini_compatible_json_schema(output_schema)

    client = genai.Client(api_key=_api_key_for_provider("gemini"), http_options=http_options)
    try:
        response = client.models.generate_content(
            model=resolved.model,
            contents=user,
            config=types.GenerateContentConfig(**config_payload),
        )
    except Exception as exc:
        if output_schema is None or not _is_gemini_invalid_argument(exc):
            raise RuntimeError(f"Gemini {resolved.task} call failed: {exc}") from exc

        # Some model revisions impose a lower undocumented schema-complexity
        # ceiling. JSON MIME mode still guarantees a JSON response, after which
        # the task-specific local validator enforces the authoritative schema.
        print(
            f"MAV model warning: Gemini rejected the {resolved.task} response schema; "
            "retrying once in JSON mode with strict local validation.",
            file=sys.stderr,
            flush=True,
        )
        fallback_payload = dict(config_payload)
        fallback_payload.pop("response_json_schema", None)
        try:
            response = client.models.generate_content(
                model=resolved.model,
                contents=user,
                config=types.GenerateContentConfig(**fallback_payload),
            )
        except Exception as fallback_exc:
            raise RuntimeError(
                f"Gemini {resolved.task} call failed after response-schema fallback: {fallback_exc}"
            ) from fallback_exc

    finish_reasons = _gemini_finish_reasons(response)
    joined_reasons = ",".join(finish_reasons).upper()
    if "MAX_TOKENS" in joined_reasons:
        raise RuntimeError(
            f"Gemini {resolved.task} call stopped with max_tokens; "
            "refusing to use incomplete/non-schema output"
        )
    if any(reason in joined_reasons for reason in ("SAFETY", "RECITATION", "PROHIBITED")):
        raise RuntimeError(f"Gemini {resolved.task} call stopped with {finish_reasons}")

    record_model_usage(
        task=resolved.task,
        provider=resolved.provider,
        model=resolved.model,
        usage=_gemini_usage(response),
        response_id=None,
    )
    return _extract_json(_gemini_response_text(response), resolved.task, "gemini", output_schema)


def _call_gemini_text(
    resolved: ResolvedModelConfig,
    *,
    system: str,
    user: str,
) -> str:
    from google import genai
    from google.genai import types

    http_options = types.HttpOptions(timeout=model_timeout_seconds(resolved) * 1000)
    config_payload: dict[str, Any] = {
        "system_instruction": system,
        "max_output_tokens": resolved.max_tokens,
        "http_options": http_options,
    }

    client = genai.Client(api_key=_api_key_for_provider("gemini"), http_options=http_options)
    try:
        response = client.models.generate_content(
            model=resolved.model,
            contents=user,
            config=types.GenerateContentConfig(**config_payload),
        )
    except Exception as exc:
        raise RuntimeError(f"Gemini {resolved.task} call failed: {exc}") from exc

    finish_reasons = _gemini_finish_reasons(response)
    joined_reasons = ",".join(finish_reasons).upper()
    if "MAX_TOKENS" in joined_reasons:
        raise RuntimeError(f"Gemini {resolved.task} call stopped with max_tokens")
    if any(reason in joined_reasons for reason in ("SAFETY", "RECITATION", "PROHIBITED")):
        raise RuntimeError(f"Gemini {resolved.task} call stopped with {finish_reasons}")

    record_model_usage(
        task=resolved.task,
        provider=resolved.provider,
        model=resolved.model,
        usage=_gemini_usage(response),
        response_id=None,
    )
    return _gemini_response_text(response)
