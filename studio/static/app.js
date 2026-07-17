const state = {
  dashboard: null,
  runs: [],
  renderQueue: {entries: [], summary: {}},
  selectedTopicRef: null,
  topicDetail: null,
  activeRunId: null,
  activeRun: null,
  selectedChapterId: null,
  selectedBeatId: null,
  pollTimer: null,
  queueTimer: null,
  view: "production"
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
const escapeHtml = (value = "") => String(value).replace(/[&<>'"]/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
const percent = (value, total) => total ? Math.round((Number(value) / Number(total)) * 100) : 0;
const formatNumber = value => Number(value || 0).toLocaleString();
const formatUsd = value => { const number = Number(value || 0); return number >= 1 ? `$${number.toFixed(2)}` : `$${number.toFixed(4)}`; };
const activeStatuses = new Set(["running", "rendering"]);
const motionCanvasSteps = ["Inputs", "Narration", "Voiceover", "Word timing", "Visual reels", "Compile & QA", "Review", "Approval"];
const stepsForRun = () => motionCanvasSteps;
const visibleModelTasks = new Set(["script_structure", "script_writing", "audio_generation", "motion_canvas_batch", "motion_canvas_repair"]);

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options
  });
  let payload = {};
  try { payload = await response.json(); } catch { payload = {}; }
  if (!response.ok) throw new Error(payload.error || response.statusText || "Request failed");
  return payload;
}

function showError(error) {
  const alert = $("#global-error");
  alert.textContent = error?.message || String(error);
  alert.classList.remove("is-hidden");
  toast(alert.textContent, true);
}

function clearError() { $("#global-error").classList.add("is-hidden"); }

function toast(message, isError = false) {
  const element = document.createElement("div");
  element.className = `toast${isError ? " is-error" : ""}`;
  element.textContent = message;
  $("#toast-stack").append(element);
  setTimeout(() => element.remove(), 4200);
}

function setBusy(button, busy, label = "Working…") {
  if (!button) return;
  if (busy) {
    button.dataset.label = button.textContent;
    button.textContent = label;
    button.disabled = true;
  } else {
    button.textContent = button.dataset.label || button.textContent;
    button.disabled = false;
  }
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function statCard(label, value, note, accent = false) {
  return `<article class="stat-card${accent ? " accent" : ""}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong><small>${escapeHtml(note)}</small></article>`;
}

function statusPill(status) {
  return `<span class="status-pill status-${escapeHtml(status)}">${escapeHtml(String(status).replaceAll("_", " "))}</span>`;
}

function artifactLabel(path) {
  return String(path).split("/").pop().replaceAll("_", " ");
}

function artifactUrl(runId, path) {
  return `/artifacts/runs/${encodeURIComponent(runId)}/${String(path).split("/").map(encodeURIComponent).join("/")}`;
}

function chapterPlayerUrl(previewUrl, chapter) {
  if (!previewUrl || !chapter) return null;
  const base = previewUrl.endsWith("/") ? previewUrl : `${previewUrl}/`;
  const params = new URLSearchParams({
    start: String(Number(chapter.absolute_start || 0)),
    end: String(Number(chapter.absolute_end || 0)),
    visualStart: String(Number(chapter.render_absolute_start ?? (chapter.render_start_frame != null ? chapter.render_start_frame / 30 : chapter.absolute_start) ?? 0)),
    visualEnd: String(Number(chapter.render_absolute_end ?? (chapter.render_end_frame != null ? chapter.render_end_frame / 30 : chapter.absolute_end) ?? 0)),
    chapter: chapter.scene_id || ""
  });
  return `${base}chapter-player.html?${params}`;
}

function selectedChapter(run = state.activeRun) {
  const chapters = run?.artifacts?.chapters || [];
  return chapters.find(chapter => chapter.scene_id === state.selectedChapterId) || chapters[0] || null;
}

function selectedBeat(reel) {
  const beats = reel?.beats || [];
  return beats.find(beat => beat.beat_id === state.selectedBeatId) || beats[0] || null;
}

function chapterWorkspaceMarkup(run, working) {
  const artifacts = run.artifacts || {};
  const chapters = artifacts.chapters || [];
  if (!chapters.length) return "";
  const chapter = selectedChapter(run);
  state.selectedChapterId = chapter?.scene_id || null;
  const beat = artifacts.timeline_mode === "immutable_reels" ? selectedBeat(chapter) : chapter;
  state.selectedBeatId = beat?.beat_id || null;
  const playerUrl = chapterPlayerUrl(artifacts.preview_url, beat || chapter);
  return `<details class="chapter-workspace" open>
    <summary>
      <div><p class="eyebrow">Persistent visual timeline</p><h2>Continuous reels with editable narration beats</h2></div>
      <span class="count-chip">${chapters.length} ${artifacts.timeline_mode === "immutable_reels" ? "reels" : artifacts.timeline_mode === "immutable_shots" ? "shots" : "chapters"}</span>
    </summary>
    <div class="chapter-workspace-grid">
      <nav class="chapter-nav" aria-label="Continuous visual reels">${chapters.map((item, index) => `<button type="button" class="chapter-select${item.scene_id === chapter.scene_id ? " is-selected" : ""}" data-chapter-id="${escapeHtml(item.scene_id)}"><span>${String(index + 1).padStart(2, "0")}</span><div><strong>${escapeHtml(item.scene_id)}</strong><small>${Number(item.duration || 0).toFixed(1)}s · ${(item.beats || []).length} beats</small></div><i>${item.source_ready ? "READY" : "MISSING"}</i></button>`).join("")}</nav>
      <section class="chapter-review">
        <header><div><p class="eyebrow">${escapeHtml(chapter.scene_id)} · ${Number(chapter.absolute_start || 0).toFixed(1)}s–${Number(chapter.absolute_end || 0).toFixed(1)}s</p><h3>Continuous reel preview</h3></div>${artifacts.preview_url ? `<a href="${escapeHtml(chapterPlayerUrl(artifacts.preview_url, chapter))}" target="_blank" rel="noreferrer">OPEN REEL ↗</a>` : ""}</header>
        ${chapter.beats?.length ? `<div class="chapter-beat-nav" aria-label="Editable narration beats">${chapter.beats.map((item, index) => `<button type="button" class="beat-select${item.beat_id === beat?.beat_id ? " is-selected" : ""}" data-beat-id="${escapeHtml(item.beat_id)}"><strong>${String(index + 1).padStart(2, "0")}</strong><small>${Number(item.local_start || 0).toFixed(1)}–${Number(item.local_end || 0).toFixed(1)}s</small></button>`).join("")}</div>` : ""}
        ${playerUrl ? `<iframe class="chapter-player-frame" src="${escapeHtml(playerUrl)}" title="${escapeHtml(chapter.scene_id)} live preview" allow="autoplay"></iframe>` : `<div class="chapter-preview-empty"><p>Start the same live Motion Canvas preview used by the full lesson. No MP4 render is required.</p><button class="primary-button start-preview" ${working ? "disabled" : ""}>Start live preview</button></div>`}
        <div class="chapter-audio-row"><div><strong>${beat?.beat_id ? `${escapeHtml(beat.beat_id)} synchronized window` : "Master-timeline audio"}</strong><small>${Number((beat || chapter).duration || 0).toFixed(1)}s · frames ${Number((beat || chapter).render_start_frame ?? 0)}–${Number((beat || chapter).render_end_frame ?? 0)}</small></div><span class="artifact-empty">Audio is synchronized in the live preview above.</span></div>
        <div class="chapter-copy"><strong>${beat?.beat_id ? "Beat narration" : "Narration"}</strong><p>${escapeHtml((beat || chapter).narration || "No timestamped narration is available.")}</p></div>
        <div class="chapter-edit">
          <label for="chapter-edit-instruction"><span>Edit request for ${escapeHtml(beat?.beat_id || chapter.scene_id)}</span><textarea id="chapter-edit-instruction" placeholder="Example: preserve the existing diagram, but make the force change in this beat clearer."></textarea></label>
          <div><button class="danger-button" id="regenerate-motion-chapter" data-chapter-id="${escapeHtml(beat?.beat_id || chapter.scene_id)}" ${working || !chapter.source_ready ? "disabled" : ""}>Regenerate this beat in context</button><small>The parent reel remains continuous. Its clock, master audio, surrounding visual state, and later reels are preserved.</small></div>
        </div>
      </section>
    </div>
  </details>`;
}

function renderChapterWorkspace() {
  const root = $("#chapter-workspace-root");
  if (!root || !state.activeRun) return;
  const working = activeStatuses.has(state.activeRun.status) || state.activeRun.process_active;
  root.innerHTML = chapterWorkspaceMarkup(state.activeRun, working);
}

function selectedTaskModels(run) {
  const overrides = run.settings?.task_models || {};
  return Object.fromEntries((run.model_map?.tasks || []).filter(task => visibleModelTasks.has(task.task)).map(task => {
    if (overrides[task.task]) return [task.task, overrides[task.task]];
    let provider = task.provider;
    if (["script_structure", "script_writing"].includes(task.task)) {
      const requested = run.settings?.model_provider;
      if (requested && requested !== "configured" && task.provider_models?.[requested]) provider = requested;
    }
    if (task.task === "audio_generation") {
      const requested = run.settings?.audio_provider;
      if (requested && task.provider_models?.[requested]) provider = requested;
    }
    return [task.task, { provider, model: task.provider_models?.[provider] || task.model }];
  }));
}

function modelMapMarkup(run, working) {
  const selected = selectedTaskModels(run);
  return `<section class="model-map-panel"><div class="model-map-heading"><div><p class="eyebrow">Prompt routing</p><h3>Models used by Motion Canvas production</h3></div><button class="secondary-button" id="save-model-map" ${working ? "disabled" : ""}>Save model map</button></div><div class="model-map-list">${(run.model_map?.tasks || []).filter(task => visibleModelTasks.has(task.task)).map(task => {
    const current = selected[task.task];
    const providers = Object.keys(task.provider_models || {});
    const prompts = task.prompt_files?.length ? task.prompt_files.join(" · ") : "Voice synthesis (no text prompt file)";
    const modelOptions = task.provider_model_options?.[current.provider] || [task.provider_models[current.provider]];
    const reasoning = current.reasoning_effort || "low";
    return `<article class="model-map-row" data-model-task="${escapeHtml(task.task)}" data-provider-models="${escapeHtml(JSON.stringify(task.provider_models || {}))}" data-provider-model-options="${escapeHtml(JSON.stringify(task.provider_model_options || {}))}"><span class="model-step">STEP ${task.step}</span><div class="model-task-copy"><strong>${escapeHtml(task.label)}</strong><small>${escapeHtml(prompts)}</small></div><select class="task-provider" ${working ? "disabled" : ""}>${providers.map(provider => `<option value="${escapeHtml(provider)}" ${provider === current.provider ? "selected" : ""}>${escapeHtml(provider === "codex" ? "Codex CLI (ChatGPT)" : provider)}</option>`).join("")}</select><select class="task-model" ${working ? "disabled" : ""}>${modelOptions.map(model => `<option value="${escapeHtml(model)}" ${model === current.model ? "selected" : ""}>${escapeHtml(model)}</option>`).join("")}</select><select class="task-reasoning" ${working || current.provider !== "codex" ? "disabled" : ""}>${(task.reasoning_efforts || ["low"]).map(effort => `<option value="${effort}" ${effort === reasoning ? "selected" : ""}>${effort} reasoning</option>`).join("")}</select></article>`;
  }).join("")}</div><p class="model-map-note">Changes are saved to this run and applied on its next execution. Past usage records keep the model that actually produced them.</p></section>`;
}

function costMarkup(artifacts) {
  const summary = artifacts.cost_summary || {};
  const rows = Object.entries(summary.by_task || {}).sort((a,b) => Number(b[1].estimated_cost_usd || 0) - Number(a[1].estimated_cost_usd || 0));
  if (!rows.length) return `<section class="cost-panel"><div class="model-map-heading"><div><p class="eyebrow">Usage ledger</p><h3>Model cost</h3></div></div><p class="artifact-empty">Usage appears after the first completed provider call.</p></section>`;
  return `<section class="cost-panel"><div class="cost-head"><div><p class="eyebrow">Usage ledger</p><h3>Model cost</h3></div><strong>${formatUsd(summary.estimated_cost_usd)}</strong></div><div class="cost-stats"><span><b>${formatNumber(summary.calls ?? summary.priced_records)}</b> calls</span><span><b>${formatNumber(summary.input_tokens)}</b> input</span><span><b>${formatNumber(summary.output_tokens)}</b> output</span><span><b>${formatNumber(summary.cached_input_tokens)}</b> cached</span><span><b>${formatNumber(summary.total_tokens || (Number(summary.input_tokens || 0) + Number(summary.output_tokens || 0)))}</b> total tokens</span></div><div class="cost-task-list">${rows.map(([task,item]) => `<article><div><strong>${escapeHtml(task.replaceAll("_", " "))}</strong><small>${formatNumber(item.calls)} call${Number(item.calls) === 1 ? "" : "s"} · ${formatNumber(Number(item.input_tokens || 0) + Number(item.output_tokens || 0))} tokens</small></div><b>${formatUsd(item.estimated_cost_usd)}</b></article>`).join("")}</div><footer>${formatNumber(summary.priced_records)} priced · ${formatNumber(summary.unpriced_records)} unpriced</footer></section>`;
}

function collectTaskModels() {
  return Object.fromEntries($$("[data-model-task]").map(row => [row.dataset.modelTask, { provider: $(".task-provider", row).value, model: $(".task-model", row).value, ...($(".task-provider", row).value === "codex" ? {reasoning_effort: $(".task-reasoning", row).value} : {}) }]));
}

async function boot() {
  clearError();
  try {
    const [dashboard, runsPayload, queuePayload] = await Promise.all([
      request("/api/dashboard"), request("/api/runs"), request("/api/render-queue")
    ]);
    state.dashboard = dashboard;
    state.runs = runsPayload.runs || [];
    state.renderQueue = await hydrateRenderQueueLogs(queuePayload.queue || {entries: [], summary: {}});
    state.selectedTopicRef = state.selectedTopicRef || dashboard.next_topic?.ref || dashboard.topics?.[0]?.ref;
    renderChrome();
    renderDashboard();
    renderCurriculum();
    renderRuns();
    manageQueuePolling();
    if (state.selectedTopicRef) await selectTopic(state.selectedTopicRef, false);
    if (state.activeRunId) await selectRun(state.activeRunId, false);
  } catch (error) { showError(error); }
}

function renderChrome() {
  $("#run-count").textContent = state.runs.length;
  const providerLabels = { gemini: "Gemini", elevenlabs: "ElevenLabs", zai: "Z.AI", moonshot: "Moonshot" };
  $("#provider-dots").innerHTML = Object.entries(state.dashboard.providers || {}).map(([key, ready]) =>
    `<span class="provider-dot${ready ? " is-ready" : ""}">${escapeHtml(providerLabels[key] || key)} ${ready ? "●" : "○"}</span>`
  ).join("");
}

function renderDashboard() {
  const summary = state.dashboard.summary;
  $("#summary-stats").innerHTML = [
    statCard("Syllabus coverage", `${summary.covered_objectives}/${summary.objective_count}`, `${percent(summary.covered_objectives, summary.objective_count)}% objectives covered`, true),
    statCard("Completed topics", `${summary.complete_topics}/${summary.topic_count}`, "Prerequisite-aware order"),
    statCard("Motion Canvas", "3.17.2", "Pinned deterministic renderer"),
    statCard("Published videos", summary.video_count, "Approved lesson outputs")
  ].join("");
  $("#topic-count").textContent = `${summary.topic_count} topics`;
  renderTopicList();
}

function renderTopicList() {
  const query = ($("#topic-search")?.value || "").trim().toLowerCase();
  const topics = state.dashboard.topics.filter(topic => `${topic.ref} ${topic.title} ${topic.domain_title}`.toLowerCase().includes(query));
  $("#topic-list").innerHTML = topics.map(topic => {
    const progress = percent(topic.covered, topic.total);
    return `<button class="topic-item${state.selectedTopicRef === topic.ref ? " is-selected" : ""}" data-topic="${escapeHtml(topic.ref)}">
      <span class="topic-number">${escapeHtml(topic.ref)}</span>
      <span class="topic-copy"><strong>${escapeHtml(topic.title)}</strong><small>${escapeHtml(topic.domain_title)} · ${topic.facts_ready ? "packet ready" : "not prepared"}</small></span>
      <span><span class="mini-progress"><i style="width:${progress}%"></i></span><span class="topic-progress-label">${topic.covered}/${topic.total}</span></span>
    </button>`;
  }).join("") || `<div class="loading-card">No matching topic.</div>`;
}

async function selectTopic(topicRef, rerenderList = true, syncActiveRun = true) {
  state.selectedTopicRef = topicRef;
  if (rerenderList) renderTopicList();
  $("#topic-detail").innerHTML = `<div class="loading-card">Loading ${escapeHtml(topicRef)}…</div>`;
  try {
    state.topicDetail = await request(`/api/topics/${encodeURIComponent(topicRef)}`);
    renderTopicDetail();
    const topicRuns = state.topicDetail.runs || [];
    if (syncActiveRun && state.activeRun?.topic_ref !== topicRef) {
      if (topicRuns[0]) {
        await selectRun(topicRuns[0].id, false);
      } else {
        state.activeRunId = null;
        state.activeRun = null;
        managePolling();
        renderPipeline();
      }
    }
  } catch (error) { showError(error); }
}

function evidenceChips(items, fallback = "No classified pattern") {
  if (!items?.length) return `<span class="data-chip">${escapeHtml(fallback)}</span>`;
  return items.slice(0, 6).map(item => `<span class="data-chip">${escapeHtml(item.label)} <b>${item.count}</b></span>`).join("");
}

function renderTopicDetail() {
  const { topic, objectives, assessment, facts } = state.topicDetail;
  const runDefault = `physics-${topic.ref.replaceAll(".", "-")}-v01`;
  $("#topic-detail").innerHTML = `
    <div class="topic-hero">
      <div><span class="topic-kicker">TOPIC ${escapeHtml(topic.ref)} · ${escapeHtml(topic.domain_title)}</span><h2>${escapeHtml(topic.title)}</h2><p>${topic.core} Core and ${topic.supplement} Supplement objectives. The lesson packet uses syllabus statements plus private aggregate assessment patterns, while all examples and diagrams remain original.</p></div>
      <div class="topic-score"><strong>${topic.covered}/${topic.total}</strong><span>objectives covered</span></div>
    </div>
    <div class="detail-grid">
      <section class="subsection">
        <div class="subsection-heading"><h3>Learning objectives</h3><span>${objectives.length} objectives</span></div>
        <div class="objective-list">${objectives.map(objective => `<article class="objective-row">
          <span class="route-chip ${objective.route}">${objective.route === "supplement" ? "Supp" : "Core"}</span>
          <p><b>${escapeHtml(objective.objective_id)}</b> · ${escapeHtml(objective.objective_text)}</p>
          ${statusPill(objective.status)}
        </article>`).join("")}</div>
      </section>
      <section class="subsection evidence-block">
        <div class="subsection-heading"><h3>Assessment intelligence</h3><span>aggregate only</span></div>
        <div class="evidence-stat"><span>Classified questions</span><strong>${assessment.question_count}</strong></div>
        <div class="evidence-stat"><span>Questions with visuals</span><strong>${assessment.visual_count}</strong></div>
        <div><p class="eyebrow">Command words</p><div class="chip-row">${evidenceChips(assessment.command_words)}</div></div>
        <div><p class="eyebrow">Question types</p><div class="chip-row">${evidenceChips(assessment.question_types)}</div></div>
      </section>
    </div>
    <div class="production-form">
      <p class="model-map-note">These settings apply to the next new run. To change an existing run, use its active-run controls and model map below.</p>
      <div class="form-grid">
        <label class="field"><span>Run ID</span><input id="run-id-input" value="${escapeHtml(runDefault)}"></label>
        <label class="field"><span>Duration</span><select id="duration-input"><option value="300">5 minutes</option><option value="480" selected>8 minutes</option><option value="600">10 minutes</option><option value="720">12 minutes</option></select></label>
        <label class="field"><span>Script generator / model</span><select id="model-provider"><option value="gemini">Gemini</option><option value="anthropic">Claude</option><optgroup label="Codex CLI (ChatGPT)"><option value="codex:gpt-5.6-sol">GPT-5.6-Sol</option><option value="codex:gpt-5.6-terra">GPT-5.6-Terra</option><option value="codex:gpt-5.6-luna">GPT-5.6-Luna</option><option value="codex:gpt-5.5">GPT-5.5</option><option value="codex:gpt-5.4">GPT-5.4</option><option value="codex:gpt-5.4-mini">GPT-5.4-Mini</option></optgroup><option value="configured">Configured</option></select></label>
        <label class="field"><span>Script reasoning</span><select id="script-reasoning" disabled><option>low</option><option>medium</option><option selected>high</option><option>xhigh</option><option>max</option><option>ultra</option></select></label>
        <label class="field"><span>Voice</span><select id="audio-provider"><option value="gemini">Gemini TTS</option><option value="elevenlabs">ElevenLabs</option></select></label>
        <label class="field"><span>Visual reel generator</span><select id="chapter-provider"><option value="moonshot">Kimi K2.7 Code</option><option value="codex">Codex CLI (ChatGPT)</option></select></label>
        <label class="field"><span>Codex model</span><select id="codex-model" disabled><option value="gpt-5.6-sol">GPT-5.6-Sol</option><option value="gpt-5.6-terra">GPT-5.6-Terra</option><option value="gpt-5.6-luna">GPT-5.6-Luna</option><option value="gpt-5.5">GPT-5.5</option><option value="gpt-5.4">GPT-5.4</option><option value="gpt-5.4-mini">GPT-5.4-Mini</option></select></label>
        <label class="field"><span>Chapter reasoning</span><select id="chapter-reasoning" disabled><option>low</option><option>medium</option><option selected>high</option><option>xhigh</option><option>max</option><option>ultra</option></select></label>
        <label class="field"><span>Chapter workers</span><select id="scene-concurrency"><option>1</option><option selected>2</option><option>4</option></select></label>
      </div>
      <div class="form-actions">
        <label class="paid-check"><input type="checkbox" id="paid-confirm" checked disabled> Paid model and voice APIs authorized for this run</label>
        <div class="button-row">
          <button class="secondary-button" id="prepare-topic-button">${facts ? "Rebuild packet" : "Prepare lesson packet"}</button>
          <button class="secondary-button" id="create-run-button">Create run</button>
          <span class="flow-note">Create the run, then execute and verify one numbered step at a time below.</span>
        </div>
      </div>
    </div>`;
}

function renderPipeline() {
  const run = state.activeRun;
  const root = $("#pipeline-panel");
  if (!run) {
    root.innerHTML = `<div class="empty-pipeline"><span class="empty-orbit">◎</span><h3>No active production run</h3><p>Create a run for the selected syllabus topic.</p></div>`;
    return;
  }
  const working = activeStatuses.has(run.status) || run.process_active;
  const artifacts = run.artifacts || {};
  const completed = Number(run.current_step || 0);
  const steps = stepsForRun(run);
  root.innerHTML = `
    <div class="run-header">
      <div><p class="eyebrow">Active Motion Canvas production · ${statusPill(run.status)}</p><h2>${escapeHtml(run.topic)}</h2><span class="run-id">${escapeHtml(run.id)} · NARRATION-DRIVEN CHAPTERS</span><small class="run-settings-summary">${Number(run.settings?.duration || 480) / 60} min · script ${escapeHtml(run.settings?.model_provider || "configured")} · voice ${escapeHtml(run.settings?.audio_provider || "configured")} · paid confirmation ${run.settings?.confirm_paid_api ? "enabled" : "required"}</small></div>
      <div class="run-header-actions">
        <button class="secondary-button" id="run-refresh">Refresh</button>
        <button class="danger-button" id="run-stop" ${working ? "" : "disabled"}>Stop</button>
        <button class="danger-button" id="run-delete" ${working ? "disabled" : ""}>Delete run</button>
        <button class="secondary-button" id="run-next" ${working || completed >= 8 ? "disabled" : ""}>Run next</button>
        <button class="primary-button" id="run-all" ${working ? "disabled" : ""}>Run to QA</button>
        <button class="secondary-button" id="render-button" ${working || completed < 7 ? "disabled" : ""}>Render MP4</button>
      </div>
    </div>
    <div class="stepper">${steps.map((name, index) => {
      const number = index + 1;
      return `<button class="step${completed >= number ? " is-done" : ""}${working && completed + 1 === number ? " is-current" : ""}" data-step="${number}" ${working ? "disabled" : ""}><span>${completed >= number ? "✓" : number}</span><b>${name}</b></button>`;
    }).join("")}</div>
    <div class="run-workspace">
      <div class="preview-shell"><div class="preview-toolbar"><span>LIVE MOTION CANVAS · PRE-RENDER VIDEO + SYNCHRONIZED VOICEOVER</span>${artifacts.preview_url ? `<a href="${escapeHtml(artifacts.preview_url)}" target="_blank" rel="noreferrer">OPEN EDITOR ↗</a>` : "LOCAL EDITOR PREVIEW"}</div>${artifacts.preview_url ? `<iframe class="preview-frame editor-preview" src="${escapeHtml(artifacts.preview_url)}" title="Motion Canvas lesson preview" allow="autoplay"></iframe>` : `<div class="preview-placeholder preview-launch"><span>Start the live Motion Canvas player to review animation and voiceover immediately. Rendering is not required.</span><button class="primary-button start-preview" ${working || completed < 6 ? "disabled" : ""}>Start live preview</button></div>`}</div>
      <div class="run-side">
        <div class="run-control-card"><h3>Run or regenerate a stage</h3><div class="step-control"><select id="step-select">${steps.map((name,index) => `<option value="${index+1}">${index+1}. ${name}</option>`).join("")}</select><button class="secondary-button" id="run-step" ${working ? "disabled" : ""}>Run selected step</button><button class="danger-button" id="regenerate-step" ${working ? "disabled" : ""}>Regenerate from step</button></div><label class="paid-check" style="margin-top:9px"><input type="checkbox" id="run-paid-confirm" checked disabled> Paid model and voice APIs authorized</label><p class="control-help">Regenerate removes the selected stage and every downstream artifact before starting that stage again.</p></div>
        <div class="run-control-card"><h3>Generated artifacts</h3>${artifacts.validation_preview_url ? `<a class="validation-evidence-link" href="${escapeHtml(artifacts.validation_preview_url)}" target="_blank" rel="noreferrer">Open deterministic contact sheet ↗</a>` : ""}<div class="artifact-list">${artifacts.files?.length ? artifacts.files.map(path => `<a href="${artifactUrl(run.id, path)}" target="_blank" title="${escapeHtml(path)}"><span>${escapeHtml(artifactLabel(path))}</span><small>${escapeHtml(path)}</small><b>OPEN ↗</b></a>`).join("") : `<p class="artifact-empty">Artifacts appear after each completed stage.</p>`}</div></div>
        <pre class="log-box" id="run-log">Loading logs…</pre>
        ${artifacts.mp4_url ? `<a class="primary-button" href="${escapeHtml(artifacts.mp4_url)}" target="_blank">Open rendered MP4 ↗</a>` : ""}
        ${run.error ? `<div class="alert">${escapeHtml(run.error)}</div>` : ""}
      </div>
    </div>
    <div class="run-intelligence">${modelMapMarkup(run, working)}${costMarkup(artifacts)}</div>
    <div id="chapter-workspace-root">${chapterWorkspaceMarkup(run, working)}</div>`;
  loadLogs(run.id);
  managePolling();
}

async function selectRun(runId, switchView = true) {
  clearError();
  try {
    const payload = await request(`/api/runs/${encodeURIComponent(runId)}`);
    if (state.activeRunId !== runId) state.selectedChapterId = null;
    state.activeRunId = runId;
    state.activeRun = payload.run;
    renderPipeline();
    if (switchView) {
      switchViewTo("production");
      if (state.activeRun.topic_ref && state.selectedTopicRef !== state.activeRun.topic_ref) await selectTopic(state.activeRun.topic_ref, true, false);
      window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
    }
  } catch (error) { showError(error); }
}

async function loadLogs(runId) {
  try {
    const payload = await request(`/api/runs/${encodeURIComponent(runId)}/logs`);
    const box = $("#run-log");
    if (box) { box.textContent = payload.log || "No process output yet."; box.scrollTop = box.scrollHeight; }
  } catch { /* The active run refresh will surface meaningful errors. */ }
}

function managePolling() {
  clearInterval(state.pollTimer);
  state.pollTimer = null;
  if (!state.activeRun || !activeStatuses.has(state.activeRun.status)) return;
  state.pollTimer = setInterval(async () => {
    if (!state.activeRunId) return;
    try {
      const payload = await request(`/api/runs/${encodeURIComponent(state.activeRunId)}`);
      state.activeRun = payload.run;
      renderPipeline();
      if (!activeStatuses.has(state.activeRun.status)) {
        clearInterval(state.pollTimer); state.pollTimer = null;
        await refreshRuns();
      }
    } catch (error) { clearInterval(state.pollTimer); showError(error); }
  }, 1800);
}

function renderCurriculum() {
  const summary = state.dashboard.summary;
  $("#curriculum-stats").innerHTML = [
    statCard("Covered", summary.status_counts.covered, "Final curriculum state", true),
    statCard("In production", ["planned","scripted","rendered","reviewed"].reduce((sum,key) => sum + summary.status_counts[key],0), "Planned through reviewed"),
    statCard("Needs revision", summary.status_counts.needs_revision, "Returned to production"),
    statCard("Uncovered", summary.status_counts.uncovered, "Remaining objectives")
  ].join("");
  $("#domain-grid").innerHTML = state.dashboard.domains.map(domain => `<article class="domain-card"><header><h3>${escapeHtml(domain.ref)} · ${escapeHtml(domain.title)}</h3><span>${domain.covered}/${domain.objectives}</span></header><div class="large-progress"><i style="width:${percent(domain.covered, domain.objectives)}%"></i></div><footer>${domain.topics} topics · ${percent(domain.covered, domain.objectives)}% covered</footer></article>`).join("");
  $("#curriculum-table").innerHTML = state.dashboard.topics.map(topic => `<article class="curriculum-row"><strong>${escapeHtml(topic.ref)}</strong><div><strong>${escapeHtml(topic.title)}</strong><small>${escapeHtml(topic.domain_title)}</small></div><div><span class="mini-progress"><i style="width:${percent(topic.covered,topic.total)}%"></i></span><small>${topic.covered}/${topic.total} covered</small></div><select class="status-select topic-status-select" data-status-topic="${escapeHtml(topic.ref)}"><option value="">Set status…</option>${["planned","scripted","rendered","reviewed","covered","needs_revision"].map(status => `<option value="${status}">${status.replaceAll("_"," ")}</option>`).join("")}</select></article>`).join("");
}

function renderRuns() {
  $("#runs-table").innerHTML = state.runs.map(run => {
    const ready = Number(run.current_step || 0) >= 7 && !activeStatuses.has(run.status);
    return `<article class="run-row-table"><input type="checkbox" class="render-run-select" value="${escapeHtml(run.id)}" ${ready ? "" : "disabled"} aria-label="Select ${escapeHtml(run.id)} for rendering"><div><strong>${escapeHtml(run.topic)}</strong><small>${escapeHtml(run.id)}</small></div>${statusPill(run.status)}<span>Step ${run.current_step || 0}/8</span><span>${formatDate(run.updated_at)}</span><button class="secondary-button run-open" data-run="${escapeHtml(run.id)}">Open</button></article>`;
  }).join("") || `<div class="loading-card">No production runs yet.</div>`;
  const entries = state.renderQueue?.entries || [];
  $("#render-queue-strip").innerHTML = entries.length
    ? entries.slice(-12).map(item => renderQueueItem(item)).join("")
    : `<span class="artifact-empty">Render queue is empty. Select completed runs below and queue them together.</span>`;
}

function renderQueueItem(item) {
  const running = item.status === "running";
  const lines = String(item.live_log || "").split(/\r?\n/).filter(Boolean);
  const renderStart = lines.map((line, index) => line.includes("Starting queued render:") ? index : -1).filter(index => index >= 0).pop();
  const currentRenderLines = renderStart == null ? lines : lines.slice(renderStart);
  const recentLines = currentRenderLines.filter(line => line.includes("[render]")).slice(-8);
  const progressLine = [...recentLines].reverse().find(line => line.includes("[render] Frames ")) || "";
  const match = progressLine.match(/Frames\s+([\d,]+)\/([\d,]+)\s+\(([\d.]+)%\);.*?speed=([\d.]+) frames\/s; ETA=([^\]]+)$/);
  let progress = "";
  if (match) {
    const completed = Number(match[1].replaceAll(",", ""));
    const total = Number(match[2].replaceAll(",", ""));
    const percentage = Number(match[3]);
    const remaining = Math.max(0, total - completed);
    progress = `<div class="render-live-progress"><div class="render-progress-track"><i style="width:${Math.max(0, Math.min(100, percentage))}%"></i></div><div class="render-progress-stats"><strong>${formatNumber(completed)} / ${formatNumber(total)} frames</strong><span>${formatNumber(remaining)} left</span><span>${percentage.toFixed(1)}%</span><span>${escapeHtml(match[4])} fps</span><span>ETA ${escapeHtml(match[5])}</span></div></div>`;
  }
  const liveOutput = running
    ? `<pre class="render-live-log">${escapeHtml(recentLines.join("\n") || "Waiting for the renderer to report its first frame…")}</pre>`
    : "";
  return `<article class="render-queue-item${running ? " is-running" : ""}"><div class="render-queue-heading"><strong>${escapeHtml(item.run_id)}</strong><small>${escapeHtml(item.status)} · ${escapeHtml(item.settings?.quality || "standard")} · ${Number(item.settings?.fps || 30)} fps</small></div>${progress}${liveOutput}${item.error ? `<small>${escapeHtml(item.error)}</small>` : ""}</article>`;
}

async function hydrateRenderQueueLogs(queue) {
  const running = (queue?.entries || []).filter(item => item.status === "running");
  await Promise.all(running.map(async item => {
    try {
      const payload = await request(`/api/runs/${encodeURIComponent(item.run_id)}/logs`);
      item.live_log = payload.log || "";
    } catch { item.live_log = ""; }
  }));
  return queue;
}

async function refreshRuns() {
  const [payload, queuePayload] = await Promise.all([request("/api/runs"), request("/api/render-queue")]);
  state.runs = payload.runs || [];
  state.renderQueue = await hydrateRenderQueueLogs(queuePayload.queue || {entries: [], summary: {}});
  renderRuns(); renderChrome();
  manageQueuePolling();
}

function manageQueuePolling() {
  const queueActive = (state.renderQueue.entries || []).some(item => ["queued", "running"].includes(item.status));
  if (queueActive && !state.queueTimer) {
    state.queueTimer = setInterval(async () => {
      try {
        const [runsPayload, nextQueue] = await Promise.all([request("/api/runs"), request("/api/render-queue")]);
        state.runs = runsPayload.runs || [];
        state.renderQueue = await hydrateRenderQueueLogs(nextQueue.queue || {entries: [], summary: {}});
        renderRuns();
        if (!(state.renderQueue.entries || []).some(item => ["queued", "running"].includes(item.status))) {
          clearInterval(state.queueTimer); state.queueTimer = null;
        }
      } catch { /* Normal active-run polling will surface server errors. */ }
    }, 2500);
  } else if (!queueActive && state.queueTimer) {
    clearInterval(state.queueTimer); state.queueTimer = null;
  }
}

function switchViewTo(view) {
  state.view = view;
  $$(".nav-item").forEach(item => item.classList.toggle("is-active", item.dataset.view === view));
  $$(".view").forEach(item => item.classList.toggle("is-active", item.id === `view-${view}`));
  const titles = { production: ["Motion Canvas lesson engine", "Production workspace"], curriculum: ["Coverage control", "Curriculum map"], runs: ["Production history", "Runs and outputs"] };
  $("#view-eyebrow").textContent = titles[view][0]; $("#view-title").textContent = titles[view][1];
  history.replaceState(null, "", `#${view}`);
}

function productionPayload(execute) {
  const chapterProvider = $("#chapter-provider").value;
  const scriptSelection = $("#model-provider").value;
  const scriptProvider = scriptSelection.startsWith("codex:") ? "codex" : scriptSelection;
  const scriptModel = scriptProvider === "codex" ? scriptSelection.split(":", 2)[1] : null;
  const taskModels = {
    motion_canvas_batch: {
      provider: chapterProvider,
      model: chapterProvider === "codex" ? $("#codex-model").value : "kimi-k2.7-code",
      ...(chapterProvider === "codex" ? {reasoning_effort: $("#chapter-reasoning").value} : {})
    },
    motion_canvas_repair: {provider: "codex", model: $("#codex-model").value, reasoning_effort: "high"}
  };
  if (scriptProvider === "codex") {
    for (const task of ["script_structure", "script_writing"]) taskModels[task] = {provider: "codex", model: scriptModel, reasoning_effort: $("#script-reasoning").value};
  }
  return {
    topic_ref: state.selectedTopicRef,
    run_id: $("#run-id-input").value.trim(),
    duration: Number($("#duration-input").value),
    model_provider: $("#model-provider").value,
    audio_provider: $("#audio-provider").value,
    animation_mode: "motion-canvas",
    scene_concurrency: Number($("#scene-concurrency").value),
    task_models: taskModels,
    confirm_paid_api: $("#paid-confirm").checked,
    execute
  };
}

async function prepareTopic(button) {
  setBusy(button, true, "Preparing…"); clearError();
  try {
    const payload = await request(`/api/topics/${encodeURIComponent(state.selectedTopicRef)}/prepare`, { method: "POST", body: JSON.stringify({ force: Boolean(state.topicDetail.facts) }) });
    state.topicDetail = payload.detail; renderTopicDetail(); toast("Grounded lesson packet prepared.");
  } catch (error) { showError(error); } finally { setBusy(button, false); }
}

async function createProductionRun(button, execute) {
  const payload = productionPayload(execute);
  if (execute && !payload.confirm_paid_api) return showError(new Error("Confirm paid APIs before starting full generation."));
  setBusy(button, true, execute ? "Starting…" : "Creating…"); clearError();
  try {
    const response = await request("/api/runs", { method: "POST", body: JSON.stringify(payload) });
    state.activeRun = response.run; state.activeRunId = response.run.id;
    await refreshRuns(); renderPipeline(); toast(execute ? "Full lesson generation started." : "Production run created.");
    window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
  } catch (error) { showError(error); } finally { setBusy(button, false); }
}

async function executeActive(payload, message) {
  if (!state.activeRunId) return;
  payload.confirm_paid_api = $("#run-paid-confirm")?.checked ?? true;
  clearError();
  try {
    const response = await request(`/api/runs/${encodeURIComponent(state.activeRunId)}/execute`, { method: "POST", body: JSON.stringify(payload) });
    state.activeRun = response.run; renderPipeline(); toast(message);
  } catch (error) { showError(error); }
}

async function updateCoverage(select) {
  if (!select.value) return;
  clearError(); select.disabled = true;
  try {
    await request(`/api/topics/${encodeURIComponent(select.dataset.statusTopic)}/status`, { method: "POST", body: JSON.stringify({ status: select.value }) });
    toast(`${select.dataset.statusTopic} marked ${select.value.replaceAll("_", " ")}.`);
    await boot();
  } catch (error) { showError(error); } finally { select.disabled = false; }
}

document.addEventListener("click", async event => {
  const nav = event.target.closest(".nav-item"); if (nav) return switchViewTo(nav.dataset.view);
  const topic = event.target.closest(".topic-item"); if (topic) return selectTopic(topic.dataset.topic);
  const runOpen = event.target.closest(".run-open"); if (runOpen) return selectRun(runOpen.dataset.run);
  if (event.target.closest("#refresh-button")) return boot();
  if (event.target.closest("#runs-refresh")) return refreshRuns();
  if (event.target.closest("#queue-selected-renders")) {
    const runIds = $$(".render-run-select:checked").map(input => input.value);
    if (!runIds.length) return showError(new Error("Select at least one completed run to render."));
    try {
      const response = await request("/api/render-queue", {
        method: "POST",
        body: JSON.stringify({run_ids: runIds, quality: "high", fps: 30, workers: 1})
      });
      state.renderQueue = await hydrateRenderQueueLogs(response.queue);
      renderRuns();
      manageQueuePolling();
      toast(`${runIds.length} run${runIds.length === 1 ? "" : "s"} added to the MP4 render queue.`);
    } catch (error) { showError(error); }
    return;
  }
  if (event.target.closest("#prepare-topic-button")) return prepareTopic(event.target.closest("button"));
  if (event.target.closest("#create-run-button")) return createProductionRun(event.target.closest("button"), false);
  if (event.target.closest("#run-refresh")) return selectRun(state.activeRunId, false);
  if (event.target.closest("#save-model-map")) {
    try {
      const response = await request(`/api/runs/${encodeURIComponent(state.activeRunId)}/models`, { method: "POST", body: JSON.stringify({ task_models: collectTaskModels() }) });
      state.activeRun = response.run; renderPipeline(); toast("Prompt/model map saved for this run.");
    } catch (error) { showError(error); }
    return;
  }
  if (event.target.closest("#run-stop")) {
    try { const response = await request(`/api/runs/${encodeURIComponent(state.activeRunId)}/stop`, { method: "POST", body: "{}" }); state.activeRun = response.run; renderPipeline(); toast("Stop requested."); } catch (error) { showError(error); }
    return;
  }
  if (event.target.closest("#run-delete")) {
    if (!window.confirm(`Delete run ${state.activeRunId} and all of its generated assets? This cannot be undone.`)) return;
    try {
      await request(`/api/runs/${encodeURIComponent(state.activeRunId)}`, { method: "DELETE" });
      state.activeRun = null; state.activeRunId = null; renderPipeline(); await refreshRuns();
      if (state.selectedTopicRef) await selectTopic(state.selectedTopicRef, true, false);
      toast("Run and generated assets deleted.");
    } catch (error) { showError(error); }
    return;
  }
  if (event.target.closest("#run-next")) {
    const next = Math.min(8, Number(state.activeRun.current_step || 0) + 1);
    return executeActive({ from_step: next, stop_after_step: next, confirm_paid_api: $("#run-paid-confirm")?.checked, task_models: collectTaskModels() }, `Step ${next} started.`);
  }
  const stepButton = event.target.closest(".step[data-step]");
  if (stepButton) {
    const selected = Number(stepButton.dataset.step);
    return executeActive({ from_step: selected, stop_after_step: selected, confirm_paid_api: $("#run-paid-confirm")?.checked, task_models: collectTaskModels() }, `Step ${selected} started.`);
  }
  if (event.target.closest("#run-all")) {
    const next = Math.max(1, Number(state.activeRun.current_step || 0) + 1);
    return executeActive({ from_step: next, stop_after_step: 8, confirm_paid_api: $("#run-paid-confirm")?.checked, task_models: collectTaskModels() }, "Pipeline resumed through QA.");
  }
  if (event.target.closest("#run-step")) {
    const selected = Number($("#step-select").value);
    return executeActive({ from_step: selected, stop_after_step: selected, confirm_paid_api: $("#run-paid-confirm")?.checked, task_models: collectTaskModels() }, `Step ${selected} started.`);
  }
  if (event.target.closest("#regenerate-step")) {
    const selected = Number($("#step-select").value);
    if (!window.confirm(`Regenerate from step ${selected}? The selected stage and every later artifact will be removed.`)) return;
    try {
      // Capture the user's current selections before reset_run re-renders the
      // model map from the previously saved run metadata.
      const taskModels = collectTaskModels();
      const reset = await request(`/api/runs/${encodeURIComponent(state.activeRunId)}/reset`, { method: "POST", body: JSON.stringify({ step: selected }) });
      state.activeRun = reset.run; renderPipeline();
      return executeActive({ from_step: selected, stop_after_step: selected, task_models: taskModels }, `Step ${selected} regeneration started.`);
    } catch (error) { showError(error); }
    return;
  }
  if (event.target.closest("#render-button")) {
    try { const response = await request(`/api/runs/${encodeURIComponent(state.activeRunId)}/render`, { method: "POST", body: JSON.stringify({ quality: "high", fps: 30, workers: 1 }) }); state.activeRun = response.run; renderPipeline(); await refreshRuns(); toast("High-quality MP4 added to the render queue. Existing frames will be resumed when available."); } catch (error) { showError(error); }
    return;
  }
  if (event.target.closest(".start-preview")) {
    const button = event.target.closest("button"); setBusy(button, true, "Starting player…");
    try {
      const response = await request(`/api/runs/${encodeURIComponent(state.activeRunId)}/preview`, { method: "POST", body: "{}" });
      state.activeRun = response.run; renderPipeline(); toast("Motion Canvas video preview started. Press play in the embedded player.");
    } catch (error) { showError(error); setBusy(button, false); }
    return;
  }
  const chapterSelect = event.target.closest(".chapter-select");
  if (chapterSelect) {
    state.selectedChapterId = chapterSelect.dataset.chapterId;
    state.selectedBeatId = null;
    renderChapterWorkspace();
    return;
  }
  const beatSelect = event.target.closest(".beat-select");
  if (beatSelect) {
    state.selectedBeatId = beatSelect.dataset.beatId;
    renderChapterWorkspace();
    return;
  }
  if (event.target.closest("#regenerate-motion-chapter")) {
    const button = event.target.closest("button");
    const chapterId = button.dataset.chapterId;
    const instruction = $("#chapter-edit-instruction")?.value.trim() || "";
    if (!window.confirm(`Regenerate ${chapterId} inside its continuous reel? The reel clock, audio, and surrounding visual state will remain fixed.`)) return;
    setBusy(button, true, "Starting…");
    try {
      const endpoint = chapterId.startsWith("beat_") ? "motion-beats" : "motion-shots";
      const response = await request(`/api/runs/${encodeURIComponent(state.activeRunId)}/${endpoint}/${encodeURIComponent(chapterId)}/regenerate`, {
        method: "POST",
        body: JSON.stringify({ confirm_paid_api: true, custom_instruction: instruction, task_models: collectTaskModels() })
      });
      state.activeRun = response.run;
      renderPipeline();
      toast(`${chapterId} regeneration started inside its persistent reel. The master timeline and audio are locked.`);
    } catch (error) {
      showError(error);
      setBusy(button, false);
    }
    return;
  }
});

document.addEventListener("input", event => {
  if (event.target.id === "topic-search") renderTopicList();
});
document.addEventListener("change", event => {
  if (event.target.classList.contains("topic-status-select")) updateCoverage(event.target);
  if (event.target.id === "chapter-provider") {
    $("#codex-model").disabled = event.target.value !== "codex";
    $("#chapter-reasoning").disabled = event.target.value !== "codex";
  }
  if (event.target.id === "model-provider") {
    $("#script-reasoning").disabled = !event.target.value.startsWith("codex:");
  }
  if (event.target.classList.contains("task-provider")) {
    const row = event.target.closest("[data-model-task]");
    const models = JSON.parse(row.dataset.providerModels || "{}");
    const options = JSON.parse(row.dataset.providerModelOptions || "{}");
    const available = options[event.target.value] || [models[event.target.value]];
    $(".task-model", row).innerHTML = available.map(model => `<option value="${escapeHtml(model)}">${escapeHtml(model)}</option>`).join("");
    $(".task-reasoning", row).disabled = event.target.value !== "codex";
  }
});

const initialView = location.hash.replace("#", "");
if (["production", "curriculum", "runs"].includes(initialView)) switchViewTo(initialView);
boot();
