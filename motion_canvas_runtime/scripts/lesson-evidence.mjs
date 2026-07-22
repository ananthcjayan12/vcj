import {spawn} from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import process from 'node:process';
import puppeteer from 'puppeteer-core';
import sharp from 'sharp';

const ROOT = path.resolve(import.meta.dirname, '..');
const RUN_ROOT = process.env.MAV_MOTION_RUN_ROOT || path.join(ROOT, 'runs', 'latest');
const args = process.argv.slice(2);
const valueAfter = flag => {
  const index = args.indexOf(flag);
  return index >= 0 ? args[index + 1] : null;
};
const OUTPUT_ROOT = path.resolve(valueAfter('--output') || path.join(RUN_ROOT, 'lesson-review', 'evidence'));
const selectedReels = new Set((valueAfter('--reels') || '').split(',').map(value => value.trim()).filter(Boolean));
const manifest = JSON.parse(fs.readFileSync(path.join(RUN_ROOT, 'manifest.json'), 'utf8'));
const units = manifest.reels || manifest.shots || manifest.chapters || [];
const unitDirectory = manifest.timeline_mode === 'immutable_reels' ? 'reels' : manifest.timeline_mode === 'immutable_shots' ? 'shots' : 'chapters';
const reels = selectedReels.size ? units.filter(unit => selectedReels.has(String(unit.scene_id))) : units;
const CONTRACT_START = '/* MAV_VISUAL_CONTRACT';
const CONTRACT_END = 'MAV_VISUAL_CONTRACT */';
const BACKGROUND = [7, 17, 31];

function findChrome() {
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

async function waitForServer(url, timeoutMs = 30000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {}
    await new Promise(resolve => setTimeout(resolve, 150));
  }
  throw new Error(`Motion Canvas server did not start within ${timeoutMs} ms.`);
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

function uniqueCandidates(candidates, duration) {
  const byTime = new Map();
  for (const candidate of candidates) {
    const time = clamp(Number(candidate.time || 0), 0.05, Math.max(0.05, duration - 0.05));
    const key = time.toFixed(3);
    const existing = byTime.get(key);
    if (!existing || Number(candidate.semanticBonus || 0) > Number(existing.semanticBonus || 0)) {
      byTime.set(key, {...candidate, time});
    }
  }
  return [...byTime.values()].sort((a, b) => a.time - b.time);
}

function candidateTimes(unit, contract, cues) {
  const duration = Number(unit.render_duration ?? unit.duration ?? 0);
  const candidates = [];
  const beats = unit.beats || [];
  const beatById = new Map(beats.map(beat => [String(beat.beat_id || beat.id), beat]));
  for (const checkpoint of contract.review_checkpoints || []) {
    let time = null;
    if (checkpoint.cue && Array.isArray(cues[checkpoint.cue])) {
      const occurrence = Number(checkpoint.occurrence || 0);
      if (cues[checkpoint.cue][occurrence] != null) {
        time = Number(cues[checkpoint.cue][occurrence]) + Number(checkpoint.offset_seconds ?? 0.35);
      }
    } else if (checkpoint.local_time != null) {
      time = Number(checkpoint.local_time);
    } else if (checkpoint.beat_id && beatById.has(String(checkpoint.beat_id))) {
      const beat = beatById.get(String(checkpoint.beat_id));
      const position = String(checkpoint.position || 'end');
      if (position === 'start') time = Number(beat.local_start || 0) + Number(checkpoint.offset_seconds ?? 0.35);
      else if (position === 'mid') time = (Number(beat.local_start || 0) + Number(beat.local_end || 0)) / 2;
      else time = Number(beat.local_end || duration) + Number(checkpoint.offset_seconds ?? -0.25);
    }
    if (time != null && Number.isFinite(time)) {
      candidates.push({
        time,
        kind: 'contract',
        semanticBonus: 0.5,
        cue: checkpoint.cue || null,
        purpose: String(checkpoint.purpose || 'Declared completed visual state'),
      });
    }
  }
  for (const beat of beats) {
    const end = Number(beat.local_end ?? 0);
    const start = Number(beat.local_start ?? 0);
    candidates.push({
      time: Math.max(start + 0.25, end - 0.3),
      kind: 'beat-end',
      semanticBonus: 0.2,
      beat_id: beat.beat_id || beat.id,
      purpose: 'Stable state near the end of a narration beat',
    });
  }
  candidates.push({time: Math.max(0.1, duration - 0.3), kind: 'final', semanticBonus: 0.25, purpose: 'Final persistent teaching state'});
  if (!candidates.length) candidates.push({time: duration * 0.75, kind: 'fallback', semanticBonus: 0, purpose: 'Fallback late reel state'});
  return uniqueCandidates(candidates, duration);
}

async function metrics(file, previousFile) {
  const current = await sharp(file).resize(240, 135, {fit: 'fill'}).removeAlpha().raw().toBuffer();
  const previous = previousFile
    ? await sharp(previousFile).resize(240, 135, {fit: 'fill'}).removeAlpha().raw().toBuffer()
    : current;
  let changed = 0;
  let difference = 0;
  const pixels = current.length / 3;
  for (let offset = 0; offset < current.length; offset += 3) {
    const backgroundDistance = Math.abs(current[offset] - BACKGROUND[0]) + Math.abs(current[offset + 1] - BACKGROUND[1]) + Math.abs(current[offset + 2] - BACKGROUND[2]);
    if (backgroundDistance > 42) changed += 1;
    difference += Math.abs(current[offset] - previous[offset]) + Math.abs(current[offset + 1] - previous[offset + 1]) + Math.abs(current[offset + 2] - previous[offset + 2]);
  }
  return {
    density: changed / pixels,
    motion: difference / (pixels * 3 * 255),
  };
}

function selectFrames(scored, targetCount, duration) {
  const chosen = [];
  const minimumGap = Math.max(0.65, duration / Math.max(8, targetCount * 5));
  for (const candidate of [...scored].sort((a, b) => b.score - a.score)) {
    if (chosen.every(item => Math.abs(item.time - candidate.time) >= minimumGap)) chosen.push(candidate);
    if (chosen.length >= targetCount) break;
  }
  if (!chosen.length && scored.length) chosen.push(scored[0]);
  return chosen.sort((a, b) => a.time - b.time);
}

function xml(value) {
  return String(value ?? '').replace(/[&<>"']/g, character => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;'}[character]));
}

function truncate(value, length) {
  const text = String(value || '');
  return text.length <= length ? text : `${text.slice(0, length - 1)}…`;
}

async function labelledPanel(file, frame) {
  const image = await sharp(file).resize(640, 360, {fit: 'fill'}).png().toBuffer();
  const footer = Buffer.from(`<svg width="640" height="48" xmlns="http://www.w3.org/2000/svg">
    <rect width="640" height="48" fill="#0e1d31"/>
    <text x="14" y="20" fill="#eaf3ff" font-size="15" font-family="Arial, sans-serif" font-weight="700">${xml(frame.reel_id)} · CH ${xml(frame.chapter_number)} · ${xml(frame.frame_id)} · ${frame.local_time.toFixed(2)}s</text>
    <text x="14" y="39" fill="#91a8c5" font-size="12" font-family="Arial, sans-serif">${xml(truncate(frame.cue ? `cue: ${frame.cue} · ${frame.purpose}` : frame.purpose, 92))}</text>
  </svg>`);
  return await sharp({create: {width: 640, height: 408, channels: 4, background: '#07111f'}})
    .composite([{input: image, left: 0, top: 0}, {input: footer, left: 0, top: 360}])
    .png()
    .toBuffer();
}

fs.mkdirSync(OUTPUT_ROOT, {recursive: true});
fs.mkdirSync(path.join(OUTPUT_ROOT, 'frames'), {recursive: true});
fs.mkdirSync(path.join(OUTPUT_ROOT, 'candidates'), {recursive: true});
const port = await freePort();
const viteBin = path.join(ROOT, 'node_modules', 'vite', 'bin', 'vite.js');
const server = spawn(process.execPath, [viteBin, '--host', '127.0.0.1', '--port', String(port)], {cwd: ROOT, stdio: ['ignore', 'pipe', 'pipe']});
let serverLog = '';
server.stdout.on('data', chunk => { serverLog += String(chunk); });
server.stderr.on('data', chunk => { serverLog += String(chunk); });
let browser;

try {
  const url = `http://127.0.0.1:${port}/render.html`;
  await waitForServer(url);
  browser = await puppeteer.launch({
    executablePath: findChrome(),
    headless: true,
    args: ['--no-sandbox', '--disable-gpu', '--font-render-hinting=none'],
  });
  const page = await browser.newPage();
  await page.setViewport({width: 1920, height: 1080, deviceScaleFactor: 1});
  await page.goto(url, {waitUntil: 'networkidle0', timeout: 60000});
  await page.waitForFunction(() => window.__motionCanvasRobotReady === true, {timeout: 120000});
  const canvas = await page.$('#robot-canvas');
  if (!canvas) throw new Error('Motion Canvas render surface was not found.');
  const capture = async (globalTime, target) => {
    await page.evaluate(at => window.MotionCanvasRobot.seek(at), globalTime);
    await canvas.screenshot({path: target, type: 'png'});
  };

  const evidence = {version: '2.0', reels: [], contact_sheets: []};
  const allFrames = [];
  for (const [index, unit] of reels.entries()) {
    const reelId = String(unit.scene_id);
    const sourcePath = path.join(RUN_ROOT, unitDirectory, `${reelId}.tsx`);
    const cuePath = path.join(RUN_ROOT, unitDirectory, `${reelId}.cues.ts`);
    const source = fs.existsSync(sourcePath) ? fs.readFileSync(sourcePath, 'utf8') : '';
    const cues = fs.existsSync(cuePath) ? parseCues(fs.readFileSync(cuePath, 'utf8')) : {};
    const contract = parseContract(source);
    const duration = Number(unit.render_duration ?? unit.duration ?? 0);
    const globalStart = Number(unit.render_absolute_start ?? unit.absolute_start ?? 0);
    const candidates = candidateTimes(unit, contract, cues);
    const scored = [];
    for (const [candidateIndex, candidate] of candidates.entries()) {
      const currentPath = path.join(OUTPUT_ROOT, 'candidates', `${reelId}-${String(candidateIndex).padStart(2, '0')}.png`);
      const previousPath = path.join(OUTPUT_ROOT, 'candidates', `${reelId}-${String(candidateIndex).padStart(2, '0')}-previous.png`);
      await capture(globalStart + candidate.time, currentPath);
      await capture(globalStart + Math.max(0.01, candidate.time - 0.16), previousPath);
      const measured = await metrics(currentPath, previousPath);
      scored.push({
        ...candidate,
        ...measured,
        score: measured.density * 1.25 + (1 - measured.motion) * 0.8 + Number(candidate.semanticBonus || 0),
        currentPath,
      });
    }
    const declaredCount = Array.isArray(contract.review_checkpoints) ? contract.review_checkpoints.length : 0;
    const fallbackCount = (unit.beats || []).length <= 1 ? 1 : (unit.beats || []).length <= 3 ? 2 : 3;
    const targetCount = clamp(declaredCount || fallbackCount, 1, 3);
    const chosen = selectFrames(scored, targetCount, duration);
    const reelFrames = [];
    for (const [chosenIndex, candidate] of chosen.entries()) {
      const frameId = `${reelId}-${String.fromCharCode(65 + chosenIndex)}`;
      const relativeFile = `frames/${frameId}.png`;
      const target = path.join(OUTPUT_ROOT, relativeFile);
      await sharp(candidate.currentPath).png().toFile(target);
      const frame = {
        reel_id: reelId,
        chapter_number: index + 1,
        frame_id: frameId,
        file: relativeFile,
        local_time: Number(candidate.time.toFixed(3)),
        global_time: Number((globalStart + candidate.time).toFixed(3)),
        cue: candidate.cue || null,
        beat_id: candidate.beat_id || null,
        purpose: candidate.purpose,
        density: Number(candidate.density.toFixed(4)),
        motion: Number(candidate.motion.toFixed(4)),
      };
      reelFrames.push(frame);
      allFrames.push(frame);
    }
    evidence.reels.push({
      reel_id: reelId,
      chapter_number: index + 1,
      duration,
      scene_claim: contract.scene_claim || '',
      frames: reelFrames,
    });
  }

  const panels = [];
  for (const frame of allFrames) panels.push(await labelledPanel(path.join(OUTPUT_ROOT, frame.file), frame));
  const panelsPerSheet = 18;
  for (let offset = 0; offset < panels.length; offset += panelsPerSheet) {
    const pagePanels = panels.slice(offset, offset + panelsPerSheet);
    const columns = 3;
    const rows = Math.ceil(pagePanels.length / columns);
    const composites = pagePanels.map((input, panelIndex) => ({
      input,
      left: (panelIndex % columns) * 640,
      top: Math.floor(panelIndex / columns) * 408,
    }));
    const name = `contact-sheet-${String(evidence.contact_sheets.length + 1).padStart(2, '0')}.png`;
    await sharp({create: {width: 1920, height: rows * 408, channels: 4, background: '#07111f'}})
      .composite(composites)
      .png()
      .toFile(path.join(OUTPUT_ROOT, name));
    evidence.contact_sheets.push(name);
  }
  fs.writeFileSync(path.join(OUTPUT_ROOT, 'evidence.json'), JSON.stringify(evidence, null, 2) + '\n');
} catch (error) {
  throw new Error(`${error}\nVite log:\n${serverLog.slice(-12000)}`);
} finally {
  if (browser) await browser.close();
  server.kill('SIGTERM');
}
