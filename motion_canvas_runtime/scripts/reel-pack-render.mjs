import {spawn, spawnSync} from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import process from 'node:process';
import puppeteer from 'puppeteer-core';
import sharp from 'sharp';

const ROOT = path.resolve(import.meta.dirname, '..');
const RUN_ROOT = process.env.MAV_MOTION_RUN_ROOT;
if (!RUN_ROOT) throw new Error('MAV_MOTION_RUN_ROOT is required for standalone Reel rendering.');
const manifest = JSON.parse(fs.readFileSync(path.join(RUN_ROOT, 'manifest.json'), 'utf8'));
const width = Number(process.env.MAV_MOTION_CANVAS_WIDTH || manifest.canvas?.width || 1080);
const height = Number(process.env.MAV_MOTION_CANVAS_HEIGHT || manifest.canvas?.height || 1920);
const videoMode = process.argv.includes('--video');
const previewMode = !videoMode || process.argv.includes('--preview');
const previewRoot = path.join(RUN_ROOT, 'preview');
const frameRoot = path.join(RUN_ROOT, 'frames');
fs.mkdirSync(previewRoot, {recursive: true});

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
  const consoleErrors = [];
  const pageErrors = [];
  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('pageerror', error => pageErrors.push(String(error)));
  await page.goto(url, {waitUntil: 'networkidle0', timeout: 60000});
  await page.waitForFunction(() => window.__motionCanvasRobotReady === true, {timeout: 120000});
  const dimensions = await page.evaluate(() => ({
    width: window.MotionCanvasRobot.width,
    height: window.MotionCanvasRobot.height,
    fps: window.MotionCanvasRobot.fps,
    duration: window.MotionCanvasRobot.duration(),
  }));
  if (dimensions.width !== width || dimensions.height !== height) {
    throw new Error(`Render host size mismatch: ${dimensions.width}x${dimensions.height}, expected ${width}x${height}`);
  }
  const canvas = await page.$('#robot-canvas');
  if (!canvas) throw new Error('Motion Canvas render surface not found.');
  const capture = async (time, target) => {
    await page.evaluate(at => window.MotionCanvasRobot.seek(at), time);
    await canvas.screenshot({path: target, type: 'png'});
  };

  const expected = Number(manifest.render_duration || 0);
  const timelineDelta = expected ? dimensions.duration - expected : 0;
  const timelineStable = !expected || Math.abs(timelineDelta) <= 1.1 / dimensions.fps;
  if (!timelineStable) throw new Error(`Standalone Reel timeline drifted by ${timelineDelta}s`);

  if (previewMode) {
    const ratios = [0, 0.25, 0.5, 0.75, 1];
    const files = [];
    for (const [index, ratio] of ratios.entries()) {
      const target = path.join(previewRoot, `${String(index).padStart(2, '0')}-${Math.round(ratio * 100)}.png`);
      await capture(Math.max(0, Math.min(dimensions.duration, dimensions.duration * ratio)), target);
      files.push(target);
    }
    const repeat = path.join(previewRoot, 'deterministic-repeat.png');
    await capture(dimensions.duration * 0.5, repeat);
    const deterministic = fs.readFileSync(files[2]).equals(fs.readFileSync(repeat));
    const panelWidth = 270;
    const panelHeight = 480;
    const composites = [];
    for (const [index, file] of files.entries()) {
      composites.push({
        input: await sharp(file).resize(panelWidth, panelHeight, {fit: 'fill'}).png().toBuffer(),
        left: index * panelWidth,
        top: 0,
      });
    }
    await sharp({
      create: {width: panelWidth * files.length, height: panelHeight, channels: 4, background: '#07111f'},
    }).composite(composites).png().toFile(path.join(previewRoot, 'contact-sheet.png'));
    const validation = {
      status: deterministic && timelineStable && !consoleErrors.length && !pageErrors.length ? 'passed' : 'failed',
      canvas: {width, height},
      duration: dimensions.duration,
      expectedDuration: expected,
      timelineDelta,
      timelineStable,
      deterministic,
      consoleErrors,
      pageErrors,
    };
    fs.writeFileSync(path.join(RUN_ROOT, 'validation.json'), JSON.stringify(validation, null, 2) + '\n');
    if (validation.status !== 'passed') throw new Error(`Portrait preview validation failed: ${JSON.stringify(validation)}`);
  }

  if (videoMode) {
    fs.rmSync(frameRoot, {recursive: true, force: true});
    fs.mkdirSync(frameRoot, {recursive: true});
    const frameCount = Math.ceil(dimensions.duration * dimensions.fps);
    for (let frame = 0; frame <= frameCount; frame += 1) {
      const target = path.join(frameRoot, `${String(frame).padStart(6, '0')}.png`);
      await capture(frame / dimensions.fps, target);
      if (frame % Math.max(1, dimensions.fps * 5) === 0 || frame === frameCount) {
        process.stdout.write(`[reel-render] ${frame + 1}/${frameCount + 1} frames\n`);
      }
    }
    const silent = path.join(RUN_ROOT, 'final.silent.mp4');
    const output = path.join(RUN_ROOT, 'final.mp4');
    const encode = spawnSync('ffmpeg', [
      '-y',
      '-framerate', String(dimensions.fps),
      '-i', path.join(frameRoot, '%06d.png'),
      '-c:v', 'libx264',
      '-pix_fmt', 'yuv420p',
      '-movflags', '+faststart',
      silent,
    ], {encoding: 'utf8'});
    if (encode.status !== 0) throw new Error(`ffmpeg video encoding failed: ${encode.stderr}`);
    const audio = path.join(RUN_ROOT, 'voiceover.mp3');
    if (fs.existsSync(audio) && fs.statSync(audio).size > 0) {
      const mux = spawnSync('ffmpeg', [
        '-y',
        '-i', silent,
        '-i', audio,
        '-map', '0:v:0',
        '-map', '1:a:0',
        '-c:v', 'copy',
        '-c:a', 'aac',
        '-b:a', '192k',
        '-shortest',
        '-movflags', '+faststart',
        output,
      ], {encoding: 'utf8'});
      if (mux.status !== 0) throw new Error(`ffmpeg audio mux failed: ${mux.stderr}`);
      fs.rmSync(silent, {force: true});
    } else {
      fs.renameSync(silent, output);
    }
    fs.writeFileSync(path.join(RUN_ROOT, 'render-report.json'), JSON.stringify({
      status: 'completed',
      output,
      canvas: {width, height},
      fps: dimensions.fps,
      duration: dimensions.duration,
      frameCount: frameCount + 1,
      completedAt: new Date().toISOString(),
    }, null, 2) + '\n');
  }
} catch (error) {
  throw new Error(`${error}\nVite log:\n${serverLog.slice(-12000)}`);
} finally {
  if (browser) await browser.close();
  server.kill('SIGTERM');
}
