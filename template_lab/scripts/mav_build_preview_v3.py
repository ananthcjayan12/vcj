"""V3 preview builder: stitches generated scene HTML into master_v3.html."""
from __future__ import annotations

import html as html_mod
from pathlib import Path
from typing import Any

from mav_schema import dependency_hashes, read_json, sha256_file, sha256_text, write_json
from mav_validate_v3 import normalize_scene_html_for_shell


def _load_plan_with_scene_overrides(run_path: Path) -> dict[str, Any]:
    """Load scene_plan_v3.json and apply editable v3_scenes/*.json overrides."""
    plan = read_json(run_path / "scene_plan_v3.json")
    scene_override_dir = run_path / "v3_scenes"
    if not scene_override_dir.exists():
        return plan

    merged_scenes = []
    for scene in plan.get("scenes", []):
        scene_id = scene.get("id")
        override_path = scene_override_dir / f"{scene_id}.json"
        if scene_id and override_path.exists():
            override = read_json(override_path)
            for key in ("id", "paragraph_id", "start", "duration", "beat_label", "narration_text"):
                override.setdefault(key, scene.get(key))
            merged_scenes.append(override)
        else:
            merged_scenes.append(scene)
    plan["scenes"] = merged_scenes
    plan["scene_count"] = len(merged_scenes)
    return plan


def _scene_source_hashes(run_path: Path, scenes: list[dict[str, Any]]) -> dict[str, str]:
    hashes = {"scene_plan": sha256_file(run_path / "scene_plan_v3.json")}
    scene_override_dir = run_path / "v3_scenes"
    for scene in scenes:
        scene_id = scene.get("id")
        scene_path = scene_override_dir / f"{scene_id}.json"
        if scene_id and scene_path.exists():
            hashes[f"v3_scenes/{scene_id}.json"] = sha256_file(scene_path)
    return hashes


def _scene_section(scene: dict[str, Any]) -> str:
    """Wrap a scene's HTML in the standard section container."""
    sid = html_mod.escape(scene["id"])
    start = float(scene["start"])
    duration = float(scene["duration"])
    scene_html, _ = normalize_scene_html_for_shell(scene["scene_html"], scene["id"])

    return f"""
      <section class="mav-scene mav-v3-scene" data-scene-id="{sid}" data-start="{start}" data-duration="{duration}" style="--scene-start:{start}s;--scene-duration:{duration}s">
        <div class="paper-bg"></div>
        <div class="camera">
          <div class="v3-scene-content">
            {scene_html}
          </div>
        </div>
        <div class="grain"></div>
        <div class="vignette"></div>
      </section>
    """


def _gsap_init_calls(scenes: list[dict[str, Any]]) -> str:
    """Generate JavaScript that registers each scene's initScene function."""
    blocks = []
    for scene in scenes:
        sid = html_mod.escape(scene["id"])
        gsap_code = scene.get("scene_gsap", "")
        if not gsap_code:
            continue
        blocks.append(
            f"""
      // === {sid} ===
      (function() {{
        {gsap_code}
        initScene(tl, {float(scene['start'])}, {float(scene['duration'])});
      }})();
"""
        )
    return "\n".join(blocks)


def _master_html(
    *,
    title: str,
    body: str,
    gsap_inits: str,
    project_prefix: str,
    duration: float,
    audio_src: str | None,
    timeline_id: str = "mav_master_v3",
    initial_time: float | None = None,
    show_controls: bool | None = None,
) -> str:
    audio = f'<audio id="mav-audio" src="{html_mod.escape(audio_src)}" preload="auto"></audio>' if audio_src else ""
    controls = ""
    should_show_controls = bool(audio_src) if show_controls is None else show_controls
    if should_show_controls:
        mute_button = '<button type="button" id="mav-mute">Mute</button>' if audio_src else ""
        controls = f"""
        <div class="mav-controls" data-html2canvas-ignore="true">
          <button type="button" id="mav-play">Play</button>
          <button type="button" id="mav-pause">Pause</button>
          <button type="button" id="mav-restart">Restart</button>
          <input id="mav-seek" type="range" min="0" max="{duration}" step="0.01" value="0">
          <span id="mav-time">0.00s</span>
          {mute_button}
        </div>
        """

    return f"""<!doctype html>
<html data-composition-id="{html_mod.escape(timeline_id)}" data-width="1920" data-height="1080" data-duration="{duration}">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{html_mod.escape(title)} — MAV V3</title>
    <link rel="icon" href="data:,">
    <link rel="stylesheet" href="{project_prefix}/css/tokens.css">
    <link rel="stylesheet" href="{project_prefix}/css/common.css">
    <link rel="stylesheet" href="{project_prefix}/css/v3_base.css">
    <style>
      body {{ margin:0; background:#28251f; overflow:hidden; }}
      .mav-scene {{ position:absolute; inset:0; overflow:hidden; opacity:0; background:var(--paper); }}
      .mav-scene:first-of-type {{ opacity:1; }}
      .mav-flash {{ position:absolute; inset:0; background:var(--yellow); opacity:0; z-index:40; }}
      .mav-controls {{ position:fixed; left:50%; bottom:18px; z-index:9999; transform:translateX(-50%); display:flex; align-items:center; gap:10px; width:min(980px, calc(100vw - 32px)); padding:10px 12px; background:rgba(23,23,20,.88); color:#f6f0df; border:1px solid rgba(246,240,223,.18); border-radius:6px; box-shadow:0 12px 32px rgba(0,0,0,.24); font:14px/1 var(--sans); }}
      .mav-controls button {{ border:1px solid rgba(246,240,223,.25); border-radius:5px; background:#f2efe4; color:#171714; padding:8px 10px; font:700 13px/1 var(--sans); cursor:pointer; }}
      .mav-controls input {{ flex:1 1 auto; min-width:160px; }}
      .mav-controls span {{ min-width:64px; text-align:right; }}
      body.mav-render-mode .mav-controls {{ display:none; }}
      .camera {{ position:absolute; inset:0; transform-origin:center center; }}
      .v3-scene-content {{ position:absolute; inset:0; overflow:hidden; }}
    </style>
  </head>
  <body class="composition-body">
    <div class="composition-root" data-composition-id="{html_mod.escape(timeline_id)}" data-width="1920" data-height="1080" data-duration="{duration}" data-scene-id="master">
      <div class="stage">
        {body}
        <div class="mav-flash"></div>
        <div class="debug-layer"><div class="safe-area"></div><div class="center-line-x"></div><div class="center-line-y"></div><div class="debug-readout"></div></div>
      </div>
      {audio}
    </div>
    {controls}
    <script src="{project_prefix}/vendor/gsap.min.js"></script>
    <script type="module">
      import {{ scaleToViewport, registerTimeline }} from "{project_prefix}/js/composition_runtime.js";
      const root = document.querySelector(".composition-root");
      if (window.__hf || new URLSearchParams(location.search).get("render") === "1") {{
        document.body.classList.add("mav-render-mode");
      }}
      scaleToViewport(root);
      const tl = gsap.timeline({{ paused: true }});
      const scenes = Array.from(document.querySelectorAll(".mav-scene"));

      function resetPlaybackState() {{
        gsap.set(scenes, {{ opacity: 0 }});
        if (scenes[0]) gsap.set(scenes[0], {{ opacity: 1 }});
        gsap.set(".mav-flash", {{ opacity: 0 }});
      }}

      scenes.forEach((scene, index) => {{
        const start = Number(scene.dataset.start || 0);
        const dur = Number(scene.dataset.duration || 5);
        tl.set(scene, {{ opacity: 1 }}, start);
        if (index > 0) tl.set(scenes[index - 1], {{ opacity: 0 }}, start);
        if (index < scenes.length - 1) {{
          tl.fromTo(".mav-flash", {{ opacity: 0 }}, {{ opacity: 0.42, duration: 0.04, yoyo: true, repeat: 1 }}, start + dur - 0.16);
        }}
      }});

      {gsap_inits}

      tl.set({{}}, {{}}, {duration});
      registerTimeline("{html_mod.escape(timeline_id)}", tl, {duration});
      tl.pause().time({initial_time if initial_time is not None else f"Math.min(0.75, {duration} - 0.1)"});

      const audio = document.querySelector("#mav-audio");
      const play = document.querySelector("#mav-play");
      const pause = document.querySelector("#mav-pause");
      const restart = document.querySelector("#mav-restart");
      const seek = document.querySelector("#mav-seek");
      const time = document.querySelector("#mav-time");
      const mute = document.querySelector("#mav-mute");
      let syncing = false;
      function syncUi() {{
        if (!seek || !time) return;
        seek.value = String(tl.time());
        time.textContent = `${{tl.time().toFixed(2)}}s`;
      }}
      function seekTo(value) {{
        const next = Math.max(0, Math.min({duration}, Number(value) || 0));
        const current = tl.time();
        if (next <= 0.001 || next < current - 0.001) {{
          tl.time(0);
          resetPlaybackState();
        }}
        tl.time(next);
        if (audio) audio.currentTime = next;
        syncUi();
      }}
      play?.addEventListener("click", async () => {{
        if (tl.time() >= {duration} - 0.05) seekTo(0);
        if (audio) {{
          audio.currentTime = tl.time();
          try {{ await audio.play(); }} catch (err) {{}}
        }}
        tl.play();
      }});
      pause?.addEventListener("click", () => {{
        tl.pause();
        audio?.pause();
        syncUi();
      }});
      restart?.addEventListener("click", async () => {{
        seekTo(0);
        if (audio) {{ try {{ await audio.play(); }} catch (err) {{}} }}
        tl.play(0);
      }});
      seek?.addEventListener("input", () => {{
        tl.pause();
        audio?.pause();
        seekTo(seek.value);
      }});
      mute?.addEventListener("click", () => {{
        if (!audio) return;
        audio.muted = !audio.muted;
        mute.textContent = audio.muted ? "Unmute" : "Mute";
      }});
      audio?.addEventListener("timeupdate", () => {{
        if (syncing || audio.paused) return;
        syncing = true;
        if (Math.abs(tl.time() - audio.currentTime) > 0.08) tl.time(audio.currentTime);
        syncUi();
        syncing = false;
      }});
      tl.eventCallback("onUpdate", syncUi);
      tl.eventCallback("onComplete", () => audio?.pause());
      if (new URLSearchParams(location.search).get("autoplay") === "1") {{
        seekTo(0);
        audio?.pause();
        tl.play(0);
      }}
      syncUi();
      window.__mavResetPlaybackState = resetPlaybackState;
      window.__templateLabReady = true;
    </script>
  </body>
</html>
"""


def _audio_src_for_run(run_path: Path) -> str:
    return "../voiceover.mp3"


def build_preview_v3(run_path: Path) -> dict[str, Any]:
    """Build the V3 master preview HTML."""
    plan = _load_plan_with_scene_overrides(run_path)
    timing = read_json(run_path / "audio_timing.json")
    duration = float(timing["audio_duration_seconds"])

    composition_dir = run_path / "compositions"
    scene_dir = composition_dir / "scenes_v3"
    composition_dir.mkdir(parents=True, exist_ok=True)
    scene_dir.mkdir(parents=True, exist_ok=True)

    body = "\n".join(_scene_section(scene) for scene in plan["scenes"])
    gsap_inits = _gsap_init_calls(plan["scenes"])

    master_html = _master_html(
        title=f"{plan['title']} V3",
        body=body,
        gsap_inits=gsap_inits,
        project_prefix="../../../project",
        duration=duration,
        audio_src=_audio_src_for_run(run_path),
    )

    master_path = composition_dir / "master_v3.html"
    master_path.write_text(master_html, encoding="utf-8")

    scenes_payload = []
    for scene in plan["scenes"]:
        scene_duration = float(scene["duration"])
        scene_start = float(scene["start"])
        single_scene = {**scene, "start": 0.0, "duration": scene_duration}
        scene_html = _master_html(
            title=f"{scene['id']} {plan['title']} V3",
            body=_scene_section(single_scene),
            gsap_inits=_gsap_init_calls([single_scene]),
            project_prefix="../../../../project",
            duration=scene_duration,
            audio_src=None,
            timeline_id=f"mav_v3_{scene['id']}",
            initial_time=round(min(0.75, max(0.0, scene_duration - 0.1)), 3),
            show_controls=True,
        )
        scene_path = scene_dir / f"{scene['id']}.html"
        scene_path.write_text(scene_html, encoding="utf-8")
        scenes_payload.append(
            {
                "id": scene["id"],
                "path": str(scene_path.relative_to(run_path)),
                "start": scene_start,
                "duration": scene_duration,
                "paragraph_id": scene.get("paragraph_id"),
                "beat_label": scene.get("beat_label"),
            }
        )

    manifest = {
        "run_id": plan["run_id"],
        "title": plan["title"],
        "duration": duration,
        "version": "3.0",
        "scene_count": len(plan["scenes"]),
        "master": "compositions/master_v3.html",
        "audio": "voiceover.mp3",
        "scenes": scenes_payload,
        "hashes": {
            **_scene_source_hashes(run_path, plan["scenes"]),
            "master_composition": sha256_text(master_html),
            "audio": sha256_file(run_path / "voiceover.mp3") if (run_path / "voiceover.mp3").exists() else "",
            "dependencies": dependency_hashes(),
        },
        "validation": {
            "plan": "validation/plan_validation_v3.json",
            "visual_qa": "validation/visual_qa.json",
        },
        "narration_paragraphs": read_json(run_path / "narration.json").get("paragraphs", []),
        "audio_timing": timing,
    }
    write_json(run_path / "preview_manifest_v3.json", manifest)
    return manifest
