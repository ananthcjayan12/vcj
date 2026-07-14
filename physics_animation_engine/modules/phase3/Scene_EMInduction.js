import { append, clamp, drawPaths, el, finishPhase3, phase3Root, phase3Timeline, pointLabel, schemas, svg, svgEl } from './_shared.js';

const RATE = { slow: 1, medium: 1.7, fast: 2.6 };

export class Scene_EMInduction {
  setup(container, params) {
    const frame = phase3Root(container, 'Scene_EMInduction', 'Changing magnetic flux', 'Electromagnetic induction', `${params.method.replaceAll('_', ' ')} · ${params.speed} motion`, 'scene-em-induction');
    this.root = frame.root;
    this.card = el('section', 'p3-induction-card');
    this.diagram = svg('p3-induction-svg', '0 0 1420 700');
    this.coil = svgEl('g', { class: 'p3-induction-coil' });
    for (let index = 0; index < 8; index++) this.coil.appendChild(svgEl('ellipse', { cx: 720 + index * 28, cy: 315, rx: 35, ry: 125 }));
    this.magnet = svgEl('g', { class: 'p3-induction-magnet' });
    append(this.magnet, svgEl('rect', { x: 225, y: 255, width: 300, height: 120, rx: 16 }), svgEl('rect', { x: 225, y: 255, width: 150, height: 120, rx: 16, class: 'north' }), pointLabel(300, 330, 'N', 'p3-pole-label'), pointLabel(450, 330, 'S', 'p3-pole-label'));
    this.fieldLines = [0,1,2,3].map(index => svgEl('path', { d: `M375 ${275 + index * 28} C520 ${245 + index * 40}, 650 ${245 + index * 40}, 760 ${285 + index * 20}`, class: 'p3-induction-field' }));
    this.needle = svgEl('line', { x1: 1135, y1: 315, x2: 1135, y2: 230, class: 'p3-meter-needle' });
    this.graphPath = svgEl('path', { class: 'p3-emf-graph' });
    append(this.diagram, ...this.fieldLines, this.magnet, this.coil,
      svgEl('circle', { cx: 1135, cy: 315, r: 120, class: 'p3-galvanometer' }), this.needle, pointLabel(1135, 470, 'galvanometer', 'p3-svg-label'),
      svgEl('rect', { x: 860, y: 520, width: 510, height: 120, rx: 12, class: 'p3-emf-plot' }), this.graphPath
    );
    if (!params.showGalvanometer) { this.needle.classList.add('is-hidden'); this.diagram.querySelector('.p3-galvanometer').classList.add('is-hidden'); }
    this.card.appendChild(this.diagram); this.root.appendChild(this.card);
  }
  update(progress, params) {
    const wave = Math.sin(progress * Math.PI * 2 * RATE[params.speed]);
    if (params.method === 'magnet_in_coil') this.magnet.setAttribute('transform', `translate(${190 + wave * 105} 0)`);
    else this.coil.setAttribute('transform', `rotate(${progress * 720 * RATE[params.speed]} 820 315)`);
    this.needle.setAttribute('transform', `rotate(${wave * 48} 1135 315)`);
    let d = 'M880 580';
    for (let index = 0; index <= 50; index++) d += ` L${880 + index * 9.2} ${580 - Math.sin(index / 50 * Math.PI * 4 * RATE[params.speed]) * 38}`;
    this.graphPath.setAttribute('d', d);
  }
  buildTimeline(params) {
    const state = { progress: 0 }, tl = phase3Timeline(this.root); this.update(0, params);
    tl.fromTo(this.card, { y: 25, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .3)
      .fromTo([this.magnet, this.coil], { autoAlpha: 0, scale: .85, transformOrigin: 'center' }, { autoAlpha: 1, scale: 1, duration: .55, stagger: .12 }, .65)
      .fromTo(this.needle, { autoAlpha: 0 }, { autoAlpha: params.showGalvanometer ? 1 : 0, duration: .35 }, 1.05)
      .to(state, { progress: 1, duration: 4.25, ease: 'none', onUpdate: () => this.update(state.progress, params) }, 1.25);
    drawPaths(tl, this.fieldLines, 1.0, .8, .08);
    return finishPhase3(tl, this.root, params, 6.5);
  }
  teardown() { this.root?.remove(); }
  static getParamSchema() { return { type: 'object', additionalProperties: false, properties: { method: { type: 'string', enum: ['magnet_in_coil', 'rotating_coil'], default: 'magnet_in_coil' }, speed: { type: 'string', enum: ['slow', 'medium', 'fast'], default: 'medium' }, showGalvanometer: schemas.toggle(true) } }; }
}
