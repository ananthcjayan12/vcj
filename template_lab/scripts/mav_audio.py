from __future__ import annotations

import base64
import array
import hashlib
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import wave
import math
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
DEFAULT_REEL_GEMINI_TTS_PROMPT_PREFIX = (
    "Perform the following vertical educational Reel voiceover exactly as written. Use a youthful, premium, "
    "high-energy presenter voice: aggressive forward momentum, fast and enthusiastic, crisp consonants, confident "
    "curiosity, and strong payoff emphasis. Aim around 175 to 195 spoken words per minute. Keep micro-pauses short. "
    "Never sound slow, sleepy, theatrical, robotic, or like a patient classroom lecture. Scientific terms must remain "
    "precise. Do not add, remove, or rewrite words. Interpret bracketed performance directions naturally without "
    "speaking the brackets.\n\n"
)
GEMINI_TTS_SAMPLE_RATE = 24000
GEMINI_TTS_CHANNELS = 1
GEMINI_TTS_SAMPLE_WIDTH = 2
DEFAULT_CHAPTER_PAUSE_SECONDS = 0.35


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


def _audio_provider_config(provider: str, *, content_format: str = "lesson") -> AudioProviderConfig:
    load_env()
    if provider == ELEVENLABS_AUDIO_PROVIDER:
        return AudioProviderConfig(
            provider=provider,
            voice_id=os.getenv("ELEVENLABS_REEL_VOICE_ID" if content_format == "reel" else "ELEVENLABS_VOICE_ID", os.getenv("ELEVENLABS_VOICE_ID", "")),
            model_id=os.getenv("ELEVENLABS_MODEL_ID", "eleven_v3"),
            output_format=os.getenv("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128"),
        )
    if provider == GEMINI_AUDIO_PROVIDER:
        return AudioProviderConfig(
            provider=provider,
            voice_id=os.getenv("MAV_REEL_TTS_VOICE", "Puck") if content_format == "reel" else os.getenv("GEMINI_TTS_VOICE", DEFAULT_GEMINI_TTS_VOICE),
            model_id=os.getenv("GEMINI_TTS_MODEL", DEFAULT_GEMINI_TTS_MODEL),
            output_format="mp3_from_wav_24000",
            prompt_prefix=(os.getenv("MAV_REEL_TTS_PROMPT_PREFIX", DEFAULT_REEL_GEMINI_TTS_PROMPT_PREFIX)
                           if content_format == "reel" else os.getenv("GEMINI_TTS_PROMPT_PREFIX", DEFAULT_GEMINI_TTS_PROMPT_PREFIX)),
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


def _call_elevenlabs_with_timestamps(text: str, *, content_format: str = "lesson") -> dict[str, Any]:
    load_env()
    api_key = os.getenv("ELEVENLABS_API_KEY") or os.getenv("XI_API_KEY")
    voice_id = os.getenv("ELEVENLABS_REEL_VOICE_ID" if content_format == "reel" else "ELEVENLABS_VOICE_ID") or os.getenv("ELEVENLABS_VOICE_ID")
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
            "stability": float(os.getenv("ELEVENLABS_REEL_STABILITY", "0.28") if content_format == "reel" else os.getenv("ELEVENLABS_STABILITY", "0.5")),
            "similarity_boost": float(os.getenv("ELEVENLABS_SIMILARITY_BOOST", "0.75")),
            **({"style": float(os.getenv("ELEVENLABS_REEL_STYLE", "0.7")), "use_speaker_boost": True} if content_format == "reel" else {}),
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


def _convert_audio_to_wav(source_path: Path, target_path: Path) -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required to normalize chapter audio")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(source_path), "-ar", str(GEMINI_TTS_SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(target_path)],
        check=True, capture_output=True, text=True,
    )


def _write_silence(path: Path, seconds: float) -> None:
    frames = max(0, round(seconds * GEMINI_TTS_SAMPLE_RATE))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(GEMINI_TTS_CHANNELS)
        handle.setsampwidth(GEMINI_TTS_SAMPLE_WIDTH)
        handle.setframerate(GEMINI_TTS_SAMPLE_RATE)
        handle.writeframes(b"\0" * frames * GEMINI_TTS_SAMPLE_WIDTH)


def _assemble_wav(parts: list[Path], target: Path) -> None:
    with wave.open(str(target), "wb") as output:
        output.setnchannels(GEMINI_TTS_CHANNELS)
        output.setsampwidth(GEMINI_TTS_SAMPLE_WIDTH)
        output.setframerate(GEMINI_TTS_SAMPLE_RATE)
        for part in parts:
            with wave.open(str(part), "rb") as source:
                if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (
                    GEMINI_TTS_CHANNELS, GEMINI_TTS_SAMPLE_WIDTH, GEMINI_TTS_SAMPLE_RATE
                ):
                    raise RuntimeError(f"Chapter audio format mismatch: {part}")
                output.writeframes(source.readframes(source.getnframes()))


def _chapter_quality(path: Path) -> dict[str, Any]:
    with wave.open(str(path), "rb") as audio:
        frames = audio.readframes(audio.getnframes())
        duration = audio.getnframes() / audio.getframerate()
    samples = array.array("h")
    samples.frombytes(frames)
    if not samples:
        raise RuntimeError(f"Chapter audio contains no samples: {path}")
    peak = max(abs(value) for value in samples)
    rms = math.sqrt(sum(value * value for value in samples) / len(samples))
    rms_dbfs = 20 * math.log10(max(rms, 1) / 32768)
    clipping_ratio = sum(abs(value) >= 32760 for value in samples) / len(samples)
    status = "passed" if duration >= .2 and rms_dbfs > -50 and clipping_ratio < .01 else "failed"
    report = {"status": status, "duration": round(duration, 3), "peak": peak, "rms_dbfs": round(rms_dbfs, 2), "clipping_ratio": round(clipping_ratio, 6)}
    if status != "passed":
        raise RuntimeError(f"Chapter audio quality gate failed for {path.name}: {report}")
    return report


def _chapter_texts(narration: dict[str, Any]) -> list[tuple[str, str]]:
    chapters = []
    for index, paragraph in enumerate(narration.get("paragraphs") or []):
        chapter_id = str(paragraph.get("id") or f"paragraph_{index + 1:02d}")
        text = normalize_text(str(paragraph.get("text") or ""))
        if not text:
            raise RuntimeError(f"{chapter_id} has no spoken narration")
        chapters.append((chapter_id, text))
    if not chapters:
        raise RuntimeError("Narration contains no chapters")
    return chapters


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
    content_format: str = "lesson",
) -> dict[str, Any]:
    run_path.mkdir(parents=True, exist_ok=True)
    chunks_dir = run_path / "audio_chunks"
    chunks_dir.mkdir(exist_ok=True)
    text = narration["elevenlabs_narration"]
    chapter_texts = _chapter_texts(narration)
    provider = resolve_audio_provider(
        audio_provider=audio_provider,
        use_elevenlabs=use_elevenlabs,
        use_gemini_tts=use_gemini_tts,
    )
    config = _audio_provider_config(provider, content_format=content_format)
    key = _cache_key(text, config)
    audio_path = run_path / "voiceover.mp3"
    gemini_wav_path = run_path / "voiceover.wav"
    alignment_path = run_path / "audio_alignment.json"
    duration = estimate_audio_duration(narration, target_duration)
    reused = False
    pause_seconds = max(0.0, min(float(os.getenv("MAV_CHAPTER_PAUSE_SECONDS", str(DEFAULT_CHAPTER_PAUSE_SECONDS))), 2.0))
    chapter_records: list[dict[str, Any]] = []
    assembly_parts: list[Path] = []
    absolute_time = 0.0
    all_reused = True
    for index, (chapter_id, chapter_text) in enumerate(chapter_texts):
        chapter_dir = chunks_dir / chapter_id
        chapter_dir.mkdir(parents=True, exist_ok=True)
        chapter_key = _cache_key(chapter_text, config)
        key_path = chapter_dir / "cache_key.txt"
        wav_path = chapter_dir / "audio.wav"
        source_path = chapter_dir / "source_audio"
        chapter_reused = wav_path.exists() and key_path.exists() and key_path.read_text(encoding="utf-8") == chapter_key
        alignment_payload = None
        if not chapter_reused:
            (chapter_dir / "narration.txt").write_text(chapter_text, encoding="utf-8")
            if provider == ELEVENLABS_AUDIO_PROVIDER:
                response = _call_elevenlabs_with_timestamps(chapter_text, content_format=content_format)
                source_path.write_bytes(base64.b64decode(response["audio_base64"]))
                _convert_audio_to_wav(source_path, wav_path)
                alignment_payload = {"alignment": response.get("alignment"), "normalized_alignment": response.get("normalized_alignment")}
                write_json(chapter_dir / "alignment.json", alignment_payload)
            elif provider == GEMINI_AUDIO_PROVIDER:
                pcm = _call_gemini_tts(chapter_text, config)
                _write_wave_file(wav_path, pcm)
            else:
                raise RuntimeError(f"Unsupported audio provider {provider!r}")
            key_path.write_text(chapter_key, encoding="utf-8")
        all_reused = all_reused and chapter_reused
        quality = _chapter_quality(wav_path)
        write_json(chapter_dir / "quality.json", quality)
        if provider != GEMINI_AUDIO_PROVIDER or chapter_reused:
            record_audio_usage(provider=provider, model=config.model_id, voice_id=config.voice_id, text=chapter_text, cache_reused=chapter_reused)
        chapter_duration = ffprobe_duration(wav_path)
        if not chapter_duration or chapter_duration <= 0:
            raise RuntimeError(f"Invalid generated audio for {chapter_id}")
        trailing_pause = pause_seconds if index + 1 < len(chapter_texts) else 0.0
        chapter_records.append({
            "id": chapter_id, "path": str(wav_path.relative_to(run_path)), "text_sha256": hashlib.sha256(chapter_text.encode("utf-8")).hexdigest(),
            "cache_key": chapter_key, "cache_reused": chapter_reused, "quality": quality, "absolute_start": round(absolute_time, 3),
            "speech_duration": round(chapter_duration, 3), "trailing_pause": round(trailing_pause, 3),
            "absolute_end": round(absolute_time + chapter_duration + trailing_pause, 3),
        })
        assembly_parts.append(wav_path)
        if trailing_pause:
            pause_path = chunks_dir / f"pause_{index + 1:02d}.wav"
            _write_silence(pause_path, trailing_pause)
            assembly_parts.append(pause_path)
        absolute_time += chapter_duration + trailing_pause
    _assemble_wav(assembly_parts, gemini_wav_path)
    _convert_audio_to_mp3(gemini_wav_path, audio_path)
    key = hashlib.sha256("".join(item["cache_key"] for item in chapter_records).encode("utf-8")).hexdigest()
    reused = all_reused
    if alignment_path.exists():
        alignment_path.unlink()
    audio_manifest = {
        "version": "2.0", "strategy": "chapter_tts", "content_format": content_format, "provider": provider, "model_id": config.model_id,
        "voice_id": config.voice_id, "sample_rate": GEMINI_TTS_SAMPLE_RATE, "chapters": chapter_records,
        "audio_duration_seconds": round(absolute_time, 3),
        "mp3_container_duration_seconds": round(ffprobe_duration(audio_path) or absolute_time, 3),
    }
    write_json(chunks_dir / "manifest.json", audio_manifest)
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
        "has_alignment": any((chunks_dir / item["id"] / "alignment.json").exists() for item in chapter_records),
        "strategy": "chapter_tts",
        "content_format": content_format,
        "audio_manifest": "audio_chunks/manifest.json",
        "chunks": chapter_records,
    }
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
