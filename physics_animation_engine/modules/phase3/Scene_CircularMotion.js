import { addArrowMarker, append, clamp, finishPhase3, phase3Root, phase3Timeline, pointLabel, schemas, svg, svgEl } from './_shared.js';

export class Scene_CircularMotion {
  setup(container, params) {
    const frame = phase3Root(container, 'Scene_CircularMotion', 'Changing velocity', 'Uniform circular motion', 'The inward force changes direction continuously while speed can remain constant.', 'scene-circular-motion');
    this.root = frame.root;
    this.card = document.createElement('section'); this.card.className = 'p3-motion-card';
    this.diagram = svg('p3-circular-svg', '0 0 1420 700');
    addArrowMarker(this.diagram, 'p3-circular-force-arrow', '#ff5a36');
    addArrowMarker(this.diagram, 'p3-circular-velocity-arrow', '#00f5ff');
    this.cx = 710; this.cy = 345; this.radius = clamp(params.radius * 1.55, 150, 300);
    this.orbit = svgEl('ellipse', { cx: this.cx, cy: this.cy, rx: this.radius, ry: this.radius, class: 'p3-orbit-ring' });
    this.body = svgEl('circle', { r: 23, class: 'p3-orbit-body' });
    this.force = svgEl('line', { class: 'p3-orbit-vector force', 'marker-end': 'url(#p3-circular-force-arrow)' });
    this.velocity = svgEl('line', { class: 'p3-orbit-vector velocity', 'marker-end': 'url(#p3-circular-velocity-arrow)' });
    if (!params.showCentripetalForce) this.force.classList.add('is-hidden');
    if (!params.showVelocityTangent) this.velocity.classList.add('is-hidden');
    append(this.diagram,
      this.orbit, svgEl('circle', { cx: this.cx, cy: this.cy, r: 58, class: 'p3-central-body' }),
      pointLabel(this.cx, this.cy + 7, 'centre', 'p3-centre-label'), this.force, this.velocity, this.body,
      pointLabel(250, 620, `radius ${params.radius}`, 'p3-motion-stat'),
      pointLabel(710, 620, `speed ${params.speed}`, 'p3-motion-stat'),
      pointLabel(1160, 620, 'a = v² / r', 'p3-motion-stat')
    );
    this.card.appendChild(this.diagram); this.root.appendChild(this.card);
  }
  update(angle) {
    const x = this.cx + Math.cos(angle) * this.radius, y = this.cy + Math.sin(angle) * this.radius;
    this.body.setAttribute('cx', x); this.body.setAttribute('cy', y);
    this.force.setAttribute('x1', x); this.force.setAttribute('y1', y); this.force.setAttribute('x2', x + (this.cx - x) * .42); this.force.setAttribute('y2', y + (this.cy - y) * .42);
    const tangent = 105;
    this.velocity.setAttribute('x1', x); this.velocity.setAttribute('y1', y); this.velocity.setAttribute('x2', x - Math.sin(angle) * tangent); this.velocity.setAttribute('y2', y + Math.cos(angle) * tangent);
  }
  buildTimeline(params) {
    const state = { angle: -.65 * Math.PI }; this.update(state.angle);
    const tl = phase3Timeline(this.root);
    const orbitLength = this.orbit.getTotalLength(); gsap.set(this.orbit, { strokeDasharray: orbitLength, strokeDashoffset: orbitLength });
    tl.fromTo(this.card, { scale: .96, autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: .55 }, .3)
      .to(this.orbit, { strokeDashoffset: 0, duration: 1.0 }, .55)
      .fromTo(this.body, { scale: 0, transformOrigin: 'center' }, { scale: 1, duration: .38, ease: 'back.out(2)' }, .9);
    const visibleVectors = [this.force, this.velocity].filter(node => !node.classList.contains('is-hidden'));
    if (visibleVectors.length) tl.fromTo(visibleVectors, { autoAlpha: 0 }, { autoAlpha: 1, duration: .35 }, 1.15);
    tl.to(state, { angle: state.angle + Math.PI * 2 * clamp(params.speed / 2, 1.2, 3), duration: 4.3, ease: 'none', onUpdate: () => this.update(state.angle) }, 1.25);
    return finishPhase3(tl, this.root, params, 6.5);
  }
  teardown() { this.root?.remove(); }
  static getParamSchema() { return { type: 'object', additionalProperties: false, properties: { radius: schemas.positive(150, 300), speed: schemas.positive(3, 10), showCentripetalForce: schemas.toggle(true), showVelocityTangent: schemas.toggle(true) } }; }
}
