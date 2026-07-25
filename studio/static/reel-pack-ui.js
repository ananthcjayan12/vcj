(() => {
  const PRODUCT = 'topic-reel-pack';
  const ACTIVE = new Set(['running', 'rendering']);
  const PACK_STEPS = ['Inputs', 'Plan & scripts', 'Independent audio', 'Word timing', 'Portrait visuals', 'Compile & preview', 'Pack screening', 'Export MP4s'];
  const MODEL_TASKS = new Set(['script_structure', 'script_writing', 'audio_generation', 'motion_canvas_batch', 'motion_canvas_repair', 'motion_canvas_lesson_screen']);
  let activePackId = '';
  let activeRequest = null;
  let pollTimer = null;
  let lastSignature = '';

  const escapeHtml = (value = '') => String(value).replace(/[&<>'"]/g, character => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'}[character]));
  const artifactUrl = (runId, relative) => `/artifacts/runs/${encodeURIComponent(runId)}/${String(relative).split('/').map(encodeURIComponent).join('/')}`;
  const statusPill = status => `<span class="pack-status pack-status-${escapeHtml(status || 'unknown')}">${escapeHtml(String(status || 'unknown').replaceAll('_', ' '))}</span>`;

  async function request(path, options = {}) {
    const response = await fetch(path, {headers: {'Content-Type': 'application/json', ...(options.headers || {})}, ...options});
    let payload = {};
    try { payload = await response.json(); } catch { payload = {}; }
    if (!response.ok) throw new Error(payload.error || response.statusText || 'Request failed');
    return payload;
  }

  function ensureStyles() {
    if (document.getElementById('reel-pack-ui-styles')) return;
    const style = document.createElement('style');
    style.id = 'reel-pack-ui-styles';
    style.textContent = `
      .pack-product-field select{font-weight:750}.pack-only-field.is-hidden,.lesson-only-field.is-hidden{display:none!important}
      .reel-pack-workspace{display:grid;gap:18px}.reel-pack-header{display:flex;justify-content:space-between;gap:22px;align-items:flex-start;padding:22px;border:1px solid rgba(70,217,255,.22);border-radius:20px;background:linear-gradient(145deg,rgba(14,29,49,.98),rgba(7,17,31,.98))}.reel-pack-header h2{margin:4px 0 5px}.reel-pack-header-actions{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}.reel-pack-subtitle{color:#91a8c5}.pack-stepper{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:7px}.pack-step{border:1px solid rgba(145,168,197,.16);background:rgba(14,29,49,.8);color:#91a8c5;border-radius:12px;padding:10px 7px;text-align:left;cursor:pointer}.pack-step span{display:grid;place-items:center;width:24px;height:24px;border-radius:50%;background:rgba(255,255,255,.06);font-weight:800;margin-bottom:6px}.pack-step b{font-size:11px}.pack-step.is-done{color:#eaf3ff;border-color:rgba(70,217,255,.3)}.pack-step.is-done span{background:rgba(70,217,255,.16);color:#46d9ff}.pack-step:disabled{cursor:not-allowed;opacity:.65}
      .pack-summary{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px}.pack-summary article{padding:14px;border-radius:15px;background:rgba(14,29,49,.86);border:1px solid rgba(145,168,197,.12)}.pack-summary span{display:block;color:#91a8c5;font-size:12px}.pack-summary strong{display:block;font-size:25px;color:#eaf3ff;margin-top:5px}
      .pack-review{padding:17px;border-radius:17px;background:rgba(14,29,49,.86);border:1px solid rgba(255,200,87,.18)}.pack-section-head{display:flex;justify-content:space-between;align-items:center;gap:14px;margin-bottom:12px}.pack-section-head h3{margin:2px 0}.pack-review-links{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0}.pack-review-links a{padding:7px 10px;border-radius:9px;background:rgba(70,217,255,.08)}.pack-findings{display:grid;gap:8px}.pack-finding{display:grid;grid-template-columns:130px 1fr 70px;gap:12px;padding:11px;border-radius:12px;background:rgba(255,255,255,.035)}.pack-finding p{margin:3px 0}.pack-finding small{color:#91a8c5}.pack-finding>strong:last-child{text-align:right;color:#46d9ff}
      .pack-model-panel{padding:17px;border-radius:17px;background:rgba(14,29,49,.86);border:1px solid rgba(145,168,197,.12)}.pack-model-list{display:grid;gap:8px}.pack-model-row{display:grid;grid-template-columns:115px minmax(180px,1fr) 160px 210px 135px;gap:9px;align-items:center;padding:10px;border-radius:12px;background:rgba(255,255,255,.03)}.pack-model-row small{display:block;color:#91a8c5}.pack-model-row select{min-width:0}
      .pack-reels{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:13px}.pack-reel-card{display:flex;flex-direction:column;min-width:0;border:1px solid rgba(145,168,197,.14);border-radius:17px;background:rgba(14,29,49,.88);overflow:hidden}.pack-reel-preview{position:relative;aspect-ratio:9/16;background:#07111f;display:grid;place-items:center;overflow:hidden}.pack-reel-preview img,.pack-reel-preview iframe{width:100%;height:100%;border:0;display:block}.pack-reel-preview img{object-fit:cover}.pack-reel-preview span{padding:20px;text-align:center;color:#91a8c5}.pack-preview-evidence{position:absolute;top:10px;right:10px;padding:5px 7px;border-radius:8px;background:rgba(5,12,22,.9);color:#91a8c5;font-size:10px;font-weight:800;letter-spacing:.04em;text-transform:uppercase}.pack-reel-preview .pack-script-review{position:absolute;left:10px;right:10px;bottom:10px;background:rgba(5,12,22,.9);backdrop-filter:blur(8px)}.pack-reel-body{display:grid;gap:9px;padding:14px;flex:1}.pack-reel-head{display:flex;justify-content:space-between;gap:9px;align-items:flex-start}.pack-reel-head h4{margin:2px 0;font-size:16px}.pack-reel-meta{display:flex;gap:8px;flex-wrap:wrap;color:#91a8c5;font-size:12px}.pack-reel-copy{margin:0;color:#cbd9ea;font-size:13px;line-height:1.45}.pack-reel-findings{padding:9px;border-radius:10px;background:rgba(255,107,107,.07);color:#ffadad;font-size:12px}.pack-reel-actions{display:flex;gap:7px;flex-wrap:wrap;margin-top:auto}.pack-reel-actions button,.pack-reel-actions a{font-size:11px;padding:7px 9px}.pack-log{max-height:210px;overflow:auto;padding:13px;border-radius:13px;background:#050c16;color:#91a8c5;font-size:11px;white-space:pre-wrap}.pack-script-dialog{width:min(760px,calc(100vw - 30px));max-height:85vh;padding:0;border:1px solid rgba(70,217,255,.35);border-radius:18px;background:#0b192a;color:#eaf3ff;box-shadow:0 30px 100px rgba(0,0,0,.55)}.pack-script-dialog::backdrop{background:rgba(0,0,0,.72)}.pack-script-dialog-content{padding:22px;overflow:auto;max-height:72vh}.pack-script-dialog h3{margin:3px 0 5px}.pack-script-dialog p{line-height:1.55;color:#cbd9ea}.pack-script-dialog .pack-script-label{color:#46d9ff;text-transform:uppercase;font-size:10px;letter-spacing:.08em;font-weight:800;margin:14px 0 3px}.pack-script-dialog-actions{display:flex;justify-content:flex-end;padding:12px 22px;border-top:1px solid rgba(145,168,197,.14)}.pack-status{display:inline-flex;align-items:center;padding:5px 8px;border-radius:999px;font-size:10px;font-weight:850;text-transform:uppercase;letter-spacing:.05em;background:rgba(145,168,197,.11);color:#b9c8d9}.pack-status-approved,.pack-status-rendered,.pack-status-complete,.pack-status-passed{background:rgba(52,211,153,.12);color:#6ee7b7}.pack-status-rejected{background:rgba(255,107,107,.12);color:#ff9a9a}.pack-status-flagged,.pack-status-failed,.pack-status-needs-review{background:rgba(255,107,107,.12);color:#ff9a9a}.pack-status-repaired-pending-review{background:rgba(255,200,87,.12);color:#ffc857}.pack-status-visual-ready,.pack-status-timed,.pack-status-audio-ready,.pack-status-scripted{background:rgba(70,217,255,.1);color:#46d9ff}
      @media(max-width:1200px){.pack-reels{grid-template-columns:repeat(2,minmax(0,1fr))}.pack-model-row{grid-template-columns:100px 1fr 140px 180px}.pack-model-row .pack-reasoning{grid-column:4}.pack-summary{grid-template-columns:repeat(3,1fr)}}@media(max-width:800px){.reel-pack-header{display:grid}.reel-pack-header-actions{justify-content:flex-start}.pack-stepper{grid-template-columns:repeat(4,1fr)}.pack-reels{grid-template-columns:1fr}.pack-summary{grid-template-columns:repeat(2,1fr)}.pack-model-row,.pack-finding{grid-template-columns:1fr}.pack-finding>strong:last-child{text-align:left}}
    `;
    document.head.append(style);
  }

  function addProductControls() {
    const formGrid = document.querySelector('#topic-detail .production-form .form-grid');
    const runInput = document.getElementById('run-id-input');
    if (!formGrid || !runInput) return;
    let productSelect = document.getElementById('content-product-select');
    if (productSelect?.dataset.reelPackBound === 'true') return;
    runInput.dataset.lessonDefault ||= runInput.value;
    if (!productSelect) {
      const product = document.createElement('label');
      product.className = 'field pack-product-field';
      product.innerHTML = `<span>Content product</span><select id="content-product-select"><option value="full-lesson">Full lesson video</option><option value="${PRODUCT}">Independent Reels</option></select>`;
      formGrid.prepend(product);
      productSelect = product.querySelector('select');
    }
    productSelect.addEventListener('change', applyProductFormState);
    productSelect.dataset.reelPackBound = 'true';
    applyProductFormState();
  }

  function applyProductFormState() {
    const isPack = document.getElementById('content-product-select')?.value === PRODUCT;
    document.querySelectorAll('.pack-only-field').forEach(element => element.classList.toggle('is-hidden', !isPack));
    document.querySelectorAll('.lesson-only-field').forEach(element => element.classList.toggle('is-hidden', isPack));
    const runInput = document.getElementById('run-id-input');
    if (runInput) {
      const lessonDefault = runInput.dataset.lessonDefault || runInput.value;
      if (isPack && !runInput.value.includes('-reels-')) runInput.value = lessonDefault.replace(/-v(\d+)$/, '-reels-v$1');
      if (!isPack && runInput.value.includes('-reels-')) runInput.value = lessonDefault;
    }
    const button = document.getElementById('create-run-button');
    if (button) button.textContent = isPack ? 'Create Reel pack' : 'Create run';
  }

  function topicTaskModels() {
    const chapterProvider = document.getElementById('chapter-provider')?.value || 'moonshot';
    const scriptSelection = document.getElementById('model-provider')?.value || 'gemini';
    const scriptProvider = scriptSelection.startsWith('codex:') ? 'codex' : scriptSelection;
    const scriptModel = scriptProvider === 'codex' ? scriptSelection.split(':', 2)[1] : null;
    const taskModels = {
      motion_canvas_batch: {
        provider: chapterProvider,
        model: chapterProvider === 'codex' ? document.getElementById('codex-model')?.value : chapterProvider === 'grok' ? document.getElementById('grok-model')?.value : 'kimi-k2.7-code',
        ...(['codex', 'grok'].includes(chapterProvider) ? {reasoning_effort: document.getElementById('chapter-reasoning')?.value || 'high'} : {}),
      },
      motion_canvas_repair: chapterProvider === 'grok'
        ? {provider: 'grok', model: document.getElementById('grok-model')?.value || 'grok-4.5', reasoning_effort: 'high'}
        : {provider: 'codex', model: document.getElementById('codex-model')?.value || 'gpt-5.6-sol', reasoning_effort: 'high'},
    };
    if (scriptProvider === 'codex') {
      for (const task of ['script_structure', 'script_writing']) taskModels[task] = {provider: 'codex', model: scriptModel, reasoning_effort: document.getElementById('script-reasoning')?.value || 'high'};
    }
    return taskModels;
  }

  function packCreationPayload() {
    const scriptSelection = document.getElementById('model-provider')?.value || 'gemini';
    return {
      content_product: PRODUCT,
      topic_ref: document.querySelector('.topic-item.is-selected')?.dataset.topic || '',
      run_id: document.getElementById('run-id-input')?.value.trim() || '',
      reel_count: Number(document.getElementById('reel-count-input')?.value || 5),
      duration: Number(document.getElementById('reel-duration-input')?.value || 35),
      model_provider: scriptSelection.startsWith('codex:') ? 'configured' : scriptSelection,
      audio_provider: document.getElementById('audio-provider')?.value || 'gemini',
      scene_concurrency: Number(document.getElementById('scene-concurrency')?.value || 2),
      task_models: topicTaskModels(),
      confirm_paid_api: true,
      execute: false,
    };
  }

  function selectedTaskModels(run) {
    const overrides = run.settings?.task_models || {};
    return Object.fromEntries((run.model_map?.tasks || []).filter(task => MODEL_TASKS.has(task.task)).map(task => {
      if (overrides[task.task]) return [task.task, overrides[task.task]];
      let provider = task.provider;
      if (['script_structure', 'script_writing'].includes(task.task)) {
        const requested = run.settings?.model_provider;
        if (requested && requested !== 'configured' && task.provider_models?.[requested]) provider = requested;
      }
      if (task.task === 'audio_generation') {
        const requested = run.settings?.audio_provider;
        if (requested && task.provider_models?.[requested]) provider = requested;
      }
      return [task.task, {provider, model: task.provider_models?.[provider] || task.model}];
    }));
  }

  function modelMapMarkup(run, working) {
    const selected = selectedTaskModels(run);
    const rows = (run.model_map?.tasks || []).filter(task => MODEL_TASKS.has(task.task)).map(task => {
      const current = selected[task.task] || {provider: task.provider, model: task.model};
      const providers = Object.keys(task.provider_models || {});
      const options = task.provider_model_options?.[current.provider] || [task.provider_models?.[current.provider] || current.model];
      const reasoning = current.reasoning_effort || 'low';
      const efforts = current.provider === 'grok' ? ['low', 'medium', 'high'] : (task.reasoning_efforts || ['low']);
      return `<article class="pack-model-row" data-pack-model-task="${escapeHtml(task.task)}" data-provider-models="${escapeHtml(JSON.stringify(task.provider_models || {}))}" data-provider-options="${escapeHtml(JSON.stringify(task.provider_model_options || {}))}"><span>${task.step ? `STEP ${task.step}` : 'OPTIONAL'}</span><div><strong>${escapeHtml(task.label)}</strong><small>${escapeHtml((task.prompt_files || []).join(' · ') || 'Voice synthesis')}</small></div><select class="pack-provider" ${working ? 'disabled' : ''}>${providers.map(provider => `<option value="${escapeHtml(provider)}" ${provider === current.provider ? 'selected' : ''}>${escapeHtml(provider)}</option>`).join('')}</select><select class="pack-model" ${working ? 'disabled' : ''}>${options.filter(Boolean).map(model => `<option value="${escapeHtml(model)}" ${model === current.model ? 'selected' : ''}>${escapeHtml(model)}</option>`).join('')}</select><select class="pack-reasoning" ${working || !['codex', 'grok'].includes(current.provider) ? 'disabled' : ''}>${efforts.map(effort => `<option value="${effort}" ${effort === reasoning ? 'selected' : ''}>${effort}</option>`).join('')}</select></article>`;
    }).join('');
    return `<section class="pack-model-panel"><div class="pack-section-head"><div><p class="eyebrow">Prompt routing</p><h3>Reel-pack models</h3></div><button class="secondary-button" id="pack-save-models" ${working ? 'disabled' : ''}>Save model map</button></div><div class="pack-model-list">${rows}</div></section>`;
  }

  function collectPackTaskModels() {
    return Object.fromEntries([...document.querySelectorAll('[data-pack-model-task]')].map(row => {
      const provider = row.querySelector('.pack-provider').value;
      return [row.dataset.packModelTask, {
        provider,
        model: row.querySelector('.pack-model').value,
        ...(['codex', 'grok'].includes(provider) ? {reasoning_effort: row.querySelector('.pack-reasoning').value} : {}),
      }];
    }));
  }

  function nextStepForReel(reel) {
    if (reel.status === 'rejected') return 0;
    if (!reel.audio) return 3;
    if (!reel.source_ready) return 5;
    if (!reel.preview) return 6;
    if (['visual_ready', 'flagged', 'repaired_pending_review'].includes(reel.status)) return 7;
    if (reel.status === 'approved') return 8;
    if (reel.status === 'scripted') return 3;
    if (reel.status === 'audio_ready') return 4;
    if (reel.status === 'timed') return 5;
    return 2;
  }

  function reelPlayerUrl(previewUrl, reel) {
    if (!previewUrl || !reel) return null;
    const base = previewUrl.endsWith('/') ? previewUrl : `${previewUrl}/`;
    const start = Number(reel.absolute_start || 0);
    const end = Number(reel.absolute_end || start);
    const visualStart = Number(reel.render_absolute_start ?? (reel.render_start_frame != null ? reel.render_start_frame / 30 : start));
    const visualEnd = Number(reel.render_absolute_end ?? (reel.render_end_frame != null ? reel.render_end_frame / 30 : end));
    return `${base}chapter-player.html?${new URLSearchParams({
      start: String(start),
      end: String(end),
      visualStart: String(visualStart),
      visualEnd: String(visualEnd),
      chapter: reel.reel_id || '',
    })}`;
  }

  function reviewMarkup(run) {
    const artifacts = run.artifacts || {};
    const review = artifacts.pack_review || {};
    const findings = review.findings || [];
    const links = (artifacts.review_contact_sheets || []).map((relative, index) => `<a href="${artifactUrl(run.id, relative)}" target="_blank" rel="noreferrer">Contact sheet ${index + 1} ↗</a>`).join('');
    return `<section class="pack-review"><div class="pack-section-head"><div><p class="eyebrow">One-call multimodal screening</p><h3>Pack Visual Review</h3></div>${statusPill(review.status || 'not_run')}</div><div class="pack-review-links">${links || '<span class="reel-pack-subtitle">Contact sheets appear after Stage 7.</span>'}</div>${findings.length ? `<div class="pack-findings">${findings.map(finding => `<article class="pack-finding"><div><strong>${escapeHtml(finding.reel_id)}</strong><small>${escapeHtml(finding.frame_id)} · ${escapeHtml(finding.severity)}</small></div><div><strong>${escapeHtml(finding.category)}</strong><p>${escapeHtml(finding.visible_evidence)}</p><small>${escapeHtml(finding.expected_behaviour)}</small></div><strong>${Math.round(Number(finding.confidence || 0) * 100)}%</strong></article>`).join('')}</div>` : `<p class="reel-pack-subtitle">${review.status === 'passed' ? 'No serious defect was found.' : 'The reviewer returns zero to five high-confidence critical or major findings.'}</p>`}</section>`;
  }

  function reelCard(run, reel, working) {
    const next = nextStepForReel(reel);
    const findings = reel.findings || [];
    const scriptPayload = JSON.stringify({title: reel.title || reel.reel_id, hook: reel.hook || '', narration: reel.narration || '', visual_direction: reel.visual_direction || reel.visual_concept || '', learning_payoff: reel.learning_payoff || ''});
    const rejectable = ['planned', 'scripted'].includes(reel.status);
    const reviewButton = reel.narration ? `<button class="secondary-button pack-script-review" data-reel-id="${escapeHtml(reel.reel_id)}" data-script="${escapeHtml(scriptPayload)}">Review script ↗</button>` : '';
    const nextButton = next ? `<button class="secondary-button pack-reel-next" data-reel-id="${escapeHtml(reel.reel_id)}" data-step="${next}" ${working || reel.status === 'rendered' ? 'disabled' : ''}>Run stage ${next}</button>` : '';
    const canRestore = reel.status === 'rejected' && Number(run.current_step || 1) <= 2;
    const rejectButton = rejectable ? `<button class="danger-button pack-reel-reject" data-reel-id="${escapeHtml(reel.reel_id)}" ${working ? 'disabled' : ''}>Reject Reel</button>` : reel.status === 'rejected' ? `<button class="secondary-button pack-reel-restore" data-reel-id="${escapeHtml(reel.reel_id)}" ${working || !canRestore ? 'disabled' : ''}>Restore Reel</button>` : '';
    const playerUrl = reelPlayerUrl(run.artifacts?.preview_url, reel);
    const preview = playerUrl
      ? `<iframe src="${escapeHtml(playerUrl)}" title="${escapeHtml(reel.reel_id)} live video preview" allow="autoplay"></iframe>`
      : reel.preview
        ? `<a href="${artifactUrl(run.id, reel.preview)}" target="_blank" rel="noreferrer"><img src="${artifactUrl(run.id, reel.preview)}" alt="${escapeHtml(reel.reel_id)} validation contact sheet"></a><a class="pack-preview-evidence" href="${artifactUrl(run.id, reel.preview)}" target="_blank" rel="noreferrer">QA evidence</a>`
        : `<span>${reel.source_ready ? 'Start the live preview to watch this Reel with synchronized audio.' : 'Portrait visual source not generated yet.'}</span>`;
    return `<article class="pack-reel-card"><div class="pack-reel-preview">${preview}</div><div class="pack-reel-body"><div class="pack-reel-head"><div><p class="eyebrow">${escapeHtml(reel.reel_id)}</p><h4>${escapeHtml(reel.title)}</h4></div>${statusPill(reel.status)}</div><div class="pack-reel-meta"><span>${Number(reel.duration || 0).toFixed(1)}s</span><span>${(reel.fact_ids || []).length} facts</span><span>${(reel.objective_ids || []).length} objectives</span></div><p class="pack-reel-copy"><strong>Hook:</strong> ${escapeHtml(reel.hook || '—')}</p><p class="pack-reel-copy"><strong>Payoff:</strong> ${escapeHtml(reel.learning_payoff || '—')}</p>${reel.status === 'rejected' && reel.rejection_reason ? `<div class="pack-reel-findings">Rejected: ${escapeHtml(reel.rejection_reason)}</div>` : ''}${findings.length ? `<div class="pack-reel-findings">${findings.map(item => escapeHtml(item.visible_evidence)).join('<br>')}</div>` : ''}${reel.error ? `<div class="alert">${escapeHtml(reel.error)}</div>` : ''}<div class="pack-reel-actions">${reviewButton}${reel.audio ? `<a class="secondary-button" href="${artifactUrl(run.id, reel.audio)}" target="_blank">Audio ↗</a>` : ''}${playerUrl ? `<a class="secondary-button" href="${escapeHtml(playerUrl)}" target="_blank" rel="noreferrer">Open video ↗</a>` : ''}${reel.video ? `<a class="primary-button" href="${artifactUrl(run.id, reel.video)}" target="_blank">MP4 ↗</a>` : ''}${nextButton}${rejectButton}<button class="danger-button pack-reel-regenerate" data-reel-id="${escapeHtml(reel.reel_id)}" ${working || !reel.source_ready ? 'disabled' : ''}>Regenerate visual</button><button class="secondary-button pack-reel-approve" data-reel-id="${escapeHtml(reel.reel_id)}" ${working || !reel.preview || !['visual_ready', 'flagged', 'repaired_pending_review'].includes(reel.status) ? 'disabled' : ''}>Approve</button><button class="primary-button pack-reel-render" data-reel-id="${escapeHtml(reel.reel_id)}" ${working || reel.status !== 'approved' ? 'disabled' : ''}>Render</button></div></div></article>`;
  }

  function scriptDialogMarkup() {
    return `<dialog class="pack-script-dialog" id="pack-script-dialog"><div class="pack-script-dialog-content" id="pack-script-dialog-content"></div><div class="pack-script-dialog-actions"><button class="secondary-button" id="pack-script-dialog-close">Close</button></div></dialog>`;
  }

  async function loadLog(runId) {
    const box = document.getElementById('pack-run-log');
    if (!box) return;
    try {
      const payload = await request(`/api/runs/${encodeURIComponent(runId)}/logs`);
      box.textContent = payload.log || 'No process output yet.';
      box.scrollTop = box.scrollHeight;
    } catch { /* normal run refresh surfaces errors */ }
  }

  function liveProcessLabel(run) {
    if (!run.process_active && run.status !== 'running' && run.status !== 'rendering') return '';
    const step = run.process_active_step ? `step ${run.process_active_step}` : 'current stage';
    const started = run.process_started_at ? new Date(run.process_started_at).getTime() : 0;
    const elapsed = started ? Math.max(0, Math.round((Date.now() - started) / 1000)) : 0;
    return `LIVE · ${step} · elapsed ${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, '0')}`;
  }

  function renderPackWorkspace(run) {
    ensureStyles();
    const root = document.getElementById('pipeline-panel');
    if (!root) return;
    const artifacts = run.artifacts || {};
    const pack = artifacts.pack || {};
    const reels = artifacts.reels || [];
    const working = ACTIVE.has(run.status) || run.process_active;
    const completed = Number(run.current_step || pack.current_step || 1);
    const counts = pack.summary || {};
    const approved = Number(counts.approved || 0) + Number(counts.rendered || 0);
    const ready = Number(counts.visual_ready || 0) + approved + Number(counts.flagged || 0) + Number(counts.repaired_pending_review || 0);
    root.dataset.reelPackId = run.id;
    root.innerHTML = `<div class="reel-pack-workspace"><section class="reel-pack-header"><div><p class="eyebrow">Standalone portrait production · ${statusPill(run.status)}</p><h2>${escapeHtml(run.topic)}</h2><p class="reel-pack-subtitle"><span class="run-id">${escapeHtml(run.id)} · TOPIC REEL PACK</span><br>${reels.length} independent 1080×1920 productions · ${Number(run.settings?.duration || 45)}s target each</p></div><div class="reel-pack-header-actions"><button class="secondary-button" id="pack-refresh">Refresh</button><button class="secondary-button pack-start-preview" id="pack-start-preview" ${working || completed < 6 ? 'disabled' : ''}>${artifacts.preview_url ? 'Restart live preview' : 'Start live preview'}</button><button class="danger-button" id="pack-stop" ${working ? '' : 'disabled'}>Stop</button><button class="danger-button" id="pack-delete" ${working ? 'disabled' : ''}>Delete</button><button class="secondary-button" id="pack-run-next" ${working || completed >= 8 ? 'disabled' : ''}>Run next</button><button class="primary-button" id="pack-run-review" ${working || completed >= 7 ? 'disabled' : ''}>Run to screening</button><button class="secondary-button" id="pack-screen" ${working || completed < 6 ? 'disabled' : ''}>Screen pack</button><button class="primary-button" id="pack-render-approved" ${working || !approved ? 'disabled' : ''}>Render approved</button></div></section><div class="pack-stepper">${PACK_STEPS.map((name, index) => { const step = index + 1; return `<button class="pack-step${completed >= step ? ' is-done' : ''}" data-pack-step="${step}" ${working ? 'disabled' : ''}><span>${completed >= step ? '✓' : step}</span><b>${escapeHtml(name)}</b></button>`; }).join('')}</div><section class="pack-summary"><article><span>Total Reels</span><strong>${reels.length}</strong></article><article><span>Scripts ready</span><strong>${Number(counts.scripted || 0) + ready}</strong></article><article><span>Rejected</span><strong>${Number(counts.rejected || 0)}</strong></article><article><span>Visual evidence</span><strong>${ready}</strong></article><article><span>Approved</span><strong>${approved}</strong></article><article><span>Rendered</span><strong>${Number(counts.rendered || 0)}</strong></article></section>${reviewMarkup(run)}${modelMapMarkup(run, working)}<section><div class="pack-section-head"><div><p class="eyebrow">Independent child productions</p><h3>${reels.length} standalone Reels</h3></div><div class="reel-pack-header-actions"><span class="reel-pack-subtitle">${artifacts.preview_url ? 'Each card is a synchronized video player with audio.' : 'Start this to replace validation contact sheets with video.'}</span><button class="primary-button pack-start-preview" ${working || completed < 6 ? 'disabled' : ''}>${artifacts.preview_url ? 'Restart live video + audio' : 'Start live video + audio'}</button></div></div><div class="pack-reels">${reels.map(reel => reelCard(run, reel, working)).join('')}</div></section>${scriptDialogMarkup()}<pre class="pack-log" id="pack-run-log">Loading logs…</pre>${run.error ? `<div class="alert">${escapeHtml(run.error)}</div>` : ''}</div>`;
    const live = liveProcessLabel(run);
    if (live) {
      const eyebrow = root.querySelector('.reel-pack-header .eyebrow');
      if (eyebrow) eyebrow.insertAdjacentHTML('beforeend', ` <span class="pack-live-status">${escapeHtml(live)}</span>`);
    }
    loadLog(run.id);
    if (working) startPolling(run.id); else stopPolling();
  }

  function signatureFor(run) {
    const pack = run.artifacts?.pack || {};
    return JSON.stringify([run.id, run.updated_at, run.status, run.process_active, run.current_step, pack.updated_at, pack.summary, run.artifacts?.pack_review?.status]);
  }

  async function syncActiveWorkspace(force = false) {
    addProductControls();
    const label = document.querySelector('.run-id');
    const runId = label ? label.textContent.split('·')[0].trim() : '';
    if (!runId || activeRequest === runId) return;
    activeRequest = runId;
    try {
      const payload = await request(`/api/runs/${encodeURIComponent(runId)}`);
      const run = payload.run;
      if (document.getElementById('content-product-select')?.value !== PRODUCT) return;
      if (run.content_product !== PRODUCT && run.artifacts?.content_product !== PRODUCT) {
        if (activePackId === runId) activePackId = '';
        return;
      }
      const signature = signatureFor(run);
      const root = document.getElementById('pipeline-panel');
      if (!force && signature === lastSignature && root?.dataset.reelPackId === runId) {
        await loadLog(runId);
        return;
      }
      activePackId = runId;
      lastSignature = signature;
      renderPackWorkspace(run);
    } catch { /* app.js remains authoritative for non-pack errors */ }
    finally { activeRequest = null; }
  }

  function startPolling(runId) {
    if (pollTimer && activePackId === runId) return;
    stopPolling();
    pollTimer = setInterval(() => syncActiveWorkspace(true), 1800);
  }

  function stopPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
  }

  async function executePack(runId, payload) {
    payload.confirm_paid_api = true;
    payload.task_models = collectPackTaskModels();
    const response = await request(`/api/runs/${encodeURIComponent(runId)}/execute`, {method: 'POST', body: JSON.stringify(payload)});
    renderPackWorkspace(response.run);
  }

  async function handlePackAction(event) {
    const root = event.target.closest('#pipeline-panel[data-reel-pack-id]');
    if (!root) return false;
    const runId = root.dataset.reelPackId;
    const button = event.target.closest('button');
    if (!button) return false;
    const isPackControl = button.matches([
      '#pack-refresh',
      '#pack-start-preview',
      '.pack-start-preview',
      '#pack-stop',
      '#pack-delete',
      '#pack-save-models',
      '#pack-run-next',
      '#pack-run-review',
      '#pack-screen',
      '#pack-render-approved',
      '#pack-script-dialog-close',
      '[data-pack-step]',
      '.pack-script-review',
      '.pack-reel-next',
      '.pack-reel-regenerate',
      '.pack-reel-reject',
      '.pack-reel-restore',
      '.pack-reel-approve',
      '.pack-reel-render',
    ].join(','));
    if (!isPackControl) return false;
    event.preventDefault();
    event.stopImmediatePropagation();
    try {
      if (button.id === 'pack-refresh') return await syncActiveWorkspace(true), true;
      if (button.classList.contains('pack-start-preview')) {
        const response = await request(`/api/runs/${encodeURIComponent(runId)}/preview`, {method: 'POST', body: '{}'});
        renderPackWorkspace(response.run); return true;
      }
      if (button.id === 'pack-stop') {
        const response = await request(`/api/runs/${encodeURIComponent(runId)}/stop`, {method: 'POST', body: '{}'});
        renderPackWorkspace(response.run); return true;
      }
      if (button.id === 'pack-delete') {
        if (!window.confirm(`Delete Reel pack ${runId} and all 12 child productions?`)) return true;
        await request(`/api/runs/${encodeURIComponent(runId)}`, {method: 'DELETE'});
        localStorage.removeItem('mav-open-reel-pack'); window.location.reload(); return true;
      }
      if (button.id === 'pack-save-models') {
        const response = await request(`/api/runs/${encodeURIComponent(runId)}/models`, {method: 'POST', body: JSON.stringify({task_models: collectPackTaskModels()})});
        renderPackWorkspace(response.run); return true;
      }
      if (button.id === 'pack-run-next') {
        const current = Number(document.querySelectorAll('.pack-step.is-done').length || 1);
        await executePack(runId, {from_step: Math.min(8, current + 1), stop_after_step: Math.min(8, current + 1)}); return true;
      }
      if (button.id === 'pack-run-review') {
        const current = Number(document.querySelectorAll('.pack-step.is-done').length || 1);
        await executePack(runId, {from_step: Math.min(7, current + 1), stop_after_step: 7}); return true;
      }
      if (button.id === 'pack-screen') {
        const response = await request(`/api/runs/${encodeURIComponent(runId)}/reel-pack/screen`, {method: 'POST', body: JSON.stringify({auto_repair: true, task_models: collectPackTaskModels()})});
        renderPackWorkspace(response.run); return true;
      }
      if (button.id === 'pack-render-approved') {
        const response = await request(`/api/runs/${encodeURIComponent(runId)}/reel-pack/render`, {method: 'POST', body: JSON.stringify({task_models: collectPackTaskModels()})});
        renderPackWorkspace(response.run); return true;
      }
      if (button.id === 'pack-script-dialog-close') {
        document.getElementById('pack-script-dialog')?.close(); return true;
      }
      if (button.classList.contains('pack-script-review')) {
        const script = JSON.parse(button.dataset.script || '{}');
        const dialog = document.getElementById('pack-script-dialog');
        const content = document.getElementById('pack-script-dialog-content');
        if (dialog && content) {
          content.innerHTML = `<p class="pack-script-label">${escapeHtml(button.dataset.reelId || 'Reel')}</p><h3>${escapeHtml(script.title || '')}</h3><p class="pack-script-label">Hook</p><p>${escapeHtml(script.hook || '—')}</p><p class="pack-script-label">Narration</p><p>${escapeHtml(script.narration || '—')}</p><p class="pack-script-label">Learning payoff</p><p>${escapeHtml(script.learning_payoff || '—')}</p><p class="pack-script-label">Visual direction</p><p>${escapeHtml(script.visual_direction || '—')}</p>`;
          if (typeof dialog.showModal === 'function') dialog.showModal(); else dialog.setAttribute('open', '');
        }
        return true;
      }
      if (button.classList.contains('pack-reel-reject')) {
        const reason = window.prompt(`Why are you rejecting ${button.dataset.reelId}?`, 'Script needs revision');
        if (reason === null) return true;
        const response = await request(`/api/runs/${encodeURIComponent(runId)}/reel-pack/reels/${encodeURIComponent(button.dataset.reelId)}/reject`, {method: 'POST', body: JSON.stringify({reason})});
        renderPackWorkspace(response.run); return true;
      }
      if (button.classList.contains('pack-reel-restore')) {
        const response = await request(`/api/runs/${encodeURIComponent(runId)}/reel-pack/reels/${encodeURIComponent(button.dataset.reelId)}/restore`, {method: 'POST', body: '{}'});
        renderPackWorkspace(response.run); return true;
      }
      if (button.matches('[data-pack-step]')) {
        const step = Number(button.dataset.packStep);
        await executePack(runId, {from_step: step, stop_after_step: step}); return true;
      }
      const reelId = button.dataset.reelId;
      if (button.classList.contains('pack-reel-next')) {
        const step = Number(button.dataset.step);
        const response = await request(`/api/runs/${encodeURIComponent(runId)}/reel-pack/reels/${encodeURIComponent(reelId)}/run`, {method: 'POST', body: JSON.stringify({from_step: step, stop_after_step: step, confirm_paid_api: true, task_models: collectPackTaskModels()})});
        renderPackWorkspace(response.run); return true;
      }
      if (button.classList.contains('pack-reel-regenerate')) {
        if (!window.confirm(`Regenerate only ${reelId}'s portrait visual? Its script, audio, timing, and every other Reel remain unchanged.`)) return true;
        const response = await request(`/api/runs/${encodeURIComponent(runId)}/reel-pack/reels/${encodeURIComponent(reelId)}/regenerate`, {method: 'POST', body: JSON.stringify({task_models: collectPackTaskModels()})});
        renderPackWorkspace(response.run); return true;
      }
      if (button.classList.contains('pack-reel-approve')) {
        const response = await request(`/api/runs/${encodeURIComponent(runId)}/reel-pack/reels/${encodeURIComponent(reelId)}/approve`, {method: 'POST', body: '{}'});
        renderPackWorkspace(response.run); return true;
      }
      if (button.classList.contains('pack-reel-render')) {
        const response = await request(`/api/runs/${encodeURIComponent(runId)}/reel-pack/render`, {method: 'POST', body: JSON.stringify({target_reel_id: reelId, task_models: collectPackTaskModels()})});
        renderPackWorkspace(response.run); return true;
      }
    } catch (error) {
      window.alert(error.message || String(error));
      return true;
    }
    return false;
  }

  document.addEventListener('click', async event => {
    if (await handlePackAction(event)) return;
    const create = event.target.closest('#create-run-button');
    if (!create || document.getElementById('content-product-select')?.value !== PRODUCT) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    create.disabled = true;
    const previous = create.textContent;
    create.textContent = 'Creating Reel pack…';
    try {
      const response = await request('/api/runs', {method: 'POST', body: JSON.stringify(packCreationPayload())});
      localStorage.setItem('mav-open-reel-pack', response.run.id);
      window.location.reload();
    } catch (error) {
      window.alert(error.message || String(error));
      create.disabled = false;
      create.textContent = previous;
    }
  }, true);

  document.addEventListener('change', event => {
    if (event.target.id === 'content-product-select' && event.target.value !== PRODUCT) {
      activePackId = '';
      lastSignature = '';
      stopPolling();
      return;
    }
    if (!event.target.classList.contains('pack-provider')) return;
    const row = event.target.closest('[data-pack-model-task]');
    const models = JSON.parse(row.dataset.providerModels || '{}');
    const configured = JSON.parse(row.dataset.providerOptions || '{}');
    const provider = event.target.value;
    const options = configured[provider] || [models[provider]];
    row.querySelector('.pack-model').innerHTML = options.filter(Boolean).map(model => `<option value="${escapeHtml(model)}">${escapeHtml(model)}</option>`).join('');
    const reasoning = row.querySelector('.pack-reasoning');
    reasoning.disabled = !['codex', 'grok'].includes(provider);
    reasoning.innerHTML = (provider === 'grok' ? ['low', 'medium', 'high'] : ['low', 'medium', 'high', 'xhigh', 'max', 'ultra']).map(value => `<option value="${value}">${value}</option>`).join('');
  });

  function reopenCreatedPack() {
    const pending = localStorage.getItem('mav-open-reel-pack');
    if (!pending) return;
    const button = [...document.querySelectorAll('.run-open')].find(item => item.dataset.run === pending);
    if (!button) return;
    localStorage.removeItem('mav-open-reel-pack');
    button.click();
  }

  ensureStyles();
  document.addEventListener('mav:render-reel-pack', event => {
    const run = event.detail?.run;
    if (!run || (run.content_product !== PRODUCT && run.artifacts?.content_product !== PRODUCT)) return;
    activePackId = run.id;
    lastSignature = signatureFor(run);
    renderPackWorkspace(run);
  });
  const observer = new MutationObserver(() => {
    addProductControls();
    reopenCreatedPack();
    syncActiveWorkspace();
  });
  observer.observe(document.documentElement, {subtree: true, childList: true});
  addProductControls();
  syncActiveWorkspace(true);
  setInterval(() => { addProductControls(); reopenCreatedPack(); syncActiveWorkspace(); }, 2500);
})();
