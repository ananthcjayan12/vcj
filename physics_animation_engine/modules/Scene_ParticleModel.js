import { append, duration, el, finishTimeline, root } from '../engine/renderer.js';

function seeded(index, salt = 1) { return ((Math.sin(index * 9283.31 + salt * 77.7) + 1) / 2); }

export class Scene_ParticleModel {
  setup(container, params) {
    this.params = params;
    this.root = root(container, 'Scene_ParticleModel', 'scene-particlemodel');
    const header = el('div', 'pm-header');
    append(header, el('span', 'scene-kicker', { text: 'Kinetic particle model' }), el('h2', '', { text: `${params.state[0].toUpperCase() + params.state.slice(1)} → ${params.transitionTo ? params.transitionTo[0].toUpperCase() + params.transitionTo.slice(1) : params.state}` }), el('p', '', { text: 'Particle spacing and speed reveal the state of matter' }));
    this.container = el('div', `pm-container pm-${params.containerType}`);
    this.particleLayer = el('div', 'pm-particle-layer');
    this.particles = [];
    for (let i = 0; i < params.particleCount; i++) {
      const dot = el('i', 'pm-particle'); dot.dataset.index = i; this.particles.push(dot); this.particleLayer.appendChild(dot);
    }
    append(this.container, el('span', 'pm-glass-shine'), this.particleLayer);
    this.stateLabel = el('div', 'pm-state-label', { html: `<small>Current state</small><strong>${params.state}</strong>` });
    this.energy = el('div', 'pm-energy', { html: `<small>Particle energy</small><span><i></i><i></i><i></i><i></i><i></i></span><b>${params.temperature}</b>` });
    const notes = el('div', 'pm-notes');
    append(notes, el('div', '', { html: '<i class="pm-note-icon">↔</i><span><small>Spacing</small><b>Changes with state</b></span>' }), el('div', '', { html: '<i class="pm-note-icon">⌁</i><span><small>Motion</small><b>Increases with energy</b></span>' }));
    append(this.root, header, this.container, this.stateLabel, params.showEnergyLabel ? this.energy : null, notes);
    this.motion = { progress: 0 }; this.layout(params.state, 0);
  }

  positionFor(state, i, progress) {
    const width = 750, height = 560, count = this.params.particleCount;
    if (state === 'solid') {
      const cols = Math.ceil(Math.sqrt(count * 1.3)); const rows = Math.ceil(count / cols); const gap = Math.min(47, 610 / Math.max(1, cols - 1));
      return { x: 70 + (i % cols) * gap, y: height - 70 - (rows - 1 - Math.floor(i / cols)) * gap };
    }
    if (state === 'liquid') return { x: 45 + seeded(i, 2) * (width - 90), y: height * .53 + seeded(i, 3) * height * .38 };
    const speed = { low: .5, medium: 1, high: 1.8 }[this.params.temperature] || 1;
    const px = (seeded(i, 4) + progress * speed * (.35 + seeded(i, 5))) % 1;
    const py = (seeded(i, 6) + progress * speed * (.28 + seeded(i, 7))) % 1;
    const bounce = n => 1 - Math.abs((n * 2 % 2) - 1);
    return { x: 35 + bounce(px) * (width - 70), y: 35 + bounce(py) * (height - 70) };
  }

  layout(state, progress) {
    const target = this.params.transitionTo || state;
    const mix = this.params.transitionTo ? Math.min(1, Math.max(0, (progress - .45) / .45)) : 0;
    this.particles.forEach((dot, i) => {
      const start = this.positionFor(state, i, progress); const end = this.positionFor(target, i, progress);
      const jitter = state === 'solid' ? Math.sin(progress * 80 + i) * 3 : Math.sin(progress * 19 + i) * 6;
      dot.style.transform = `translate(${start.x + (end.x - start.x) * mix + jitter}px, ${start.y + (end.y - start.y) * mix + jitter * .6}px)`;
    });
    if (mix > .55) this.stateLabel.querySelector('strong').textContent = target;
    else this.stateLabel.querySelector('strong').textContent = state;
  }

  buildTimeline(params) {
    const seconds = duration(params, 7);
    const energyBars = this.energy?.querySelectorAll('span i') || [];
    const activeBars = { low: 2, medium: 3, high: 5 }[params.temperature] || 3;
    [...energyBars].forEach((bar, index) => bar.classList.toggle('active', index < activeBars));
    const tl = gsap.timeline({ paused: true });
    tl.set(this.root, { autoAlpha: 1 }, 0)
      .fromTo(this.root.querySelector('.pm-header'), { y: -22, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .6 }, .08)
      .fromTo(this.container, { scaleY: 0, transformOrigin: 'bottom' }, { scaleY: 1, duration: .72, ease: 'power3.out' }, .12)
      .fromTo(this.particles, { scale: 0, autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: .35, stagger: .018, ease: 'back.out(1.7)' }, .48)
      .fromTo([this.stateLabel, this.energy].filter(Boolean), { x: 20, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: .48, stagger: .17 }, .78)
      .fromTo(this.root.querySelector('.pm-notes'), { y: 20, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .5 }, 1.15)
      .to(this.motion, { progress: 1, duration: seconds - .55, ease: 'none', onUpdate: () => this.layout(params.state, this.motion.progress) }, .45);
    if (params.transitionTo) tl.to(this.stateLabel, { color: '#39ff14', duration: .35, yoyo: true, repeat: 1 }, seconds * .62);
    return finishTimeline(tl, this.root, seconds);
  }

  teardown() { this.root?.remove(); }

  static getParamSchema() {
    return { type: 'object', required: ['state'], additionalProperties: false, properties: {
      state: { type: 'string', enum: ['solid','liquid','gas'], default: 'solid' }, temperature: { type: 'string', enum: ['low','medium','high'], default: 'medium' },
      containerType: { type: 'string', enum: ['box','beaker','cylinder'], default: 'box' }, particleCount: { type: 'integer', minimum: 20, maximum: 80, default: 40 },
      showEnergyLabel: { type: 'boolean', default: true }, transitionTo: { type: 'string', enum: ['solid','liquid','gas'], default: '' }
    }};
  }
}
