const PANEL_ID = 'motion-canvas-lesson-review-panel';
let activeRequest = null;
let lastSignature = '';

function escapeHtml(value = '') {
  return String(value).replace(/[&<>'"]/g, character => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'}[character]));
}

function activeRunId() {
  const label = document.querySelector('.run-id');
  return label ? label.textContent.split('·')[0].trim() : '';
}

function artifactUrl(runId, relative) {
  return `/artifacts/runs/${encodeURIComponent(runId)}/${String(relative).split('/').map(encodeURIComponent).join('/')}`;
}

function panelMarkup(runId, report) {
  const findings = Array.isArray(report.findings) ? report.findings : [];
  const repairs = new Map((report.repairs || []).map(item => [String(item.reel_id), item]));
  const contactSheets = [...(report.contact_sheets || []), ...(report.corrected_contact_sheets || [])];
  const status = String(report.status || 'not_run');
  const rows = findings.map(finding => {
    const repair = repairs.get(String(finding.reel_id));
    return `<article class="lesson-review-row">
      <div><strong>${escapeHtml(finding.reel_id)}</strong><small>Chapter ${escapeHtml(finding.chapter_number ?? '—')} · ${escapeHtml(finding.frame_id)} · ${escapeHtml(finding.severity)}</small></div>
      <div><b>${escapeHtml(finding.category)}</b><p>${escapeHtml(finding.visible_evidence)}</p><small>Expected: ${escapeHtml(finding.expected_behaviour)}</small></div>
      <div class="lesson-review-confidence">${Math.round(Number(finding.confidence || 0) * 100)}%<small>${escapeHtml(repair?.status || 'screened')}</small></div>
    </article>`;
  }).join('');
  const links = contactSheets.map((relative, index) => `<a href="${artifactUrl(runId, relative)}" target="_blank" rel="noreferrer">${index < (report.contact_sheets || []).length ? 'Screening' : 'Corrected'} sheet ${index + 1} ↗</a>`).join('');
  const approval = status === 'repaired_pending_review'
    ? `<div class="lesson-review-approval"><p>Inspect the corrected sheet above. Approve only if the repaired reels now look correct.</p><button type="button" class="primary-button approve-lesson-review" data-run-id="${escapeHtml(runId)}">Approve corrected review</button></div>`
    : status === 'approved' ? `<div class="lesson-review-approved">Approved ${escapeHtml(report.approved_at || '')}</div>` : '';
  return `<section class="lesson-review-panel" id="${PANEL_ID}">
    <header><div><p class="eyebrow">One-call rendered screening</p><h3>Lesson Visual Review</h3></div><span class="lesson-review-status status-${escapeHtml(status)}">${escapeHtml(status.replaceAll('_', ' '))}</span></header>
    <div class="lesson-review-summary">
      <span><b>${escapeHtml(report.screening_calls ?? 0)}</b> Gemini screening call</span>
      <span><b>${findings.length}</b> high-confidence finding${findings.length === 1 ? '' : 's'}</span>
      <span><b>${escapeHtml((report.repaired_reels || []).length)}</b> regenerated reel${(report.repaired_reels || []).length === 1 ? '' : 's'}</span>
      ${report.elapsed_seconds != null ? `<span><b>${escapeHtml(report.elapsed_seconds)}s</b> elapsed</span>` : ''}
    </div>
    ${links ? `<div class="lesson-review-links">${links}</div>` : ''}
    ${approval}
    ${rows ? `<div class="lesson-review-findings">${rows}</div>` : `<p class="lesson-review-empty">${status === 'passed' ? 'No serious visible defect was found.' : 'The review runs during Compile & QA after the complete lesson renders.'}</p>`}
    ${report.error ? `<div class="alert">${escapeHtml(report.error)}</div>` : ''}
  </section>`;
}

function ensureStyles() {
  if (document.getElementById('lesson-review-styles')) return;
  const style = document.createElement('style');
  style.id = 'lesson-review-styles';
  style.textContent = `
    .lesson-review-panel{margin:18px 0;border:1px solid rgba(70,217,255,.2);border-radius:18px;padding:18px;background:linear-gradient(145deg,rgba(14,29,49,.97),rgba(7,17,31,.97))}
    .lesson-review-panel>header{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:13px}.lesson-review-panel h3{margin:2px 0 0}.lesson-review-status{padding:7px 11px;border-radius:999px;font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.06em;background:rgba(145,168,197,.12)}
    .status-passed,.status-approved{color:#6ee7b7;background:rgba(52,211,153,.12)}.status-issues_found,.status-needs_review{color:#ff8f8f;background:rgba(255,107,107,.12)}.status-repaired_pending_review{color:#ffc857;background:rgba(255,200,87,.12)}
    .lesson-review-summary,.lesson-review-links{display:flex;flex-wrap:wrap;gap:9px;margin-bottom:12px}.lesson-review-summary span{padding:7px 9px;border-radius:10px;background:rgba(255,255,255,.045);color:#91a8c5;font-size:12px}.lesson-review-summary b{color:#eaf3ff;font-size:15px;margin-right:3px}.lesson-review-links a{font-size:13px}
    .lesson-review-findings{display:grid;gap:8px}.lesson-review-row{display:grid;grid-template-columns:minmax(145px,.55fr) minmax(300px,2fr) 80px;gap:14px;align-items:center;padding:12px;border-radius:13px;background:rgba(255,255,255,.035)}.lesson-review-row small{display:block;color:#91a8c5;margin-top:3px}.lesson-review-row p{margin:4px 0;color:#eaf3ff}.lesson-review-confidence{text-align:right;color:#46d9ff;font-weight:800}.lesson-review-confidence small{font-weight:500}.lesson-review-empty{color:#91a8c5}
    .lesson-review-approval{display:flex;align-items:center;justify-content:space-between;gap:16px;margin:12px 0;padding:12px;border:1px solid rgba(255,200,87,.25);border-radius:12px;background:rgba(255,200,87,.06)}.lesson-review-approval p{margin:0;color:#eaf3ff}.lesson-review-approved{margin:12px 0;color:#6ee7b7;font-weight:700}
    @media(max-width:900px){.lesson-review-row{grid-template-columns:1fr}.lesson-review-confidence{text-align:left}}
  `;
  document.head.append(style);
}

async function refreshLessonReview() {
  const runId = activeRunId();
  const host = document.querySelector('.run-intelligence') || document.querySelector('#chapter-workspace-root');
  if (!runId || !host || activeRequest === runId) return;
  activeRequest = runId;
  try {
    const response = await fetch(artifactUrl(runId, 'motion_canvas/lesson-review.json'), {cache: 'no-store'});
    if (!response.ok) {
      document.getElementById(PANEL_ID)?.remove();
      return;
    }
    const report = await response.json();
    const signature = `${runId}:${JSON.stringify(report)}`;
    if (signature === lastSignature && document.getElementById(PANEL_ID)) return;
    ensureStyles();
    document.getElementById(PANEL_ID)?.remove();
    host.insertAdjacentHTML('afterend', panelMarkup(runId, report));
    lastSignature = signature;
  } catch {
    // Studio's normal run status remains authoritative when the optional report is unavailable.
  } finally {
    activeRequest = null;
  }
}

window.addEventListener('hashchange', () => { lastSignature = ''; refreshLessonReview(); });
document.addEventListener('click', async event => {
  const button = event.target.closest('.approve-lesson-review');
  if (!button) return;
  if (!window.confirm('Approve the corrected Gemini evidence for this lesson?')) return;
  button.disabled = true;
  button.textContent = 'Approving…';
  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(button.dataset.runId)}/lesson-review/approve`, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}',
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || `Approval failed (${response.status})`);
    }
    lastSignature = '';
    await refreshLessonReview();
  } catch (error) {
    window.alert(error.message || String(error));
    button.disabled = false;
    button.textContent = 'Approve corrected review';
  }
});
setInterval(refreshLessonReview, 3000);
refreshLessonReview();
