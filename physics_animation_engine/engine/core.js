import { registry } from '../modules/_registry.js';
import { narrator } from './narrator.js';
import { validateSpec } from './validator.js';

const query = new URLSearchParams(window.location.search);
const exportMode = query.get('export') === '1';
if (exportMode) document.body.classList.add('export-mode');

const dom = {
  stage: document.getElementById('stage'),
  viewport: document.getElementById('stage-viewport'),
  loading: document.getElementById('stage-loading'),
  play: document.getElementById('play-button'),
  restart: document.getElementById('restart-button'),
  mute: document.getElementById('mute-button'),
  range: document.getElementById('timeline-range'),
  current: document.getElementById('current-time'),
  total: document.getElementById('total-time'),
  speed: document.getElementById('speed-select'),
  moduleList: document.getElementById('module-list'),
  moduleItems: [],
  sceneName: document.getElementById('header-scene-name'),
  headerBuildLabel: document.getElementById('header-build-label'),
  sceneCountChip: document.getElementById('scene-count-chip'),
  compositionTitle: document.getElementById('composition-title'),
  compositionFilename: document.getElementById('composition-filename'),
  sceneListTitle: document.getElementById('scene-list-title'),
  sceneListSummary: document.getElementById('scene-list-summary'),
  validation: document.getElementById('validation-detail'),
  dialog: document.getElementById('spec-dialog'),
  dialogSpecName: document.getElementById('dialog-spec-name'),
  specOutput: document.getElementById('spec-output')
};

class SceneEngine {
  constructor() {
    this.timeline = gsap.timeline({ paused: true });
    this.instances = [];
    this.boundaries = [];
    this.spec = null;
    this.activeIndex = -1;
    this.scrubbing = false;
  }

  async load(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Unable to load the sample spec (${response.status}).`);
    const rawSpec = await response.json();
    const result = validateSpec(rawSpec, registry);
    this.spec = result.spec;
    this.renderCompositionMetadata(url);
    this.renderModuleList();
    dom.validation.textContent = `${this.spec.slides.length} scenes · ${result.warnings.length ? `${result.warnings.length} warnings` : 'no warnings'}`;
    dom.specOutput.textContent = JSON.stringify(rawSpec, null, 2);
    this.build();
    return result;
  }

  renderCompositionMetadata(url) {
    const filename = decodeURIComponent(url.split('?')[0].split('/').pop() || 'composition.json');
    const sceneCount = this.spec.slides.length;
    const sceneWord = sceneCount === 1 ? 'scene' : 'scenes';
    const title = this.spec.title || filename.replace(/\.json$/i, '').replace(/[-_]+/g, ' ');

    document.title = `${title} | MAV Physics`;
    dom.headerBuildLabel.textContent = 'Composition preview';
    dom.sceneCountChip.textContent = `${sceneCount} ${sceneWord}`;
    dom.compositionTitle.textContent = title;
    dom.compositionFilename.textContent = `composition / ${filename}`;
    dom.sceneListTitle.textContent = 'Composition scenes';
    dom.sceneListSummary.textContent = `${sceneCount} ${sceneWord} loaded from ${filename}.`;
    dom.dialogSpecName.textContent = filename;
  }

  renderModuleList() {
    const prettyName = scene => scene.replace('Scene_', '').replace(/([a-z])([A-Z])/g, '$1 $2');
    dom.moduleList.replaceChildren();
    this.spec.slides.forEach((slide, index) => {
      const button = document.createElement('button');
      button.className = `module-item${index === 0 ? ' active' : ''}`;
      button.type = 'button';
      button.dataset.sceneIndex = String(index);
      const icon = document.createElement('span');
      icon.className = `module-icon ${slide.iconClass || 'icon-phase3'}`;
      const glyph = document.createElement('i'); glyph.textContent = slide.icon || '◆'; icon.appendChild(glyph);
      const copy = document.createElement('span');
      const name = document.createElement('b'); name.textContent = slide.label || prettyName(slide.scene);
      const description = document.createElement('small'); description.textContent = slide.description || 'Reusable animation scene';
      copy.append(name, description);
      const number = document.createElement('em'); number.textContent = String(index + 1).padStart(2, '0');
      button.append(icon, copy, number);
      button.addEventListener('click', () => this.seekScene(index, true));
      dom.moduleList.appendChild(button);
    });
    dom.moduleItems = [...dom.moduleList.querySelectorAll('.module-item')];
  }

  build() {
    this.destroy();
    this.timeline = gsap.timeline({ paused: true, defaults: { overwrite: false } });
    let cursor = 0;
    this.spec.slides.forEach((slide, index) => {
      const ModuleClass = registry[slide.scene];
      const instance = new ModuleClass();
      instance.setup(dom.stage, slide.params);
      const sceneTimeline = instance.buildTimeline(slide.params);
      this.instances.push(instance);
      this.boundaries.push({ start: cursor, end: cursor + sceneTimeline.duration(), index, slide });
      // Scene modules return paused timelines by contract. Once nested, the
      // master timeline becomes their sole playback controller.
      this.timeline.add(sceneTimeline.paused(false), cursor);
      cursor += sceneTimeline.duration();
    });
    this.timeline.eventCallback('onUpdate', () => this.update());
    this.timeline.eventCallback('onComplete', () => this.setPlaying(false));
    this.timeline.seek(0.001, false).pause();
    this.update(true);
    dom.total.textContent = this.formatTime(this.timeline.duration());
    dom.loading.style.display = 'none';
    document.dispatchEvent(new CustomEvent('mav:ready', { detail: { duration: this.timeline.duration(), scenes: this.instances.length } }));
  }

  destroy() {
    this.timeline?.kill();
    this.instances.forEach(instance => instance.teardown());
    this.instances = [];
    this.boundaries = [];
    this.activeIndex = -1;
    narrator.reset();
  }

  playPause() {
    if (this.timeline.progress() >= .999) this.timeline.restart();
    else if (this.timeline.paused()) this.timeline.play();
    else this.timeline.pause();
    this.setPlaying(!this.timeline.paused());
  }

  setPlaying(playing) {
    dom.play.classList.toggle('playing', playing);
    dom.play.setAttribute('aria-label', playing ? 'Pause' : 'Play');
  }

  seekScene(index, autoplay = false) {
    const boundary = this.boundaries[index];
    if (!boundary) return;
    narrator.reset();
    this.seekTime(boundary.start + .02);
    if (autoplay) this.timeline.play();
    this.setPlaying(autoplay);
    this.update(true);
  }

  seekTime(time) {
    const target = Math.max(0, Math.min(this.timeline.duration(), Number(time) || 0));
    if (target < this.timeline.time()) this.timeline.seek(0).pause();
    this.timeline.seek(target, false).pause();
  }

  prepareExportFrame(time) {
    narrator.reset();
    this.seekTime(time);
    this.update(true);
    return {
      time: this.timeline.time(),
      duration: this.timeline.duration(),
      progress: this.timeline.progress(),
      sceneIndex: this.activeIndex
    };
  }

  update(force = false) {
    const time = this.timeline.time();
    const progress = this.timeline.duration() ? this.timeline.progress() : 0;
    if (!this.scrubbing) dom.range.value = Math.round(progress * 1000);
    dom.range.style.setProperty('--progress', `${progress * 100}%`);
    dom.current.textContent = this.formatTime(time);
    const boundary = this.boundaries.find(item => time >= item.start && (time < item.end || item.index === this.boundaries.length - 1));
    if (boundary && (force || boundary.index !== this.activeIndex)) {
      this.activeIndex = boundary.index;
      dom.moduleItems.forEach((item, index) => item.classList.toggle('active', index === boundary.index));
      const activeItem = dom.moduleItems[boundary.index];
      if (activeItem && dom.moduleList.scrollHeight > dom.moduleList.clientHeight) {
        const centered = activeItem.offsetTop - (dom.moduleList.clientHeight - activeItem.offsetHeight) / 2;
        dom.moduleList.scrollTo({ top: Math.max(0, centered), behavior: this.scrubbing ? 'auto' : 'smooth' });
      }
      dom.sceneName.textContent = boundary.slide.scene;
      narrator.present(boundary.slide, boundary.index);
    }
  }

  formatTime(seconds) {
    const min = Math.floor(seconds / 60).toString().padStart(2, '0');
    const sec = Math.floor(seconds % 60).toString().padStart(2, '0');
    return `${min}:${sec}`;
  }
}

const engine = new SceneEngine();
window.MAVEngine = engine;
window.MAVExport = {
  getMetadata: () => ({
    duration: engine.timeline.duration(),
    scenes: engine.instances.length,
    spec: engine.spec?.title || '',
    ready: Boolean(engine.spec && engine.instances.length)
  }),
  seek: time => engine.prepareExportFrame(time)
};

function resizeStage() {
  const scale = exportMode ? 1 : dom.viewport.clientWidth / 1920;
  dom.stage.style.transform = `scale(${scale})`;
}

new ResizeObserver(resizeStage).observe(dom.viewport);
resizeStage();

dom.play.addEventListener('click', () => engine.playPause());
dom.restart.addEventListener('click', () => { narrator.reset(); engine.timeline.restart(); engine.setPlaying(true); });
dom.mute.addEventListener('click', () => {
  const enabled = narrator.toggle();
  dom.mute.textContent = enabled ? '🔊' : 'Aa';
  dom.mute.title = enabled ? 'Voice narration on' : 'Voice narration off';
  if (enabled && engine.activeIndex >= 0) { narrator.lastIndex = -1; narrator.present(engine.spec.slides[engine.activeIndex], engine.activeIndex); }
});
dom.speed.addEventListener('change', () => engine.timeline.timeScale(Number(dom.speed.value)));
dom.range.addEventListener('input', event => {
  engine.scrubbing = true;
  engine.seekTime(engine.timeline.duration() * Number(event.target.value) / 1000);
  engine.setPlaying(false);
  engine.update(true);
});
dom.range.addEventListener('change', () => { engine.scrubbing = false; });
document.getElementById('spec-button').addEventListener('click', () => dom.dialog.showModal());
document.getElementById('close-spec-button').addEventListener('click', () => dom.dialog.close());
dom.dialog.addEventListener('click', event => { if (event.target === dom.dialog) dom.dialog.close(); });
document.addEventListener('keydown', event => {
  if (event.code === 'Space' && !['INPUT','TEXTAREA','SELECT','BUTTON'].includes(document.activeElement.tagName)) { event.preventDefault(); engine.playPause(); }
  if (event.code === 'ArrowRight') engine.seekScene(Math.min(engine.activeIndex + 1, engine.boundaries.length - 1), false);
  if (event.code === 'ArrowLeft') engine.seekScene(Math.max(engine.activeIndex - 1, 0), false);
});

const sampleSpecUrl = query.get('spec') || document.body.dataset.specUrl || 'specs/phase-one-showcase.json';

engine.load(sampleSpecUrl).catch(error => {
  console.error(error);
  dom.loading.innerHTML = `<strong>Preview could not start</strong><span>${error.message}</span>`;
  dom.loading.style.color = '#ff5a36';
});
