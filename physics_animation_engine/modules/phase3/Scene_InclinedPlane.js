import { addArrowMarker, append, clamp, drawPaths, finishPhase3, phase3Root, phase3Timeline, pointLabel, schemas, svg, svgEl } from './_shared.js';

export class Scene_InclinedPlane {
  setup(container, params) {
    const frame = phase3Root(container, 'Scene_InclinedPlane', 'Resolved forces', 'Block on an inclined plane', `${params.mass} kg block · ${params.angle}° slope · friction coefficient ${params.friction}`, 'scene-inclined-plane');
    this.root = frame.root;
    this.card = document.createElement('section'); this.card.className = 'p3-motion-card';
    this.diagram = svg('p3-incline-svg', '0 0 1420 700');
    addArrowMarker(this.diagram, 'p3-incline-force', '#ff5a36');
    addArrowMarker(this.diagram, 'p3-incline-component', '#ffd23f');
    const angle = clamp(params.angle, 5, 55) * Math.PI / 180;
    const start = { x: 245, y: 560 }, run = 850, rise = Math.tan(angle) * run;
    const end = { x: start.x + run, y: start.y - rise };
    this.surface = svgEl('path', { d: `M${start.x} ${start.y} L${end.x} ${end.y} L${end.x} ${start.y} Z`, class: 'p3-incline-surface' });
    const blockDistance = .58, bx = start.x + run * blockDistance, by = start.y - rise * blockDistance - 48;
    this.block = svgEl('g', { class: 'p3-incline-block', transform: `translate(${bx} ${by}) rotate(${-params.angle})` });
    append(this.block, svgEl('rect', { x: -70, y: -48, width: 140, height: 96, rx: 14 }), pointLabel(0, 8, `${params.mass} kg`, 'p3-block-label'));
    this.weight = svgEl('line', { x1: bx, y1: by, x2: bx, y2: by + 190, class: 'p3-incline-vector weight', 'marker-end': 'url(#p3-incline-force)' });
    this.parallel = svgEl('line', { x1: bx, y1: by, x2: bx - 150 * Math.cos(angle), y2: by + 150 * Math.sin(angle), class: 'p3-incline-vector component', 'marker-end': 'url(#p3-incline-component)' });
    this.normal = svgEl('line', { x1: bx, y1: by, x2: bx + 120 * Math.sin(angle), y2: by - 120 * Math.cos(angle), class: 'p3-incline-vector normal', 'marker-end': 'url(#p3-incline-component)' });
    this.friction = svgEl('line', { x1: bx, y1: by - 22, x2: bx + 125 * Math.cos(angle), y2: by - 22 - 125 * Math.sin(angle), class: 'p3-incline-vector friction', 'marker-end': 'url(#p3-incline-force)' });
    if (!params.showDecomposedWeight) { this.parallel.classList.add('is-hidden'); this.normal.classList.add('is-hidden'); }
    append(this.diagram, this.surface, this.block, this.weight, this.parallel, this.normal, this.friction,
      pointLabel(bx + 32, by + 205, 'mg', 'p3-vector-label'),
      pointLabel(bx - 120, by + 100, 'mg sin θ', 'p3-vector-label'),
      pointLabel(bx + 135, by - 78, 'N', 'p3-vector-label'),
      pointLabel(1180, 590, `θ = ${params.angle}°`, 'p3-motion-stat')
    );
    this.card.appendChild(this.diagram); this.root.appendChild(this.card);
  }
  buildTimeline(params) {
    const tl = phase3Timeline(this.root);
    tl.fromTo(this.card, { y: 28, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .3)
      .fromTo(this.block, { y: -90, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .6, ease: 'bounce.out' }, .95);
    drawPaths(tl, [this.surface], .55, .8, 0);
    drawPaths(tl, [this.weight, this.parallel, this.normal, this.friction].filter(node => !node.classList.contains('is-hidden')), 1.45, .7, .15);
    tl.fromTo(this.diagram.querySelectorAll('.p3-vector-label'), { y: 8, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .35, stagger: .1 }, 2.05);
    return finishPhase3(tl, this.root, params, 6);
  }
  teardown() { this.root?.remove(); }
  static getParamSchema() { return { type: 'object', additionalProperties: false, properties: { angle: { type: 'number', minimum: 5, maximum: 55, default: 30 }, mass: schemas.positive(5, 100), friction: { type: 'number', minimum: 0, maximum: 1.5, default: .3 }, showDecomposedWeight: schemas.toggle(true) } }; }
}
