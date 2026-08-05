const ytRoot = document.getElementById('youtube-dashboard-root');
const ytState = {
  dashboard: null,
  selectedItems: new Set(),
  timer: null,
  loading: false,
  settings: {
    privacy: 'private',
    publishAt: '',
    categoryId: '27',
    madeForKids: false,
    notifySubscribers: false,
    postFirstComment: false,
    playlistIds: '',
    autoOrganizeCourse: true,
    coursePlaylistTitle: 'Cambridge IGCSE Physics (0625) — Complete Course',
    confirmed: false,
  },
};

const ytEscape = (value = '') => String(value).replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
const ytFormatBytes = value => {
  const bytes = Number(value || 0);
  if (!bytes) return '—';
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
};
const ytFormatDate = value => value ? new Date(value).toLocaleString(undefined, {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}) : '—';

async function ytRequest(path, options = {}) {
  const response = await fetch(path, {headers:{'Content-Type':'application/json',...(options.headers || {})},...options});
  let payload = {};
  try { payload = await response.json(); } catch { payload = {}; }
  if (!response.ok) throw new Error(payload.error || response.statusText || 'Request failed');
  return payload;
}

function ytCaptureSettings() {
  if (!ytRoot) return;
  const get = id => document.getElementById(id);
  if (get('yt-privacy')) ytState.settings.privacy = get('yt-privacy').value;
  if (get('yt-publish-at')) ytState.settings.publishAt = get('yt-publish-at').value;
  if (get('yt-category')) ytState.settings.categoryId = get('yt-category').value;
  if (get('yt-made-for-kids')) ytState.settings.madeForKids = get('yt-made-for-kids').checked;
  if (get('yt-notify')) ytState.settings.notifySubscribers = get('yt-notify').checked;
  if (get('yt-comment')) ytState.settings.postFirstComment = get('yt-comment').checked;
  if (get('yt-playlists')) ytState.settings.playlistIds = get('yt-playlists').value;
  if (get('yt-auto-course')) ytState.settings.autoOrganizeCourse = get('yt-auto-course').checked;
  if (get('yt-course-title')) ytState.settings.coursePlaylistTitle = get('yt-course-title').value;
  if (get('yt-confirm')) ytState.settings.confirmed = get('yt-confirm').checked;
}

function ytBadge(label, state) { return `<span class="yt-badge ${state}">${ytEscape(label)}</span>`; }

function ytChannelMarkup(profile, selectedId) {
  const selected = profile.id === selectedId;
  const initials = String(profile.channel_title || 'YT').split(/\s+/).slice(0,2).map(part => part[0] || '').join('').toUpperCase();
  return `<button class="yt-channel${selected ? ' is-selected' : ''}" data-yt-profile="${ytEscape(profile.id)}">
    <span class="yt-avatar">${ytEscape(initials)}</span>
    <span><strong>${ytEscape(profile.label || profile.channel_title)}</strong><small>${ytEscape(profile.channel_title)} · ${ytEscape(profile.channel_id)}</small></span>
    <span class="yt-selected-mark">${selected ? 'SELECTED' : 'USE'}</span>
  </button>`;
}

function ytItemMarkup(item) {
  const selected = ytState.selectedItems.has(item.key);
  const disabled = !item.ready || item.upload_status === 'uploaded';
  const kind = item.kind === 'reel' ? `Reel · ${item.reel_id}` : 'Long-form lesson';
  return `<label class="yt-item${item.upload_status === 'uploaded' ? ' is-uploaded' : ''}">
    <input class="yt-item-check" type="checkbox" value="${ytEscape(item.key)}" ${selected ? 'checked' : ''} ${disabled ? 'disabled' : ''}>
    <span class="yt-item-copy">
      <strong>${ytEscape(item.title)}</strong>
      <small>${ytEscape(item.run_id)} · ${ytEscape(kind)}</small>
      <span class="yt-badges">
        ${ytBadge(item.video_ready ? 'MP4 ready' : 'MP4 missing', item.video_ready ? 'ready' : 'missing')}
        ${ytBadge(item.metadata_ready ? 'Metadata ready' : 'Metadata missing', item.metadata_ready ? 'ready' : 'missing')}
        ${item.kind === 'reel' ? ytBadge('Embedded cover', 'ready') : ytBadge(item.thumbnail_ready ? 'Thumbnail ready' : 'No thumbnail', item.thumbnail_ready ? 'ready' : 'missing')}
        ${item.upload_status === 'uploaded' ? ytBadge('Uploaded', 'uploaded') : ''}
      </span>
    </span>
    <span class="yt-item-side"><b>${ytFormatBytes(item.video_size)}</b>${item.youtube_url ? `<a href="${ytEscape(item.youtube_url)}" target="_blank" rel="noreferrer">Open on YouTube ↗</a>` : ''}</span>
  </label>`;
}

function ytJobMarkup(job) {
  const active = ['starting','waiting_for_browser','queued','running'].includes(job.status);
  const total = Number(job.total || (job.type === 'authorization' ? 1 : 0));
  const current = Number(job.current || (job.status === 'completed' ? total : 0));
  const progress = total ? Math.round((current / total) * 100) : (active ? 12 : job.status === 'completed' ? 100 : 0);
  return `<article class="yt-job">
    <div><strong>${ytEscape(job.message || job.type)}</strong><small>${ytEscape(job.channel_title || job.status)}${job.error ? ` · ${ytEscape(job.error)}` : ''}</small></div>
    <time>${ytFormatDate(job.updated_at)}</time>
    <div class="yt-job-progress"><i style="width:${Math.max(0,Math.min(100,progress))}%"></i></div>
  </article>`;
}

function ytRender() {
  if (!ytRoot || !ytState.dashboard) return;
  ytCaptureSettings();
  const data = ytState.dashboard;
  const longform = data.candidates?.longform || [];
  const reels = data.candidates?.reels || [];
  const readyLongform = longform.filter(item => item.ready && item.upload_status !== 'uploaded').length;
  const readyReels = reels.filter(item => item.ready && item.upload_status !== 'uploaded').length;
  const selected = data.selected_channel;
  const activeJob = (data.jobs || []).find(job => ['starting','waiting_for_browser','queued','running'].includes(job.status));
  const s = ytState.settings;
  ytRoot.innerHTML = `<div class="yt-dashboard">
    <section class="yt-hero">
      <div class="yt-hero-copy"><p class="eyebrow">Publishing control room</p><h2>${selected ? `Ready for ${ytEscape(selected.channel_title)}` : 'Connect a YouTube channel'}</h2><p>Choose the exact channel, review upload-ready long-form lessons and Reels, then publish through one guarded queue. Every upload is checked against the selected channel ID before transfer begins.</p></div>
      <div class="yt-hero-metrics"><span>Project · ${ytEscape(data.project?.id || 'capture-3494f')}</span><span>${data.client_ready ? 'OAuth ready' : 'OAuth missing'}</span><span>${readyLongform} long-form ready</span><span>${readyReels} reels ready</span></div>
    </section>
    ${activeJob?.status === 'waiting_for_browser' ? '<p class="yt-error">Google authorization is waiting in your browser. Choose the intended YouTube or Brand Account and approve access.</p>' : ''}
    <div class="yt-grid">
      <div class="yt-stack">
        <section class="yt-panel">
          <header class="yt-panel-head"><div><p class="eyebrow">Channel profiles</p><h3>Publishing identity</h3></div><div class="yt-actions"><button class="secondary-button" id="yt-add-channel">Add channel</button><button class="secondary-button" id="yt-reauthorize" ${selected ? '' : 'disabled'}>Reauthorize</button></div></header>
          <div class="yt-channel-list">${data.profiles?.length ? data.profiles.map(profile => ytChannelMarkup(profile,data.selected_profile_id)).join('') : '<div class="yt-empty">No authorized channels yet. Add a channel and choose the correct YouTube or Brand Account in Google.</div>'}</div>
        </section>
        <section class="yt-panel">
          <header class="yt-panel-head"><div><p class="eyebrow">Release settings</p><h3>Publish configuration</h3></div><span class="count-chip">Education</span></header>
          <div class="yt-settings">
            <label class="yt-field"><span>Visibility</span><select id="yt-privacy"><option value="private" ${s.privacy === 'private' ? 'selected' : ''}>Private</option><option value="unlisted" ${s.privacy === 'unlisted' ? 'selected' : ''}>Unlisted</option><option value="public" ${s.privacy === 'public' ? 'selected' : ''}>Public</option></select></label>
            <label class="yt-field"><span>Category</span><select id="yt-category"><option value="27" ${s.categoryId === '27' ? 'selected' : ''}>27 · Education</option><option value="28" ${s.categoryId === '28' ? 'selected' : ''}>28 · Science & Technology</option></select></label>
            <label class="yt-field wide"><span>Schedule one private upload (local time)</span><input id="yt-publish-at" type="datetime-local" value="${ytEscape(s.publishAt)}"></label>
            <label class="yt-field wide"><span>Course playlist</span><input id="yt-course-title" value="${ytEscape(s.coursePlaylistTitle)}"></label>
            <label class="yt-field wide"><span>Additional playlist IDs (optional)</span><textarea id="yt-playlists" placeholder="PLxxxxxxxxxxxx">${ytEscape(s.playlistIds)}</textarea></label>
            <div class="yt-options">
              <label class="yt-check"><input id="yt-auto-course" type="checkbox" ${s.autoOrganizeCourse ? 'checked' : ''}>Automatically manage the course playlist, chapters, and previous/next links</label>
              <label class="yt-check"><input id="yt-made-for-kids" type="checkbox" ${s.madeForKids ? 'checked' : ''}>This content is made for kids</label>
              <label class="yt-check"><input id="yt-notify" type="checkbox" ${s.notifySubscribers ? 'checked' : ''}>Notify subscribers when YouTube makes it public</label>
              <label class="yt-check"><input id="yt-comment" type="checkbox" ${s.postFirstComment ? 'checked' : ''}>Post the generated first comment (YouTube’s API cannot pin it)</label>
            </div>
          </div>
          <footer class="yt-publish-footer">
            <label class="yt-check"><input id="yt-confirm" type="checkbox" ${s.confirmed ? 'checked' : ''}>I reviewed the selected channel, items, visibility, audience, and schedule.</label>
            <button class="primary-button" id="yt-publish" ${selected && ytState.selectedItems.size ? '' : 'disabled'}>Publish ${ytState.selectedItems.size || ''} selected</button>
            <p class="yt-safety">Uploads run sequentially and stop on the first failure. Existing upload receipts are never published twice.</p>
          </footer>
        </section>
        <section class="yt-panel">
          <header class="yt-panel-head"><div><p class="eyebrow">Activity</p><h3>Authorization & publish jobs</h3></div><button class="secondary-button" id="yt-refresh">Refresh</button></header>
          <div class="yt-job-list">${data.jobs?.length ? data.jobs.slice(0,8).map(ytJobMarkup).join('') : '<div class="yt-empty">No YouTube jobs yet.</div>'}</div>
        </section>
      </div>
      <div class="yt-library">
        <section class="yt-library-section"><header class="yt-section-heading"><div><p class="eyebrow">16:9 lessons</p><h3>Long-form publishing pipeline</h3></div><span>${readyLongform} ready · ${longform.length} visible</span></header><div class="yt-item-list">${longform.length ? longform.map(ytItemMarkup).join('') : '<div class="yt-empty">Generate YouTube assets for a rendered lesson to make it appear here.</div>'}</div></section>
        <section class="yt-library-section"><header class="yt-section-heading"><div><p class="eyebrow">9:16 shorts</p><h3>Reels publishing pipeline</h3></div><span>${readyReels} ready · ${reels.length} visible</span></header><div class="yt-item-list">${reels.length ? reels.map(ytItemMarkup).join('') : '<div class="yt-empty">Render a Reel and generate its YouTube asset pack to make it appear here.</div>'}</div></section>
      </div>
    </div>
  </div>`;
  ytManagePolling();
}

async function ytLoad() {
  if (!ytRoot || ytState.loading) return;
  ytState.loading = true;
  try {
    ytState.dashboard = await ytRequest('/api/youtube/dashboard');
    const validKeys = new Set([...(ytState.dashboard.candidates?.longform || []),...(ytState.dashboard.candidates?.reels || [])].filter(item => item.ready && item.upload_status !== 'uploaded').map(item => item.key));
    ytState.selectedItems = new Set([...ytState.selectedItems].filter(key => validKeys.has(key)));
    ytRender();
  } catch (error) {
    ytRoot.innerHTML = `<p class="yt-error">${ytEscape(error.message || error)}</p>`;
  } finally { ytState.loading = false; }
}

function ytManagePolling() {
  const active = (ytState.dashboard?.jobs || []).some(job => ['starting','waiting_for_browser','queued','running'].includes(job.status));
  if (active && !ytState.timer) ytState.timer = setInterval(ytLoad, 2000);
  if (!active && ytState.timer) { clearInterval(ytState.timer); ytState.timer = null; }
}

async function ytAuthorize(profileId = null) {
  const label = profileId ? '' : (window.prompt('Optional label for this channel profile:', '') ?? null);
  if (label === null) return;
  await ytRequest('/api/youtube/profiles/authorize', {method:'POST',body:JSON.stringify({profile_id:profileId,label})});
  await ytLoad();
}

async function ytPublish() {
  ytCaptureSettings();
  const data = ytState.dashboard;
  if (!data?.selected_profile_id) throw new Error('Choose an authorized channel first.');
  if (!ytState.selectedItems.size) throw new Error('Select at least one long-form video or Reel.');
  if (!ytState.settings.confirmed) throw new Error('Confirm the channel and release settings before publishing.');
  if (ytState.settings.publishAt && ytState.selectedItems.size !== 1) throw new Error('Scheduling supports one selected item at a time.');
  const visibility = ytState.settings.privacy;
  if (!window.confirm(`Publish ${ytState.selectedItems.size} item${ytState.selectedItems.size === 1 ? '' : 's'} to ${data.selected_channel.channel_title} as ${visibility}?`)) return;
  const publishAt = ytState.settings.publishAt ? new Date(ytState.settings.publishAt).toISOString() : null;
  const playlistIds = ytState.settings.playlistIds.split(/[\n,]+/).map(value => value.trim()).filter(Boolean);
  await ytRequest('/api/youtube/publish', {method:'POST',body:JSON.stringify({
    profile_id:data.selected_profile_id,
    item_keys:[...ytState.selectedItems],
    privacy:visibility,
    publish_at:publishAt,
    category_id:ytState.settings.categoryId,
    made_for_kids:ytState.settings.madeForKids,
    notify_subscribers:ytState.settings.notifySubscribers,
    post_first_comment:ytState.settings.postFirstComment,
    playlist_ids:playlistIds,
    auto_organize_course:ytState.settings.autoOrganizeCourse,
    course_playlist_title:ytState.settings.coursePlaylistTitle,
    confirm_publish:true,
  })});
  ytState.settings.confirmed = false;
  ytState.selectedItems.clear();
  await ytLoad();
}

document.addEventListener('change', async event => {
  if (event.target.classList.contains('yt-item-check')) {
    event.target.checked ? ytState.selectedItems.add(event.target.value) : ytState.selectedItems.delete(event.target.value);
    ytRender();
  }
});

document.addEventListener('click', async event => {
  const nav = event.target.closest('.nav-item[data-view="youtube"]');
  if (nav) setTimeout(ytLoad, 0);
  const profile = event.target.closest('[data-yt-profile]');
  if (profile) {
    try { await ytRequest('/api/youtube/profiles/select', {method:'POST',body:JSON.stringify({profile_id:profile.dataset.ytProfile})}); await ytLoad(); } catch (error) { window.alert(error.message || error); }
    return;
  }
  try {
    if (event.target.closest('#yt-add-channel')) return await ytAuthorize();
    if (event.target.closest('#yt-reauthorize')) {
      if (!window.confirm(`Reauthorize ${ytState.dashboard?.selected_channel?.channel_title || 'this channel'}?`)) return;
      return await ytAuthorize(ytState.dashboard.selected_profile_id);
    }
    if (event.target.closest('#yt-refresh')) return await ytLoad();
    if (event.target.closest('#yt-publish')) return await ytPublish();
  } catch (error) { window.alert(error.message || error); }
});

if (location.hash === '#youtube') ytLoad();
