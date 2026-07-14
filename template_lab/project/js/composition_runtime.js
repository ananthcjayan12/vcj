export function scaleToViewport(root) {
  const apply = () => {
    const scale = Math.min(window.innerWidth / 1920, window.innerHeight / 1080);
    root.style.transform = `scale(${scale})`;
    root.style.marginLeft = `${(window.innerWidth - 1920 * scale) / 2}px`;
    root.style.marginTop = `${(window.innerHeight - 1080 * scale) / 2}px`;
  };
  apply();
  window.addEventListener("resize", apply);
}

export function registerTimeline(id, tl, duration) {
  tl.set({}, {}, duration);
  window.__timelines = window.__timelines || {};
  window.__timelines[id] = tl;
  window.__templateLabTimeline = tl;
  window.__templateLabDuration = duration;
  updateBeatReadout(0);
  tl.eventCallback("onUpdate", () => updateBeatReadout(tl.time()));
}

export function updateBeatReadout(time) {
  const readout = document.querySelector(".debug-readout");
  if (!readout) return;
  const beat = document.querySelector(`[data-beat-start][data-beat-end]`);
  let label = "hold";
  document.querySelectorAll("[data-beat-start][data-beat-end]").forEach((el) => {
    const start = Number(el.dataset.beatStart);
    const end = Number(el.dataset.beatEnd);
    if (time >= start && time <= end) label = el.dataset.beat || label;
  });
  readout.textContent = `${time.toFixed(2)}s / ${label}`;
}
