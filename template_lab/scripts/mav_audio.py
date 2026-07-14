from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mav_models import load_env
from mav_costs import record_audio_usage, record_model_usage
from mav_schema import normalize_text, spoken_word_count, write_json

ELEVENLABS_AUDIO_PROVIDER = "elevenlabs"
GEMINI_AUDIO_PROVIDER = "gemini"
SUPPORTED_AUDIO_PROVIDERS = {ELEVENLABS_AUDIO_PROVIDER, GEMINI_AUDIO_PROVIDER}
DEFAULT_GEMINI_TTS_MODEL = "gemini-3.1-flash-tts-preview"
DEFAULT_GEMINI_TTS_VOICE = "Kore"
DEFAULT_GEMINI_TTS_PROMPT_PREFIX = (
    "Read the following narration exactly as written. Sound like a warm, patient, precise IGCSE "
    "Physics teacher: curious and engaging, never rushed or theatrical. Pause naturally around "
    "questions, equations, and important conclusions. Do not add, remove, or rewrite words.\n\n"
)
GEMINI_TTS_SAMPLE_RATE = 24000
GEMINI_TTS_CHANNELS = 1
GEMINI_TTS_SAMPLE_WIDTH = 2


@dataclass(frozen=True)
class AudioProviderConfig:
    provider: str
    voice_id: str
    model_id: str
    output_format: str
    prompt_prefix: str = ""
    language_code: str = ""


def resolve_audio_provider(
    *,
    audio_provider: str | None = None,
    use_elevenlabs: bool = False,
    use_gemini_tts: bool = False,
) -> str:
    """Resolve audio flags into one provider string."""
    requested = (audio_provider or "auto").strip().lower()
    aliases = {
        "auto": "auto",
        "eleven": ELEVENLABS_AUDIO_PROVIDER,
        "elevenlabs": ELEVENLABS_AUDIO_PROVIDER,
        "elevenlabs_timed_tts": ELEVENLABS_AUDIO_PROVIDER,
        "gemini": GEMINI_AUDIO_PROVIDER,
        "gemini_tts": GEMINI_AUDIO_PROVIDER,
    }
    if requested not in aliases:
        raise RuntimeError(f"Unsupported audio provider {audio_provider!r}. Use auto, gemini, or elevenlabs.")
    provider = aliases[requested]

    shortcut_providers = [value for value, enabled in ((ELEVENLABS_AUDIO_PROVIDER, use_elevenlabs), (GEMINI_AUDIO_PROVIDER, use_gemini_tts)) if enabled]
    if len(shortcut_providers) > 1:
        raise RuntimeError("Choose only one live audio shortcut: --use-gemini-tts or --use-elevenlabs.")

    if provider == "auto":
        return shortcut_providers[0] if shortcut_providers else GEMINI_AUDIO_PROVIDER
    if shortcut_providers and provider != shortcut_providers[0]:
        shortcut_flag = "--use-gemini-tts" if shortcut_providers[0] == GEMINI_AUDIO_PROVIDER else "--use-elevenlabs"
        raise RuntimeError(f"--audio-provider {provider} conflicts with {shortcut_flag}.")
    return provider


def is_live_audio_provider(provider: str) -> bool:
    return provider in SUPPORTED_AUDIO_PROVIDERS


def _audio_provider_config(provider: str) -> AudioProviderConfig:
    load_env()
    if provider == ELEVENLABS_AUDIO_PROVIDER:
        return AudioProviderConfig(
            provider=provider,
            voice_id=os.getenv("ELEVENLABS_VOICE_ID", ""),
            model_id=os.getenv("ELEVENLABS_MODEL_ID", "eleven_v3"),
            output_format=os.getenv("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128"),
        )
    if provider == GEMINI_AUDIO_PROVIDER:
        return AudioProviderConfig(
            provider=provider,
            voice_id=os.getenv("GEMINI_TTS_VOICE", DEFAULT_GEMINI_TTS_VOICE),
            model_id=os.getenv("GEMINI_TTS_MODEL", DEFAULT_GEMINI_TTS_MODEL),
            output_format="mp3_from_wav_24000",
            prompt_prefix=os.getenv("GEMINI_TTS_PROMPT_PREFIX", DEFAULT_GEMINI_TTS_PROMPT_PREFIX),
            language_code=os.getenv("GEMINI_TTS_LANGUAGE_CODE", ""),
        )
    raise RuntimeError(f"Unsupported audio provider {provider!r}")


def _cache_key(text: str, config: AudioProviderConfig) -> str:
    digest = hashlib.sha256()
    digest.update(config.provider.encode("utf-8"))
    digest.update(normalize_text(text).encode("utf-8"))
    digest.update(config.voice_id.encode("utf-8"))
    digest.update(config.model_id.encode("utf-8"))
    digest.update(config.output_format.encode("utf-8"))
    digest.update(config.prompt_prefix.encode("utf-8"))
    digest.update(config.language_code.encode("utf-8"))
    return digest.hexdigest()


def estimate_audio_duration(narration: dict[str, Any], target: float) -> float:
    words = spoken_word_count(narration.get("elevenlabs_narration", ""))
    estimated = words / 135.0 * 60.0
    return max(target - 3.0, min(target + 3.0, estimated))


def _call_elevenlabs_with_timestamps(text: str) -> dict[str, Any]:
    load_env()
    api_key = os.getenv("ELEVENLABS_API_KEY") or os.getenv("XI_API_KEY")
    voice_id = os.getenv("ELEVENLABS_VOICE_ID")
    if not api_key or not voice_id:
        raise RuntimeError("ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID are required for live audio")
    model_id = os.getenv("ELEVENLABS_MODEL_ID", "eleven_v3")
    output_format = os.getenv("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128")
    params = urllib.parse.urlencode({"output_format": output_format})
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps?{params}"
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": float(os.getenv("ELEVENLABS_STABILITY", "0.5")),
            "similarity_boost": float(os.getenv("ELEVENLABS_SIMILARITY_BOOST", "0.75")),
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "xi-api-key": api_key,
            "accept": "application/json",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ElevenLabs timed TTS failed with HTTP {exc.code}: {detail}") from exc


def _gemini_tts_prompt(text: str, config: AudioProviderConfig) -> str:
    return f"{config.prompt_prefix}{text}"


def _extract_gemini_audio_bytes(response: Any) -> bytes:
    finish_reasons = []
    for candidate in getattr(response, "candidates", []) or []:
        reason = getattr(candidate, "finish_reason", None)
        if reason is not None:
            finish_reasons.append(str(reason))
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            inline_data = getattr(part, "inline_data", None) or getattr(part, "inlineData", None)
            if inline_data is None:
                continue
            data = getattr(inline_data, "data", None)
            if data is None:
                continue
            if isinstance(data, bytes):
                return data
            if isinstance(data, str):
                return base64.b64decode(data)
            return bytes(data)
    raise RuntimeError(f"Gemini TTS returned no inline audio data; finish_reasons={finish_reasons}")


def _gemini_tts_usage(response: Any) -> dict[str, Any]:
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


def _write_wave_file(path: Path, pcm: bytes) -> None:
    if pcm.startswith(b"RIFF"):
        path.write_bytes(pcm)
        return
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(GEMINI_TTS_CHANNELS)
        handle.setsampwidth(GEMINI_TTS_SAMPLE_WIDTH)
        handle.setframerate(GEMINI_TTS_SAMPLE_RATE)
        handle.writeframes(pcm)


def _convert_audio_to_mp3(source_path: Path, target_path: Path) -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required to convert Gemini TTS WAV audio to voiceover.mp3")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source_path),
            "-q:a",
            "4",
            "-acodec",
            "libmp3lame",
            str(target_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _call_gemini_tts(text: str, config: AudioProviderConfig) -> bytes:
    load_env()
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY is required for Gemini TTS")

    from google import genai
    from google.genai import types

    speech_config = types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=config.voice_id),
        ),
        language_code=config.language_code or None,
    )
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=config.model_id,
        contents=_gemini_tts_prompt(text, config),
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=speech_config,
        ),
    )
    audio_bytes = _extract_gemini_audio_bytes(response)
    usage = _gemini_tts_usage(response)
    if usage:
        record_model_usage(
            task="audio_generation",
            provider=GEMINI_AUDIO_PROVIDER,
            model=config.model_id,
            usage=usage,
            response_id=None,
        )
    return audio_bytes


def generate_audio(
    run_path: Path,
    narration: dict[str, Any],
    *,
    target_duration: float,
    use_elevenlabs: bool = False,
    use_gemini_tts: bool = False,
    audio_provider: str | None = None,
) -> dict[str, Any]:
    run_path.mkdir(parents=True, exist_ok=True)
    chunks_dir = run_path / "audio_chunks"
    chunks_dir.mkdir(exist_ok=True)
    text = narration["elevenlabs_narration"]
    provider = resolve_audio_provider(
        audio_provider=audio_provider,
        use_elevenlabs=use_elevenlabs,
        use_gemini_tts=use_gemini_tts,
    )
    config = _audio_provider_config(provider)
    key = _cache_key(text, config)
    audio_path = run_path / "voiceover.mp3"
    gemini_wav_path = run_path / "voiceover.wav"
    alignment_path = run_path / "audio_alignment.json"
    duration = estimate_audio_duration(narration, target_duration)
    reused = False
    sidecar = chunks_dir / "chunk_001.txt"
    alignment_payload = None
    if audio_path.exists() and (chunks_dir / "cache_key.txt").exists() and (chunks_dir / "cache_key.txt").read_text(encoding="utf-8") == key:
        reused = True
        if alignment_path.exists():
            alignment_payload = json.loads(alignment_path.read_text(encoding="utf-8"))
    else:
        sidecar.write_text(text, encoding="utf-8")
        (chunks_dir / "cache_key.txt").write_text(key, encoding="utf-8")
        if provider == ELEVENLABS_AUDIO_PROVIDER:
            response = _call_elevenlabs_with_timestamps(text)
            audio_path.write_bytes(base64.b64decode(response["audio_base64"]))
            alignment_payload = {
                "alignment": response.get("alignment"),
                "normalized_alignment": response.get("normalized_alignment"),
            }
            write_json(run_path / "audio_alignment.json", alignment_payload)
            if gemini_wav_path.exists():
                gemini_wav_path.unlink()
        elif provider == GEMINI_AUDIO_PROVIDER:
            pcm = _call_gemini_tts(text, config)
            _write_wave_file(gemini_wav_path, pcm)
            _convert_audio_to_mp3(gemini_wav_path, audio_path)
            if alignment_path.exists():
                alignment_path.unlink()
        else:
            raise RuntimeError(f"Unsupported audio provider {provider!r}")
    actual_duration = ffprobe_duration(audio_path) or duration
    provider_label = {
        ELEVENLABS_AUDIO_PROVIDER: "elevenlabs_timed_tts",
        GEMINI_AUDIO_PROVIDER: "gemini_tts",
    }[provider]
    report = {
        "provider": provider_label,
        "audio_provider": provider,
        "cache_key": key,
        "cache_reused": reused,
        "voice_id": config.voice_id,
        "model_id": config.model_id,
        "output_format": config.output_format,
        "language_code": config.language_code or None,
        "estimated_duration_seconds": round(duration, 3),
        "audio_duration_seconds": round(actual_duration, 3),
        "has_alignment": bool(alignment_payload),
        "chunks": [{"id": "chunk_001", "path": "audio_chunks/chunk_001.txt", "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}],
    }
    if provider != GEMINI_AUDIO_PROVIDER or reused:
        record_audio_usage(
            provider=provider,
            model=config.model_id,
            voice_id=config.voice_id,
            text=text,
            cache_reused=reused,
        )
    write_json(run_path / "audio_generation.json", report)
    return report


def ffprobe_duration(path: Path) -> float | None:
    if not path.exists() or not shutil.which("ffprobe") or path.stat().st_size == 0:
        return None
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(result.stdout)
    return float(data.get("format", {}).get("duration") or 0)
