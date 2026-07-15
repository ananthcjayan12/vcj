import fs from "node:fs";
import http from "node:http";
import path from "node:path";
import { pathToFileURL } from "node:url";
import puppeteer from "puppeteer-core";
import sharp from "sharp";

const [masterArg, outputArg, repoArg, chromeArg] = process.argv.slice(2);
if (!masterArg || !outputArg || !repoArg || !chromeArg) {
  throw new Error("Usage: browser-inspector.mjs MASTER OUTPUT_DIR REPO_ROOT CHROME_PATH");
}
const masterPath = path.resolve(masterArg);
const outputRoot = path.resolve(outputArg);
const repoRoot = path.resolve(repoArg);
const chapterIndex = JSON.parse(fs.readFileSync(path.join(path.dirname(masterPath), "chapter_index.json"), "utf8"));
fs.mkdirSync(outputRoot, { recursive: true });

const mime = new Map([
  [".html", "text/html; charset=utf-8"], [".js", "text/javascript; charset=utf-8"], [".mjs", "text/javascript; charset=utf-8"],
  [".css", "text/css; charset=utf-8"], [".json", "application/json"], [".svg", "image/svg+xml"],
  [".png", "image/png"], [".woff2", "font/woff2"], [".woff", "font/woff"], [".mp3", "audio/mpeg"],
]);
const server = http.createServer((request, response) => {
  const requested = decodeURIComponent(new URL(request.url, "http://127.0.0.1").pathname).replace(/^\/+/, "");
  const candidate = path.resolve(repoRoot, requested || "index.html");
  if (!candidate.startsWith(repoRoot + path.sep) || !fs.existsSync(candidate) || !fs.statSync(candidate).isFile()) {
    response.writeHead(404); response.end("Not found"); return;
  }
  response.writeHead(200, { "content-type": mime.get(path.extname(candidate).toLowerCase()) || "application/octet-stream", "cache-control": "no-store" });
  fs.createReadStream(candidate).pipe(response);
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const port = server.address().port;
const relativeMaster = path.relative(repoRoot, masterPath).split(path.sep).map(encodeURIComponent).join("/");
const origin = `http://127.0.0.1:${port}`;

const browser = await puppeteer.launch({ executablePath: chromeArg, headless: true, args: ["--no-sandbox", "--disable-gpu", "--font-render-hinting=none"] });
const page = await browser.newPage();
await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
const consoleErrors = [];
const pageErrors = [];
const blockedRequests = [];
const failedRequests = [];
page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
page.on("pageerror", (error) => pageErrors.push(String(error)));
page.on("requestfailed", (request) => {
  const failure = request.failure();
  failedRequests.push({ url: request.url(), error: failure ? failure.errorText : "failed" });
});
await page.setRequestInterception(true);
page.on("request", (request) => {
  const url = request.url();
  if (url.startsWith(origin) || url.startsWith("data:") || url.startsWith("blob:")) request.continue();
  else { blockedRequests.push(url); request.abort("blockedbyclient"); }
});
await page.goto(`${origin}/${relativeMaster}?inspect=1`, { waitUntil: "networkidle0", timeout: 60_000 });
await page.waitForFunction(() => window.__directHTMLReady === true, { timeout: 20_000 });
await page.evaluate(() => document.fonts.ready);

function intersect(a, b) {
  const width = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));
  const height = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
  return width * height;
}
const chapterReports = [];
const contactFrames = [];
for (const chapter of chapterIndex.chapters) {
  const chapterDir = path.join(outputRoot, chapter.chapter_id);
  fs.mkdirSync(chapterDir, { recursive: true });
  const duration = chapter.end - chapter.start;
  const denseTimes = Array.from({ length: 9 }, (_, index) => chapter.start + 0.05 + (Math.max(0.1, duration - 0.1) * index / 8));
  const samples = [];
  for (const time of denseTimes) {
    samples.push(await page.evaluate((at) => window.DirectHTMLProbe.snapshot(at), time));
  }
  const peak = samples.reduce((best, item) => item.active_objects > best.active_objects ? item : best, samples[0]);
  const captureTimes = [
    { label: "start", time: chapter.start + 0.05 },
    { label: "peak", time: peak.time },
    { label: "end", time: Math.max(chapter.start + 0.05, chapter.end - 0.05) },
  ];
  for (const capture of captureTimes) {
    await page.evaluate((at) => window.lessonPlayer.seek(at), capture.time);
    const target = path.join(chapterDir, `${capture.label}.png`);
    await page.screenshot({ path: target, type: "png" });
    contactFrames.push(target);
  }

  const allImportant = samples.flatMap((item) => item.important);
  const minText = Math.min(...allImportant.filter((item) => ["text", "div", "span", "p"].includes(String(item.tag).toLowerCase())).map((item) => item.font_size).filter((value) => Number.isFinite(value)), Infinity);
  const overflow = allImportant.filter((item) => item.left < 100 || item.top < 100 || item.right > 1820 || item.bottom > 980);
  const lowContrastSamples = allImportant.filter((item) => ["text", "div", "span", "p"].includes(String(item.tag).toLowerCase()) && Number.isFinite(item.contrast_ratio) && item.contrast_ratio < 4.5);
  const lowContrast = Array.from(new Map(lowContrastSamples.map((item) => [item.id || `${item.tag}:${item.text}`, item])).values());
  const peakImportant = peak.important;
  const overlapPairs = [];
  for (let left = 0; left < peakImportant.length; left += 1) {
    for (let right = left + 1; right < peakImportant.length; right += 1) {
      if (String(peakImportant[left].tag).toLowerCase() !== "text" || String(peakImportant[right].tag).toLowerCase() !== "text") continue;
      const area = intersect(peakImportant[left], peakImportant[right]);
      if (area > 400) overlapPairs.push([peakImportant[left].id, peakImportant[right].id, area]);
    }
  }

  const motionTimes = [];
  for (let time = chapter.start + 0.05; time < chapter.end - 0.05; time += 1) motionTimes.push(time);
  const signatures = [];
  for (const time of motionTimes) {
    const state = await page.evaluate((at) => window.DirectHTMLProbe.snapshot(at), time);
    signatures.push({ time, signature: JSON.stringify(state.important.map((item) => [item.id, Math.round(item.left), Math.round(item.top), Math.round(item.right), Math.round(item.bottom), Math.round(item.opacity * 100), item.transform, item.stroke_dashoffset, item.text])) });
  }
  const frozenIntervals = [];
  let holdStart = null;
  for (let index = 1; index < signatures.length; index += 1) {
    if (signatures[index].signature === signatures[index - 1].signature && holdStart === null) holdStart = signatures[index - 1].time;
    else {
      if (holdStart !== null && signatures[index - 1].time - holdStart >= 5) frozenIntervals.push([holdStart, signatures[index - 1].time]);
      holdStart = null;
    }
  }
  const finalSignature = signatures.length ? signatures[signatures.length - 1] : null;
  if (holdStart !== null && finalSignature && finalSignature.time - holdStart >= 5) frozenIntervals.push([holdStart, finalSignature.time]);

  await page.evaluate((at) => window.lessonPlayer.seek(at), peak.time);
  const first = await page.screenshot({ type: "png" });
  await page.evaluate(() => window.lessonPlayer.seek(0));
  await page.evaluate((at) => window.lessonPlayer.seek(at), peak.time);
  const second = await page.screenshot({ type: "png" });
  const deterministicSeek = Buffer.compare(first, second) === 0;
  const report = {
    chapter_id: chapter.chapter_id,
    start: chapter.start,
    end: chapter.end,
    peak_time: peak.time,
    active_object_peak: Math.max(...samples.map((item) => item.active_objects)),
    accent_color_peak: Math.max(...samples.map((item) => item.accent_colors.length)),
    accent_colors_by_sample: samples.map((item) => ({ time: item.time, colors: item.accent_colors })),
    minimum_text_px: Number.isFinite(minText) ? minText : null,
    low_contrast_elements: lowContrast,
    overflow_elements: overflow,
    overlap_pairs: overlapPairs,
    blank_frames: samples.filter((item) => item.important.length === 0).map((item) => item.time),
    frozen_intervals: frozenIntervals,
    deterministic_seek: deterministicSeek,
  };
  fs.writeFileSync(path.join(chapterDir, "metrics.json"), JSON.stringify(report, null, 2) + "\n");
  chapterReports.push(report);
}

if (contactFrames.length) {
  const thumbWidth = 480, thumbHeight = 270, columns = 3;
  const rows = Math.ceil(contactFrames.length / columns);
  const composites = [];
  for (let index = 0; index < contactFrames.length; index += 1) {
    const input = await sharp(contactFrames[index]).resize(thumbWidth, thumbHeight).png().toBuffer();
    composites.push({ input, left: (index % columns) * thumbWidth, top: Math.floor(index / columns) * thumbHeight });
  }
  await sharp({ create: { width: columns * thumbWidth, height: rows * thumbHeight, channels: 4, background: "#07131F" } }).composite(composites).png().toFile(path.join(outputRoot, "contact_sheet.png"));
}

const report = {
  status: "passed",
  console_errors: consoleErrors,
  page_errors: pageErrors,
  blocked_requests: blockedRequests,
  failed_requests: failedRequests.filter((item) => !(item.error === "net::ERR_ABORTED" && /\.(?:mp3|wav)(?:\?|$)/i.test(item.url))),
  chapters: chapterReports,
};
const hasFailures = consoleErrors.length || pageErrors.length || blockedRequests.length || report.failed_requests.length || chapterReports.some((item) =>
  item.active_object_peak > 8 || item.minimum_text_px !== null && item.minimum_text_px < 30 || item.low_contrast_elements.length || item.overflow_elements.length || item.blank_frames.length || item.frozen_intervals.length || !item.deterministic_seek
);
report.status = hasFailures ? "failed" : "passed";
fs.writeFileSync(path.join(outputRoot, "initial_report.json"), JSON.stringify(report, null, 2) + "\n");
await browser.close();
await new Promise((resolve) => server.close(resolve));
process.stdout.write(JSON.stringify(report));
