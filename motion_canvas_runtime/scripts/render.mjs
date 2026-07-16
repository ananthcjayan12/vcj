import {spawn, spawnSync} from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import process from 'node:process';
import puppeteer from 'puppeteer-core';
import sharp from 'sharp';

const ROOT = path.resolve(import.meta.dirname, '..');
const RUN_ROOT = process.env.MAV_MOTION_RUN_ROOT || path.join(ROOT, 'runs', 'latest');
const PREVIEW_ROOT = path.join(RUN_ROOT, 'preview');
const FRAME_ROOT = path.join(RUN_ROOT, 'frames');
const videoMode = process.argv.includes('--video');
const previewMode = process.argv.includes('--preview') || !videoMode;

function findChrome() {
  const candidates = [
    process.env.CHROME_PATH,
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  ].filter(Boolean);
  const found = candidates.find(candidate => fs.existsSync(candidate));
  if (!found) throw new Error('Chrome/Chromium not found. Set CHROME_PATH.');
  return found;
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return 'estimating…';
  const rounded = Math.round(seconds);
  const hours = Math.floor(rounded / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  const remainder = rounded % 60;
  return hours
    ? `${hours}h ${String(minutes).padStart(2, '0')}m ${String(remainder).padStart(2, '0')}s`
    : `${minutes}m ${String(remainder).padStart(2, '0')}s`;
}

function renderLog(message) {
  process.stdout.write(`[render] ${message}\n`);
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
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {}
    await new Promise(resolve => setTimeout(resolve, 150));
  }
  throw new Error(`Motion Canvas server did not start within ${timeoutMs}ms.`);
}

fs.mkdirSync(PREVIEW_ROOT, {recursive: true});
const port = await freePort();
const viteBin = path.join(ROOT, 'node_modules', 'vite', 'bin', 'vite.js');
const server = spawn(
  process.execPath,
  [viteBin, '--host', '127.0.0.1', '--port', String(port)],
  {cwd: ROOT, stdio: ['ignore', 'pipe', 'pipe']},
);
let serverLog = '';
server.stdout.on('data', chunk => { serverLog += String(chunk); });
server.stderr.on('data', chunk => { serverLog += String(chunk); });

let browser;
const consoleErrors = [];
const consoleTasks = [];
const pageErrors = [];

try {
  const url = `http://127.0.0.1:${port}/render.html`;
  renderLog('Starting local render host');
  await waitForServer(url);
  renderLog('Launching headless browser at 1920×1080');
  browser = await puppeteer.launch({
    executablePath: findChrome(),
    headless: true,
    args: ['--no-sandbox', '--disable-gpu', '--font-render-hinting=none'],
  });
  const page = await browser.newPage();
  await page.setViewport({width: 1920, height: 1080, deviceScaleFactor: 1});
  page.on('console', message => {
    if (message.type() !== 'error') return;
    consoleTasks.push(
      Promise.all(message.args().map(async argument => {
        try {
          const value = await argument.jsonValue();
          return typeof value === 'string' ? value : JSON.stringify(value);
        } catch {
          return argument.toString();
        }
      })).then(parts => consoleErrors.push(parts.filter(Boolean).join(' ') || message.text())),
    );
  });
  const pageFailure = new Promise(resolve => page.on('pageerror', error => {
    pageErrors.push(String(error));
    resolve(error);
  }));
  await page.goto(url, {waitUntil: 'networkidle0', timeout: 60000});
  try {
    await Promise.race([
      page.waitForFunction(() => window.__motionCanvasRobotReady === true, {timeout: 120000}),
      pageFailure.then(error => { throw error; }),
    ]);
  } catch (error) {
    throw new Error(
      `Motion Canvas initialization failed: ${error}; ` +
      `console=${JSON.stringify(consoleErrors)}; page=${JSON.stringify(pageErrors)}`,
    );
  }

  const duration = await page.evaluate(() => window.MotionCanvasRobot.duration());
  if (!Number.isFinite(duration) || duration <= 0) {
    throw new Error(`Invalid animation duration: ${duration}`);
  }
  renderLog(`Scene initialized; duration=${formatDuration(duration)}`);

  const capture = async (time, target) => {
    await page.evaluate(at => window.MotionCanvasRobot.seek(at), time);
    const canvas = await page.$('#robot-canvas');
    if (!canvas) throw new Error('Motion Canvas render surface was not found.');
    await canvas.screenshot({path: target, type: 'png'});
  };

  if (previewMode) {
    const previewFiles = [];
    for (const [index, ratio] of [0, .25, .5, .75, 1].entries()) {
      const target = path.join(
        PREVIEW_ROOT,
        `${String(index).padStart(2, '0')}-${Math.round(ratio * 100)}.png`,
      );
      await capture(duration * ratio, target);
      previewFiles.push(target);
    }
    const first = fs.readFileSync(previewFiles[2]);
    const deterministicTarget = path.join(PREVIEW_ROOT, 'deterministic-repeat.png');
    await capture(duration * .5, deterministicTarget);
    const deterministic = first.equals(fs.readFileSync(deterministicTarget));
    const composites = [];
    for (const [index, file] of previewFiles.entries()) {
      composites.push({
        input: await sharp(file).resize(480, 270).png().toBuffer(),
        left: index * 480,
        top: 0,
      });
    }
    await sharp({
      create: {width: 2400, height: 270, channels: 4, background: '#07111f'},
    }).composite(composites).png().toFile(path.join(PREVIEW_ROOT, 'contact-sheet.png'));
    await Promise.all(consoleTasks);
    fs.writeFileSync(
      path.join(RUN_ROOT, 'validation.json'),
      JSON.stringify({
        status: deterministic && !consoleErrors.length && !pageErrors.length ? 'passed' : 'failed',
        duration,
        sampledTimes: [0, .25, .5, .75, 1].map(ratio => duration * ratio),
        deterministic,
        consoleErrors,
        pageErrors,
      }, null, 2) + '\n',
    );
    if (!deterministic) throw new Error('The 50% frame was not deterministic.');
  }

  if (videoMode) {
    const audio = path.join(RUN_ROOT, 'voiceover.mp3');
    const hasAudioSource = fs.existsSync(audio) && fs.statSync(audio).size > 0;
    fs.rmSync(FRAME_ROOT, {recursive: true, force: true});
    fs.mkdirSync(FRAME_ROOT, {recursive: true});
    const fps = await page.evaluate(() => window.MotionCanvasRobot.fps);
    const frameCount = Math.ceil(duration * fps);
    const totalFrames = frameCount + 1;
    const progressInterval = Math.max(1, Math.min(Math.ceil(totalFrames / 100), fps * 5));
    const renderStarted = Date.now();
    renderLog(
      `Frame rendering started: ${totalFrames.toLocaleString()} frames at ${fps} fps, ` +
      `video duration=${formatDuration(duration)}`,
    );

    for (let frame = 0; frame <= frameCount; frame++) {
      await capture(frame / fps, path.join(FRAME_ROOT, `${String(frame).padStart(6, '0')}.png`));
      const completed = frame + 1;
      if (completed === 1 || completed === totalFrames || completed % progressInterval === 0) {
        const elapsedSeconds = (Date.now() - renderStarted) / 1000;
        const rate = completed / Math.max(elapsedSeconds, .001);
        const remainingSeconds = (totalFrames - completed) / Math.max(rate, .001);
        const percentage = completed / totalFrames * 100;
        renderLog(
          `Frames ${completed.toLocaleString()}/${totalFrames.toLocaleString()} ` +
          `(${percentage.toFixed(1)}%); elapsed=${formatDuration(elapsedSeconds)}; ` +
          `speed=${rate.toFixed(2)} frames/s; ETA=${formatDuration(remainingSeconds)}`,
        );
      }
    }

    const frameElapsed = (Date.now() - renderStarted) / 1000;
    const output = path.join(RUN_ROOT, 'final.mp4');
    const audioOutput = path.join(RUN_ROOT, 'final.with-audio.mp4');
    fs.rmSync(audioOutput, {force: true});
    renderLog(`All frames captured in ${formatDuration(frameElapsed)}; starting H.264 video encoding`);
    const encodeStarted = Date.now();
    const ffmpeg = spawnSync(
      'ffmpeg',
      [
        '-y',
        '-framerate', String(fps),
        '-i', path.join(FRAME_ROOT, '%06d.png'),
        '-c:v', 'libx264',
        '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart',
        output,
      ],
      {encoding: 'utf8'},
    );
    if (ffmpeg.status !== 0) throw new Error(`ffmpeg failed: ${ffmpeg.stderr}`);
    const videoEncodeElapsed = (Date.now() - encodeStarted) / 1000;
    let audioAttached = false;
    let audioMuxSeconds = 0;
    if (hasAudioSource) {
      renderLog('Video encoding completed; attaching voiceover audio');
      const muxStarted = Date.now();
      const mux = spawnSync(
        'ffmpeg',
        [
          '-y',
          '-i', output,
          '-i', audio,
          '-map', '0:v:0',
          '-map', '1:a:0',
          '-c:v', 'copy',
          '-c:a', 'aac',
          '-b:a', '192k',
          '-shortest',
          '-movflags', '+faststart',
          audioOutput,
        ],
        {encoding: 'utf8'},
      );
      audioMuxSeconds = (Date.now() - muxStarted) / 1000;
      if (mux.status === 0) {
        fs.renameSync(audioOutput, output);
        audioAttached = true;
        renderLog(`Voiceover attached in ${formatDuration(audioMuxSeconds)}`);
      } else {
        fs.rmSync(audioOutput, {force: true});
        renderLog(
          `WARNING: Voiceover attachment failed; preserving the completed video-only MP4. ` +
          `${String(mux.stderr || '').trim()}`,
        );
      }
    } else {
      renderLog(
        `WARNING: Voiceover is missing or empty at ${audio}; ` +
        `preserving the completed video-only MP4`,
      );
    }
    const encodeElapsed = (Date.now() - encodeStarted) / 1000;
    const outputSize = fs.statSync(output).size / (1024 * 1024);
    renderLog(
      `Rendering completed in ${formatDuration(encodeElapsed)}; audio=${audioAttached ? 'attached' : 'not attached'}; ` +
      `output=${output}; size=${outputSize.toFixed(1)} MB`,
    );
    process.stdout.write(JSON.stringify({
      status: 'rendered',
      output,
      duration,
      frameCount,
      totalFrames,
      frameRenderSeconds: frameElapsed,
      encodeSeconds: encodeElapsed,
      videoEncodeSeconds: videoEncodeElapsed,
      audioMuxSeconds,
      audioAttached,
    }, null, 2) + '\n');
  } else {
    process.stdout.write(fs.readFileSync(path.join(RUN_ROOT, 'validation.json'), 'utf8'));
  }
} finally {
  if (browser) await browser.close();
  server.kill('SIGTERM');
  if (serverLog && process.env.MOTION_ROBOT_DEBUG) process.stderr.write(serverLog);
}
