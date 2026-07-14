import { append, clamp, el, finishPhase3, phase3Root, phase3Timeline, schemas } from './_shared.js';

const SPEEDS = { low: .38, medium: .72, high: 1.15 };

export class Scene_ElectronFlow {
  setup(container, params) {
    const frame = phase3Root(container, 'Scene_ElectronFlow', 'Charge transport', `${params.current} current through a conductor`, 'Electron drift and lattice collisions reveal how resistance produces heating.', 'scene-electron-flow');
    this.root = frame.root;
    this.panel = el('section', 'p3-wire-panel');
    this.wire = el('div', 'p3-wire'); this.wire.style.setProperty('--wire-length', `${clamp(params.wireLength * 1.5, 750, 1250)}px`);
    this.electrons = [];
    for (let index = 0; index < params.electronCount; index++) {
      const electron = el('i', 'p3-electron-dot');
      electron.dataset.offset = String(index / params.electronCount);
      electron.style.top = `${18 + (index * 37 % 230)}px`;
      this.electrons.push(electron); this.wire.appendChild(electron);
    }
    this.resistance = null;
    if (params.showResistanceZone) {
      this.resistance = el('div', 'p3-resistance-zone');
      for (let index = 0; index < 18; index++) { const ion = el('i'); ion.style.left = `${12 + index % 6 * 42}px`; ion.style.top = `${18 + Math.floor(index / 6) * 83}px`; this.resistance.appendChild(ion); }
      append(this.resistance, el('span', '', { text: 'resistance zone' })); this.wire.appendChild(this.resistance);
    }
    this.flow = el('aside', 'p3-current-readout');
    append(this.flow, el('small', '', { text: 'conventional current' }), el('strong', '', { text: '→' }), el('span', '', { text: 'electron drift ←' }));
    append(this.panel, this.wire, this.flow); this.root.appendChild(this.panel);
  }
  update(progress, params) {
    const speed = SPEEDS[params.current];
    this.electrons.forEach((electron, index) => {
      let ratio = (Number(electron.dataset.offset) - progress * speed + 3) % 1;
      if (params.showResistanceZone && ratio > .48 && ratio < .72) ratio = .48 + (ratio - .48) * .55;
      electron.style.left = `${ratio * 100}%`; electron.style.opacity = String(.55 + (index % 4) * .12);
    });
  }
  buildTimeline(params) {
    const state = { progress: 0 }; this.update(0, params);
    const tl = phase3Timeline(this.root);
    tl.fromTo(this.panel, { y: 26, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .3)
      .fromTo(this.wire, { scaleX: .72 }, { scaleX: 1, duration: .65 }, .55)
      .fromTo(this.electrons, { scale: 0, autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: .25, stagger: .025 }, .9)
      .fromTo(this.flow, { x: 28, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: .45 }, 1.15)
      .to(state, { progress: 5, duration: 4.4, ease: 'none', onUpdate: () => this.update(state.progress, params) }, 1.2);
    if (this.resistance) tl.to(this.resistance.querySelectorAll('i'), { x: 4, y: -3, duration: .07, repeat: 22, yoyo: true }, 1.35);
    return finishPhase3(tl, this.root, params, 6.5);
  }
  teardown() { this.root?.remove(); }
  static getParamSchema() { return { type: 'object', additionalProperties: false, properties: { wireLength: schemas.positive(800, 1000), electronCount: { type: 'integer', minimum: 5, maximum: 40, default: 20 }, current: { type: 'string', enum: ['high', 'medium', 'low'], default: 'medium' }, showResistanceZone: schemas.toggle(true) } }; }
}
