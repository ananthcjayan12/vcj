import './render-host';

const query = new URLSearchParams(location.search);
const audioStart = Math.max(0, Number(query.get('start') || 0));
const audioEnd = Math.max(audioStart, Number(query.get('end') || audioStart));
const visualStart = Math.max(0, Number(query.get('visualStart') || audioStart));
const visualEnd = Math.max(visualStart, Number(query.get('visualEnd') || audioEnd));
const duration = Math.max(0.001, audioEnd - audioStart);
const visualDuration = Math.max(0.001, visualEnd - visualStart);
const toggle = document.querySelector<HTMLButtonElement>('#toggle')!;
const scrubber = document.querySelector<HTMLInputElement>('#scrubber')!;
const time = document.querySelector<HTMLSpanElement>('#time')!;
const stage = document.querySelector<HTMLDivElement>('#stage')!;
const audio = new Audio('/voiceover.mp3');
audio.preload = 'auto';

const ready = async () => {
  while (!window.__motionCanvasRobotReady) await new Promise(resolve => setTimeout(resolve, 25));
  const canvas = document.querySelector('canvas');
  if (canvas) {
    try {
      const profile = await fetch('/render-profile.json', {cache: 'no-store'}).then(response => response.json());
      canvas.style.aspectRatio = `${Number(profile.width || 1920)} / ${Number(profile.height || 1080)}`;
    } catch {}
    stage.append(canvas);
  }
  await window.MotionCanvasRobot.seek(visualStart);
};

const clock = (seconds: number) => {
  const rounded = Math.max(0, Math.floor(seconds));
  return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, '0')}`;
};

let rendering = false;
let lastFrame = -1;
const paint = async (localTime: number) => {
  const frame = Math.round(localTime * window.MotionCanvasRobot.fps);
  if (rendering || frame === lastFrame) return;
  rendering = true;
  lastFrame = frame;
  try {
    await window.MotionCanvasRobot.seek(visualStart + Math.min(localTime, visualDuration));
  } finally {
    rendering = false;
  }
};

const update = () => {
  const localTime = Math.min(duration, Math.max(0, audio.currentTime - audioStart));
  scrubber.value = String(localTime / duration);
  time.textContent = `${clock(localTime)} / ${clock(duration)}`;
  void paint(localTime);
  if (!audio.paused && audio.currentTime < audioEnd) requestAnimationFrame(update);
  if (audio.currentTime >= audioEnd) {
    audio.pause();
    toggle.textContent = 'Replay';
  }
};

toggle.addEventListener('click', async () => {
  if (!audio.paused) {
    audio.pause();
    toggle.textContent = 'Play';
    return;
  }
  if (audio.currentTime < audioStart || audio.currentTime >= audioEnd) audio.currentTime = audioStart;
  await audio.play();
  toggle.textContent = 'Pause';
  requestAnimationFrame(update);
});

scrubber.addEventListener('input', () => {
  audio.currentTime = audioStart + Number(scrubber.value) * duration;
  void paint(audio.currentTime - audioStart);
  update();
});

audio.addEventListener('loadedmetadata', () => {
  audio.currentTime = audioStart;
  update();
});
audio.addEventListener('pause', () => {
  if (audio.currentTime < audioEnd) toggle.textContent = 'Play';
});

await ready();
audio.currentTime = audioStart;
update();
