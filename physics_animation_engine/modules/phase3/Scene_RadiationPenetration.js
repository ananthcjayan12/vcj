import { append, drawPaths, finishPhase3, phase3Root, phase3Timeline, pointLabel, schemas, svg, svgEl } from './_shared.js';

const STOP = { alpha: 'paper', beta: 'aluminium', gamma: 'concrete' };
const COLORS = { alpha: '#ffd23f', beta: '#00f5ff', gamma: '#39ff14' };

export class Scene_RadiationPenetration {
  setup(container, params) {
    const frame = phase3Root(container, 'Scene_RadiationPenetration', 'Comparative penetration', 'Alpha, beta, and gamma range', 'Each beam is stopped by the first suitable material in the configured barrier stack.', 'scene-radiation-penetration');
    this.root = frame.root;
    this.card = document.createElement('section'); this.card.className = 'p3-radiation-card';
    this.diagram = svg('p3-radiation-svg', '0 0 1420 700');
    const barrierX = { paper: 570, aluminium: 790, lead: 1010, concrete: 1230 };
    this.barriers = params.barriers.map(material => {
      const width = { paper: 18, aluminium: 42, lead: 72, concrete: 110 }[material] || 35;
      const rect = svgEl('rect', { x: barrierX[material] - width / 2, y: 100, width, height: 480, rx: 8, class: `p3-penetration-barrier is-${material}` });
      append(this.diagram, rect, pointLabel(barrierX[material], 625, material, 'p3-barrier-label'));
      return rect;
    });
    this.beams = params.radiationTypes.map((type, index) => {
      const y = 205 + index * 135, stopMaterial = STOP[type], stopX = barrierX[stopMaterial] || 1320;
      const beam = svgEl('line', { x1: 150, y1: y, x2: stopX - 15, y2: y, class: `p3-radiation-beam is-${type}`, stroke: COLORS[type] });
      append(this.diagram, pointLabel(95, y + 8, type[0].toUpperCase(), `p3-radiation-symbol is-${type}`), beam, pointLabel(stopX - 35, y - 24, '×', 'p3-stop-mark'));
      if (params.showRange) this.diagram.appendChild(pointLabel((150 + stopX) / 2, y - 22, `${type} range`, 'p3-range-label'));
      return beam;
    });
    this.card.appendChild(this.diagram); this.root.appendChild(this.card);
  }
  buildTimeline(params) {
    const tl = phase3Timeline(this.root);
    tl.fromTo(this.card, { y: 25, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .3)
      .fromTo(this.barriers, { scaleY: 0, transformOrigin: 'bottom', autoAlpha: 0 }, { scaleY: 1, autoAlpha: 1, duration: .5, stagger: .1 }, .65);
    drawPaths(tl, this.beams, 1.15, 1.25, .2);
    tl.fromTo(this.diagram.querySelectorAll('.p3-stop-mark,.p3-range-label'), { y: 10, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .35, stagger: .08 }, 2.35);
    return finishPhase3(tl, this.root, params, 6.2);
  }
  teardown() { this.root?.remove(); }
  static getParamSchema() { return { type: 'object', required: ['radiationTypes','barriers'], additionalProperties: false, properties: { radiationTypes: { type: 'array', minItems: 1, maxItems: 3, default: ['alpha','beta','gamma'], items: { type: 'string', enum: ['alpha','beta','gamma'], default: 'alpha' } }, barriers: { type: 'array', minItems: 1, maxItems: 4, default: ['paper','aluminium','lead','concrete'], items: { type: 'string', enum: ['paper','aluminium','lead','concrete'], default: 'paper' } }, showRange: schemas.toggle(true) } }; }
}
