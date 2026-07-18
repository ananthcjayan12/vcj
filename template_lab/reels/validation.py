from __future__ import annotations

import shutil
from pathlib import Path


def assert_reel_source_isolation(prompt: str, parent_run_path: Path) -> None:
    forbidden = [parent_run_path / "motion_canvas", parent_run_path / "preview", parent_run_path / "compositions"]
    for path in forbidden:
        if str(path) in prompt:
            raise RuntimeError("Parent visual artifact path leaked into Reel creative input")
    if "parent TSX" in prompt or "motion_canvas/manifest.json" in prompt:
        raise RuntimeError("Parent visual artifacts leaked into Reel creative input")


def validate_portrait_tsx(source: str, shot_id: str) -> None:
    if "../../reel-presentation" not in source:
        raise RuntimeError(f"{shot_id} must import the portrait Reel presentation library")
    if "../../presentation" in source.replace("../../reel-presentation", ""):
        raise RuntimeError(f"{shot_id} must not import the landscape presentation library")


def invalidate(run_path: Path, stage: str, *, shot_id: str | None = None) -> None:
    order = {"narration": 1, "audio": 2, "shot_plan": 3, "shot_tsx": 4}
    if stage not in order:
        raise ValueError(f"Unknown Reel invalidation stage: {stage}")
    targets: list[Path] = []
    if order[stage] <= 1:
        targets += [run_path / name for name in ("voiceover.mp3", "voiceover.wav", "audio_generation.json", "audio_timing.json", "audio_word_timestamps.json", "audio_chunks")]
    if order[stage] <= 2:
        targets += [run_path / "audio_timing.json", run_path / "audio_word_timestamps.json", run_path / "motion_canvas" / "timeline.json", run_path / "reel_timeline.json", run_path / "reel_shot_plan.json"]
    if order[stage] <= 3:
        targets += [run_path / "motion_canvas" / name for name in ("shots", "generation-report.json")]
    if order[stage] <= 4:
        if shot_id:
            targets += [run_path / "motion_canvas" / "shots" / f"{shot_id}.tsx"]
        targets += [run_path / "motion_canvas" / name for name in ("scenes.ts", "preview", "frames", "render-checkpoint.json", "final.mp4", "validation.json", "robot-report.json")]
    for target in targets:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink(missing_ok=True)
