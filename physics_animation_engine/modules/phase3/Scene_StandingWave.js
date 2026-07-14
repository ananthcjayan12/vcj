import { append, clamp, finishPhase3, phase3Root, phase3Timeline, pointLabel, schemas, svg, svgEl } from './_shared.js';

export class Scene_StandingWave {
  setup(container, params) {
    const frame = phase3Root(container, 'Scene_StandingWave', 'Superposition', `Standing wave · harmonic ${params.harmonic}`, `${params.harmonic} loop${params.harmonic === 1 ? '' : 's'} form between fixed endpoints.`, 'scene-standing-wave');
    this.root = frame.root; this.harmonic = clamp(Math.round(params.harmonic), 1, 6);
    this.card = document.createElement('section'); this.card.className = 'p3-wave-card';
    this.diagram = svg('p3-standing-svg', '0 0 1420 700');
    this.startX = 170; this.length = clamp(params.stringLength * 1.45, 650, 1050); this.y = 350; this.amplitude = 145;
    this.string = svgEl('path', { class: 'p3-standing-string' });
    append(this.diagram,
      svgEl('line', { x1: this.startX, y1: 130, x2: this.startX, y2: 570, class: 'p3-string-support' }),
      svgEl('line', { x1: this.startX + this.length, y1: 130, x2: this.startX + this.length, y2: 570, class: 'p3-string-support' }),
      svgEl('line', { x1: this.startX, y1: this.y, x2: this.startX + this.length, y2: this.y, class: 'p3-equilibrium-line' }),
      this.string
    );
    this.nodes = [];
    if (params.showNodes) for (let index = 0; index <= this.harmonic; index++) {
      const x = this.startX + this.length * index / this.harmonic;
      const node = svgEl('circle', { cx: x, cy: this.y, r: 9, class: 'p3-wave-node' }); this.nodes.push(node); this.diagram.appendChild(node);
    }
    this.antinodes = [];
    if (params.showAntinodes) for (let index = 0; index < this.harmonic; index++) {
      const x = this.startX + this.length * (index + .5) / this.harmonic;
      const marker = pointLabel(x, 150 + (index % 2) * 400, `A${index + 1}`, 'p3-antinode-label'); this.antinodes.push(marker); this.diagram.appendChild(marker);
    }
    append(this.diagram, pointLabel(710, 635, `λ = ${Math.round(params.stringLength * 2 / this.harmonic)} units`, 'p3-motion-stat'));
    this.card.appendChild(this.diagram); this.root.appendChild(this.card); this.update(0);
  }
  update(phase) {
    let d = '';
    for (let index = 0; index <= 120; index++) {
      const ratio = index / 120, x = this.startX + ratio * this.length;
      const y = this.y - this.amplitude * Math.sin(this.harmonic * Math.PI * ratio) * Math.sin(phase);
      d += `${index ? 'L' : 'M'}${x} ${y}`;
    }
    this.string.setAttribute('d', d);
  }
  buildTimeline(params) {
    const state = { phase: 0 }, tl = phase3Timeline(this.root);
    tl.fromTo(this.card, { y: 28, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .3)
      .fromTo([this.string, ...this.nodes], { autoAlpha: 0 }, { autoAlpha: 1, duration: .45, stagger: .04 }, .7)
      .fromTo(this.antinodes, { y: 12, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .35, stagger: .1 }, 1.05)
      .to(state, { phase: Math.PI * 6, duration: 4.4, ease: 'none', onUpdate: () => this.update(state.phase) }, 1.15);
    return finishPhase3(tl, this.root, params, 6.5);
  }
  teardown() { this.root?.remove(); }
  static getParamSchema() { return { type: 'object', additionalProperties: false, properties: { harmonic: { type: 'integer', minimum: 1, maximum: 6, default: 1 }, stringLength: schemas.positive(600, 800), showNodes: schemas.toggle(true), showAntinodes: schemas.toggle(true) } }; }
}
