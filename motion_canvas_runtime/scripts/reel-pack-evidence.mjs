import {spawn} from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import process from 'node:process';
import puppeteer from 'puppeteer-core';
import sharp from 'sharp';

const ROOT = path.resolve(import.meta.dirname, '..');
const RUN_ROOT = process.env.MAV_MOTION_RUN_ROOT;
if (!RUN_ROOT) throw new Error('MAV_MOTION_RUN_ROOT is required.');
const args = process.argv.slice(2);
const valueAfter = flag => {
  const index = args.indexOf(flag);
  return index >= 0 ? args[index + 1] : null;
};
const OUTPUT_ROOT = path.resolve(valueAfter('--output') || path.join(RUN_ROOT, 'reel-pack-evidence'));
const manifest = JSON.parse(fs.readFileSync(path.join(RUN_ROOT, 'manifest.json'), 'utf8'));
const units = manifest.reels || manifest.shots || manifest.chapters || [];
if (units.length !== 1) throw new Error(`Standalone Reel evidence expects one scene, received ${units.length}.`);
const unit = units[0];
const width = Number(process.env.MAV_MOTION_CANVAS_WIDTH || manifest.canvas?.width || 1080);
const height = Number(process.env.MAV_MOTION_CANVAS_HEIGHT || manifest.canvas?.height || 1920);
const displayReelId = String(manifest.standalone_reel_id || unit.scene_id || 'reel_001');
const unitDirectory = manifest.timeline_mode === 'immutable_reels' ? 'reels' : manifest.timeline_mode === 'immutable_shots' ? 'shots' : 'chapters';
const internalId = String(unit.scene_id);
const CONTRACT_START = '/* MAV_VISUAL_CONTRACT';
const CONTRACT_END = 'MAV_VISUAL_CONTRACT */';
const BACKGROUND = [7, 17, 31];

function chromePath() {
  const candidates = [
    process.env.CHROME_PATH,
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
  ].filter(Boolean);
  const found = candidates.find(candidate => fs.existsSync(candidate));
  if (!found) throw new Error('Chrome/Chromium not found. Set CHROME_PATH.');
  return found;
}

async function freePort() {
  return await new Promise((resolve, reject) => {
    const server = http.createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      server.close(() => resolve(address.port));
    });
  });
}

async function waitFor(url, timeoutMs = 30000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {}
    await new Promise(resolve => setTimeout(resolve, 150));
  }
  throw new Error(`Motion Canvas server did not start within ${timeoutMs}ms.`);
}

function parseContract(source) {
  const start = source.indexOf(CONTRACT_START);
  if (start < 0) return {};
  const contentStart = start + CONTRACT_START.length;
  const end = source.indexOf(CONTRACT_END, contentStart);
  if (end < 0) return {};
  try {
    return JSON.parse(source.slice(contentStart, end).trim());
  } catch {
    return {};
  }
}

function parseCues(source) {
  const match = source.match(/export const CUES = (\{.*\}) as const;/s);
  if (!match) return {};
  try {
    return JSON.parse(match[1]);
  } catch {
    return {};
  }
}

function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}

function candidateTimes(contract, cues, duration) {
  const candidates = [];
  for (const checkpoint of contract.review_checkpoints || []) {
    let time = null;
    if (checkpoint.cue && Array.isArray(cues[checkpoint.cue])) {
      const occurrence = Number(checkpoint.occurrence || 0);
      if (cues[checkpoint.cue][occurrence] != null) {
        time = Number(cues[checkpoint.cue][occurrence]) + Number(checkpoint.offset_seconds ?? 0.35);
      }
    } else if (checkpoint.local_time != null) {
      time = Number(checkpoint.local_time);
    }
    if (Number.isFinite(time)) {
      candidates.push({
        time,
        cue: checkpoint.cue || null,
        purpose: String(checkpoint.purpose || 'Declared stable completed state'),
        semanticBonus: 0.6,
      });
    }
  }
  for (const beat of unit.beats || []) {
    candidates.push({
      time: Math.max(Number(beat.local_start || 0) + 0.25, Number(beat.local_end || duration) - 0.3),
      beat_id: beat.beat_id || beat.id,
      purpose: 'Stable state near the end of a narration beat',
      semanticBonus: 0.2,
    });
  }
  candidates.push({
    time: Math.max(0.1, duration - 0.3),
    purpose: 'Final persistent teaching state',
    semanticBonus: 0.3,
  });
  const unique = new Map();
  for (const candidate of candidates) {
    const time = clamp(Number(candidate.time || 0), 0.05, Math.max(0.05, duration - 0.05));
    const key = time.toFixed(3);
    const previous = unique.get(key);
    if (!previous || candidate.semanticBonus > previous.semanticBonus) unique.set(key, {...candidate, time});
  }
  return [...unique.values()];
}

async function metrics(file, previousFile) {
  const current = await sharp(file).resize(135, 240, {fit: 'fill'}).removeAlpha().raw().toBuffer();
  const previous = previousFile
    ? await sharp(previousFile).resize(135, 240, {fit: 'fill'}).removeAlpha().raw().toBuffer()
    : current;
  let foreground = 0;
  let difference = 0;
  const pixels = current.length / 3;
  for (let offset = 0; offset < current.length; offset += 3) {
    const backgroundDistance =
      Math.abs(current[offset] - BACKGROUND[0]) +
      Math.abs(current[offset + 1] - BACKGROUND[1]) +
      Math.abs(current[offset + 2] - BACKGROUND[2]);
    if (backgroundDistance > 42) foreground += 1;
    difference +=
      Math.abs(current[offset] - previous[offset]) +
      Math.abs(current[offset + 1] - previous[offset + 1]) +
      Math.abs(current[offset + 2] - previous[offset + 2]);
  }
  return {density: foreground / pixels, motion: difference / (pixels * 3 * 255)};
}

function select(scored, count, duration) {
  const chosen = [];
  const gap = Math.max(0.65, duration / 10);
  for (const item of [...scored].sort((a, b) => b.score - a.score)) {
    if (chosen.every(previous => Math.abs(previous.time - item.time) >= gap)) chosen.push(item);
    if (chosen.length >= count) break;
  }
  return (chosen.length ? chosen : scored.slice(0, 1)).sort((a, b) => a.time - b.time);
}

function xml(value) {
  return String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;',
  }[character]));
}

async function panel(file, frame) {
  const imageWidth = 360;
  const imageHeight = 640;
  const footerHeight = 72;
  const image = await sharp(file).resize(imageWidth, imageHeight, {fit: 'fill'}).png().toBuffer();
  const footer = Buffer.from(`<svg width="${imageWidth}" height="${footerHeight}" xmlns="http://www.w3.org/2000/svg">
    <rect width="${imageWidth}" height="${footerHeight}" fill="#0e1d31"/>
    <text x="14" y="26" fill="#eaf3ff" font-size="18" font-family="Arial" font-weight="700">${xml(displayReelId)} · ${xml(frame.frame_id)} · ${frame.local_time.toFixed(2)}s</text>
    <text x="14" y="52" fill="#91a8c5" font-size="13" font-family="Arial">${xml((frame.cue ? `cue: ${frame.cue} · ` : '') + frame.purpose).slice(0, 54)}</text>
  </svg>`);
  return await sharp({
    create: {width: imageWidth, height: imageHeight + footerHeight, channels: 4, background: '#07111f'},
  }).composite([{input: image, left: 0, top: 0}, {input: footer, left: 0, top: imageHeight}]).png().toBuffer();
}

fs.mkdirSync(OUTPUT_ROOT, {recursive: true});
fs.mkdirSync(path.join(OUTPUT_ROOT, 'frames'), {recursive: true});
fs.mkdirSync(path.join(OUTPUT_ROOT, 'candidates'), {recursive: true});
const source = fs.readFileSync(path.join(RUN_ROOT, unitDirectory, `${internalId}.tsx`), 'utf8');
const cues = parseCues(fs.readFileSync(path.join(RUN_ROOT, unitDirectory, `${internalId}.cues.ts`), 'utf8'));
const contract = parseContract(source);
const duration = Number(unit.render_duration ?? unit.duration ?? 0);
const candidates = candidateTimes(contract, cues, duration);

const port = await freePort();
const vite = path.join(ROOT, 'node_modules', 'vite', 'bin', 'vite.js');
const server = spawn(process.execPath, [vite, '--host', '127.0.0.1', '--port', String(port)], {
  cwd: ROOT,
  env: process.env,
  stdio: ['ignore', 'pipe', 'pipe'],
});
let serverLog = '';
server.stdout.on('data', chunk => { serverLog += String(chunk); });
server.stderr.on('data', chunk => { serverLog += String(chunk); });
let browser;

try {
  const url = `http://127.0.0.1:${port}/render.html`;
  await waitFor(url);
  browser = await puppeteer.launch({
    executablePath: chromePath(),
    headless: true,
    args: ['--no-sandbox', '--disable-gpu', '--font-render-hinting=none'],
  });
  const page = await browser.newPage();
  await page.setViewport({width, height, deviceScaleFactor: 1});
  await page.goto(url, {waitUntil: 'networkidle0', timeout: 60000});
  await page.waitForFunction(() => window.__motionCanvasRobotReady === true, {timeout: 120000});
  const canvas = await page.$('#robot-canvas');
  if (!canvas) throw new Error('Motion Canvas render surface not found.');
  const capture = async (time, target) => {
    await page.evaluate(at => window.MotionCanvasRobot.seek(at), time);
    await canvas.screenshot({path: target, type: 'png'});
  };
  const scored = [];
  for (const [index, candidate] of candidates.entries()) {
    const current = path.join(OUTPUT_ROOT, 'candidates', `${String(index).padStart(2, '0')}.png`);
    const previous = path.join(OUTPUT_ROOT, 'candidates', `${String(index).padStart(2, '0')}-previous.png`);
    await capture(candidate.time, current);
    await capture(Math.max(0.01, candidate.time - 0.16), previous);
    const measured = await metrics(current, previous);
    scored.push({
      ...candidate,
      ...measured,
      score: measured.density * 1.25 + (1 - measured.motion) * 0.8 + candidate.semanticBonus,
      current,
    });
  }
  const declared = Array.isArray(contract.review_checkpoints) ? contract.review_checkpoints.length : 0;
  const targetCount = clamp(declared || ((unit.beats || []).length <= 1 ? 1 : 2), 1, 3);
  const chosen = select(scored, targetCount, duration);
  const frames = [];
  for (const [index, item] of chosen.entries()) {
    const frameId = `${displayReelId}-${String.fromCharCode(65 + index)}`;
    const relative = `frames/${frameId}.png`;
    await sharp(item.current).png().toFile(path.join(OUTPUT_ROOT, relative));
    frames.push({
      reel_id: displayReelId,
      chapter_number: Number(displayReelId.split('_')[1] || 0),
      frame_id: frameId,
      file: relative,
      local_time: Number(item.time.toFixed(3)),
      global_time: Number(item.time.toFixed(3)),
      cue: item.cue || null,
      beat_id: item.beat_id || null,
      purpose: item.purpose,
      density: Number(item.density.toFixed(4)),
      motion: Number(item.motion.toFixed(4)),
    });
  }
  const panels = [];
  for (const frame of frames) panels.push(await panel(path.join(OUTPUT_ROOT, frame.file), frame));
  const composites = panels.map((input, index) => ({input, left: index * 360, top: 0}));
  const contactName = 'contact-sheet.png';
  await sharp({
    create: {width: Math.max(360, panels.length * 360), height: 712, channels: 4, background: '#07111f'},
  }).composite(composites).png().toFile(path.join(OUTPUT_ROOT, contactName));
  fs.writeFileSync(path.join(OUTPUT_ROOT, 'evidence.json'), JSON.stringify({
    version: '1.0',
    reels: [{
      reel_id: displayReelId,
      chapter_number: Number(displayReelId.split('_')[1] || 0),
      duration,
      scene_claim: contract.scene_claim || '',
      frames,
    }],
    contact_sheets: [contactName],
  }, null, 2) + '\n');
} catch (error) {
  throw new Error(`${error}\nVite log:\n${serverLog.slice(-12000)}`);
} finally {
  if (browser) await browser.close();
  server.kill('SIGTERM');
}
