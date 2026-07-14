const state = {
  dashboard: null,
  assets: [],
  runs: [],
  selectedTopicRef: null,
  topicDetail: null,
  activeRunId: null,
  activeRun: null,
  pollTimer: null,
  view: "production"
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
const escapeHtml = (value = "") => String(value).replace(/[&<>'"]/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
const percent = (value, total) => total ? Math.round((Number(value) / Number(total)) * 100) : 0;
const activeStatuses = new Set(["running", "rendering"]);
const steps = ["Inputs", "Script", "Audio", "Timing", "Scenes", "Validate", "Preview", "QA"];

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

async function boot() {
  clearError();
  try {
    const [dashboard, assetsPayload, runsPayload] = await Promise.all([
      request("/api/dashboard"), request("/api/assets"), request("/api/runs")
    ]);
    state.dashboard = dashboard;
    state.assets = assetsPayload.scenes || [];
    state.runs = runsPayload.runs || [];
    state.selectedTopicRef = state.selectedTopicRef || dashboard.next_topic?.ref || dashboard.topics?.[0]?.ref;
    renderChrome();
    renderDashboard();
    renderCurriculum();
    renderAssets();
    renderRuns();
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
    statCard("Animation scenes", summary.scene_count, "Validated reusable modules"),
    statCard("Published videos", summary.video_count, "Manual publishing registry")
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

async function selectTopic(topicRef, rerenderList = true) {
  state.selectedTopicRef = topicRef;
  if (rerenderList) renderTopicList();
  $("#topic-detail").innerHTML = `<div class="loading-card">Loading ${escapeHtml(topicRef)}…</div>`;
  try {
    state.topicDetail = await request(`/api/topics/${encodeURIComponent(topicRef)}`);
    renderTopicDetail();
    const topicRuns = state.topicDetail.runs || [];
    if (!state.activeRunId && topicRuns[0]) await selectRun(topicRuns[0].id, false);
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
      <div class="form-grid">
        <label class="field"><span>Run ID</span><input id="run-id-input" value="${escapeHtml(runDefault)}"></label>
        <label class="field"><span>Duration</span><select id="duration-input"><option value="300">5 minutes</option><option value="480" selected>8 minutes</option><option value="600">10 minutes</option><option value="720">12 minutes</option></select></label>
        <label class="field"><span>Script model</span><select id="model-provider"><option value="gemini">Gemini</option><option value="anthropic">Claude</option><option value="configured">Configured</option></select></label>
        <label class="field"><span>Voice</span><select id="audio-provider"><option value="gemini">Gemini TTS</option><option value="elevenlabs">ElevenLabs</option></select></label>
        <label class="field"><span>Scene workers</span><select id="scene-concurrency"><option>1</option><option>2</option><option>4</option></select></label>
      </div>
      <div class="form-actions">
        <label class="paid-check"><input type="checkbox" id="paid-confirm"> I confirm this run may call paid model and voice APIs</label>
        <div class="button-row">
          <button class="secondary-button" id="prepare-topic-button">${facts ? "Rebuild packet" : "Prepare lesson packet"}</button>
          <button class="secondary-button" id="create-run-button">Create run</button>
          <button class="primary-button" id="generate-run-button">Generate full lesson</button>
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
  root.innerHTML = `
    <div class="run-header">
      <div><p class="eyebrow">Active production · ${statusPill(run.status)}</p><h2>${escapeHtml(run.topic)}</h2><span class="run-id">${escapeHtml(run.id)}</span></div>
      <div class="run-header-actions">
        <button class="secondary-button" id="run-refresh">Refresh</button>
        <button class="danger-button" id="run-stop" ${working ? "" : "disabled"}>Stop</button>
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
      <div class="preview-shell"><div class="preview-toolbar"><span>V3 COMPOSITION PREVIEW</span>${artifacts.preview_url ? `<a href="${escapeHtml(artifacts.preview_url)}" target="_blank">OPEN ↗</a>` : "WAITING FOR STEP 7"}</div>${artifacts.preview_url ? `<iframe class="preview-frame" src="${escapeHtml(artifacts.preview_url)}" title="Video preview"></iframe>` : `<div class="preview-placeholder">Preview becomes available after step 7.</div>`}</div>
      <div class="run-side">
        <div class="run-control-card"><h3>Resume a specific stage</h3><div class="step-control"><select id="step-select">${steps.map((name,index) => `<option value="${index+1}">${index+1}. ${name}</option>`).join("")}</select><button class="secondary-button" id="run-step" ${working ? "disabled" : ""}>Run selected step</button></div><label class="paid-check" style="margin-top:9px"><input type="checkbox" id="run-paid-confirm" ${run.settings?.confirm_paid_api ? "checked" : ""}> Confirm paid APIs when required</label></div>
        <pre class="log-box" id="run-log">Loading logs…</pre>
        ${artifacts.mp4_url ? `<a class="primary-button" href="${escapeHtml(artifacts.mp4_url)}" target="_blank">Open rendered MP4 ↗</a>` : ""}
        ${run.error ? `<div class="alert">${escapeHtml(run.error)}</div>` : ""}
      </div>
    </div>
    ${artifacts.scenes?.length ? `<div class="panel-heading compact"><div><p class="eyebrow">Scene surgery</p><h2>Regenerate one weak scene</h2></div><span class="count-chip">${artifacts.scenes.length} scenes</span></div><div class="scene-list">${artifacts.scenes.map(scene => `<article class="scene-row"><strong>${escapeHtml(scene.id)}<br><small>${Number(scene.duration || 0).toFixed(1)}s</small></strong><p>${escapeHtml(scene.narration_text || scene.beat_label || "Scene")}</p><input class="scene-note" data-scene-note="${escapeHtml(scene.id)}" placeholder="Director note for this scene"><button class="secondary-button scene-regenerate" data-scene="${escapeHtml(scene.id)}" ${working ? "disabled" : ""}>Regenerate</button></article>`).join("")}</div>` : ""}`;
  loadLogs(run.id);
  managePolling();
}

async function selectRun(runId, switchView = true) {
  clearError();
  try {
    const payload = await request(`/api/runs/${encodeURIComponent(runId)}`);
    state.activeRunId = runId;
    state.activeRun = payload.run;
    renderPipeline();
    if (switchView) {
      switchViewTo("production");
      if (state.activeRun.topic_ref && state.selectedTopicRef !== state.activeRun.topic_ref) await selectTopic(state.activeRun.topic_ref);
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

function renderAssets() {
  const categorySelect = $("#asset-category");
  const selectedCategory = categorySelect.value;
  const categories = [...new Set(state.assets.map(asset => asset.category))].sort();
  categorySelect.innerHTML = `<option value="">All categories</option>${categories.map(category => `<option value="${escapeHtml(category)}" ${category === selectedCategory ? "selected" : ""}>${escapeHtml(category)}</option>`).join("")}`;
  const query = ($("#asset-search")?.value || "").trim().toLowerCase();
  const assets = state.assets.filter(asset => (!categorySelect.value || asset.category === categorySelect.value) && `${asset.scene} ${asset.description} ${asset.category}`.toLowerCase().includes(query));
  $("#asset-grid").innerHTML = assets.map(asset => `<article class="asset-card"><span class="asset-icon">${asset.category === "mathematics" ? "∑" : asset.category === "graphs" ? "⌁" : asset.category === "electricity" ? "⚡" : "◇"}</span><h3>${escapeHtml(asset.scene)}</h3><p>${escapeHtml(asset.description)}</p><footer><span>${escapeHtml(asset.category)}</span><span>${asset.parameter_schema ? "schema ready" : "registered"}</span></footer></article>`).join("") || `<div class="loading-card">No matching scenes.</div>`;
}

function renderRuns() {
  $("#runs-table").innerHTML = state.runs.map(run => `<article class="run-row-table"><div><strong>${escapeHtml(run.topic)}</strong><small>${escapeHtml(run.id)}</small></div>${statusPill(run.status)}<span>Step ${run.current_step || 0}/8</span><span>${formatDate(run.updated_at)}</span><button class="secondary-button run-open" data-run="${escapeHtml(run.id)}">Open</button></article>`).join("") || `<div class="loading-card">No production runs yet.</div>`;
}

async function refreshRuns() {
  const payload = await request("/api/runs");
  state.runs = payload.runs || [];
  renderRuns(); renderChrome();
}

function switchViewTo(view) {
  state.view = view;
  $$(".nav-item").forEach(item => item.classList.toggle("is-active", item.dataset.view === view));
  $$(".view").forEach(item => item.classList.toggle("is-active", item.id === `view-${view}`));
  const titles = { production: ["Manual lesson engine", "Production workspace"], curriculum: ["Coverage control", "Curriculum map"], assets: ["Visual vocabulary", "Scene library"], runs: ["Production history", "Runs and outputs"] };
  $("#view-eyebrow").textContent = titles[view][0]; $("#view-title").textContent = titles[view][1];
  history.replaceState(null, "", `#${view}`);
}

function productionPayload(execute) {
  return {
    topic_ref: state.selectedTopicRef,
    run_id: $("#run-id-input").value.trim(),
    duration: Number($("#duration-input").value),
    model_provider: $("#model-provider").value,
    audio_provider: $("#audio-provider").value,
    scene_concurrency: Number($("#scene-concurrency").value),
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
  if (event.target.closest("#prepare-topic-button")) return prepareTopic(event.target.closest("button"));
  if (event.target.closest("#create-run-button")) return createProductionRun(event.target.closest("button"), false);
  if (event.target.closest("#generate-run-button")) return createProductionRun(event.target.closest("button"), true);
  if (event.target.closest("#run-refresh")) return selectRun(state.activeRunId, false);
  if (event.target.closest("#run-stop")) {
    try { const response = await request(`/api/runs/${encodeURIComponent(state.activeRunId)}/stop`, { method: "POST", body: "{}" }); state.activeRun = response.run; renderPipeline(); toast("Stop requested."); } catch (error) { showError(error); }
    return;
  }
  if (event.target.closest("#run-next")) {
    const next = Math.min(8, Number(state.activeRun.current_step || 0) + 1);
    return executeActive({ from_step: next, stop_after_step: next, confirm_paid_api: $("#run-paid-confirm")?.checked }, `Step ${next} started.`);
  }
  if (event.target.closest("#run-all")) {
    const next = Math.max(1, Number(state.activeRun.current_step || 0) + 1);
    return executeActive({ from_step: next, stop_after_step: 8, confirm_paid_api: $("#run-paid-confirm")?.checked }, "Pipeline resumed through QA.");
  }
  if (event.target.closest("#run-step")) {
    const selected = Number($("#step-select").value);
    return executeActive({ from_step: selected, stop_after_step: selected, confirm_paid_api: $("#run-paid-confirm")?.checked, force_paid_api: [2,3,5].includes(selected) }, `Step ${selected} started.`);
  }
  if (event.target.closest("#render-button")) {
    try { const response = await request(`/api/runs/${encodeURIComponent(state.activeRunId)}/render`, { method: "POST", body: JSON.stringify({ quality: "high", fps: 30, workers: 1 }) }); state.activeRun = response.run; renderPipeline(); toast("High-quality MP4 render started."); } catch (error) { showError(error); }
    return;
  }
  const sceneButton = event.target.closest(".scene-regenerate");
  if (sceneButton) {
    const sceneId = sceneButton.dataset.scene;
    const note = $(`[data-scene-note="${sceneId}"]`)?.value || "";
    if (!$("#run-paid-confirm")?.checked) return showError(new Error("Confirm paid APIs before regenerating a scene."));
    try { const response = await request(`/api/runs/${encodeURIComponent(state.activeRunId)}/scenes/${encodeURIComponent(sceneId)}/regenerate`, { method: "POST", body: JSON.stringify({ confirm_paid_api: true, custom_instruction: note }) }); state.activeRun = response.run; renderPipeline(); toast(`${sceneId} regeneration started.`); } catch (error) { showError(error); }
  }
});

document.addEventListener("input", event => {
  if (event.target.id === "topic-search") renderTopicList();
  if (event.target.id === "asset-search") renderAssets();
});
document.addEventListener("change", event => {
  if (event.target.id === "asset-category") renderAssets();
  if (event.target.classList.contains("topic-status-select")) updateCoverage(event.target);
});

const initialView = location.hash.replace("#", "");
if (["production", "curriculum", "assets", "runs"].includes(initialView)) switchViewTo(initialView);
boot();
