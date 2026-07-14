import { addArrowMarker, append, drawPaths, finishPhase3, phase3Root, phase3Timeline, pointLabel, schemas, svg, svgEl } from './_shared.js';

export class Scene_MotorEffect {
  setup(container, params) {
    const wireSign = params.wireDirection === 'out_of_page' ? 1 : -1, fieldSign = params.fieldDirection === 'right' ? 1 : -1;
    this.forceUp = wireSign * fieldSign > 0;
    const frame = phase3Root(container, 'Scene_MotorEffect', 'Force on a current', 'The motor effect', `Current ${params.wireDirection.replaceAll('_', ' ')} · field points ${params.fieldDirection} · force is ${this.forceUp ? 'up' : 'down'}.`, 'scene-motor-effect');
    this.root = frame.root;
    this.card = document.createElement('section'); this.card.className = 'p3-field-card';
    this.diagram = svg('p3-motor-svg', '0 0 1420 700');
    addArrowMarker(this.diagram, 'p3-field-direction', '#00f5ff'); addArrowMarker(this.diagram, 'p3-motor-force', '#ff5a36');
    this.fieldLines = [];
    for (let index = 0; index < 7; index++) {
      const y = 140 + index * 72, right = params.fieldDirection === 'right';
      this.fieldLines.push(svgEl('line', { x1: right ? 150 : 1270, y1: y, x2: right ? 1270 : 150, y2: y, class: 'p3-motor-field-line', 'marker-end': 'url(#p3-field-direction)' }));
    }
    this.wire = svgEl('g', { class: 'p3-motor-wire' });
    append(this.wire, svgEl('circle', { cx: 710, cy: 350, r: 72 }), pointLabel(710, 366, params.wireDirection === 'out_of_page' ? '•' : '×', 'p3-wire-sign'));
    this.force = svgEl('line', { x1: 710, y1: 350, x2: 710, y2: this.forceUp ? 145 : 555, class: 'p3-motor-force', 'marker-end': 'url(#p3-motor-force)' });
    if (!params.showForceDirection) this.force.classList.add('is-hidden');
    append(this.diagram, ...this.fieldLines, this.wire, this.force, pointLabel(710, this.forceUp ? 115 : 600, 'FORCE', 'p3-force-label'));
    this.rule = null;
    if (params.showRule === 'flemings_left') {
      this.rule = document.createElement('aside'); this.rule.className = 'p3-fleming-card';
      append(this.rule, document.createTextNode('Fleming’s left hand'), document.createElement('span'));
      this.rule.querySelector('span').innerHTML = '<i>First</i> field · <i>seCond</i> current · <i>thuMb</i> motion';
    }
    this.card.appendChild(this.diagram); if (this.rule) this.card.appendChild(this.rule); this.root.appendChild(this.card);
  }
  buildTimeline(params) {
    const tl = phase3Timeline(this.root);
    tl.fromTo(this.card, { y: 25, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .3);
    drawPaths(tl, this.fieldLines, .62, 1.0, .07);
    tl.fromTo(this.wire, { scale: .5, autoAlpha: 0, transformOrigin: 'center' }, { scale: 1, autoAlpha: 1, duration: .55, ease: 'back.out(1.8)' }, 1.25);
    if (!this.force.classList.contains('is-hidden')) drawPaths(tl, [this.force], 1.72, .65, 0);
    if (this.rule) tl.fromTo(this.rule, { x: 28, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: .48 }, 2.15);
    return finishPhase3(tl, this.root, params, 6);
  }
  teardown() { this.root?.remove(); }
  static getParamSchema() { return { type: 'object', additionalProperties: false, properties: { wireDirection: { type: 'string', enum: ['into_page', 'out_of_page'], default: 'into_page' }, fieldDirection: { type: 'string', enum: ['left', 'right'], default: 'right' }, showForceDirection: schemas.toggle(true), showRule: { type: 'string', enum: ['flemings_left', 'none'], default: 'flemings_left' } } }; }
}
