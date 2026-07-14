import { addArrowMarker, append, clamp, finishPhase3, phase3Root, phase3Timeline, pointLabel, schemas, svg, svgEl } from './_shared.js';

export class Scene_OrbitalMotion {
  setup(container, params) {
    const frame = phase3Root(container, 'Scene_OrbitalMotion', 'Gravity in space', `${params.orbitingBody} orbiting ${params.centralBody}`, params.isElliptical ? 'An elliptical path changes orbital speed and distance.' : 'A circular orbit balances tangential velocity with inward acceleration.', 'scene-orbital-motion');
    this.root = frame.root;
    this.card = document.createElement('section'); this.card.className = 'p3-space-card';
    this.diagram = svg('p3-orbital-svg', '0 0 1420 700');
    addArrowMarker(this.diagram, 'p3-gravity-arrow', '#ff5a36'); addArrowMarker(this.diagram, 'p3-orbit-velocity', '#00f5ff');
    this.cx = 710; this.cy = 350; this.rx = clamp(params.orbitRadius * 1.35, 250, 430); this.ry = params.isElliptical ? this.rx * .58 : this.rx;
    this.orbit = svgEl('ellipse', { cx: this.cx, cy: this.cy, rx: this.rx, ry: this.ry, class: 'p3-space-orbit' });
    this.body = svgEl('g', { class: 'p3-central-space-body' });
    append(this.body, svgEl('circle', { cx: this.cx, cy: this.cy, r: 78 }), pointLabel(this.cx, this.cy + 8, params.centralBody, 'p3-space-label'));
    this.satellite = svgEl('g', { class: 'p3-satellite' });
    append(this.satellite, svgEl('rect', { x: -26, y: -16, width: 52, height: 32, rx: 7 }), svgEl('rect', { x: -62, y: -10, width: 30, height: 20 }), svgEl('rect', { x: 32, y: -10, width: 30, height: 20 }));
    this.gravity = svgEl('line', { class: 'p3-space-vector gravity', 'marker-end': 'url(#p3-gravity-arrow)' });
    this.velocity = svgEl('line', { class: 'p3-space-vector velocity', 'marker-end': 'url(#p3-orbit-velocity)' });
    if (!params.showGravityVector) this.gravity.classList.add('is-hidden'); if (!params.showVelocityVector) this.velocity.classList.add('is-hidden');
    append(this.diagram, this.orbit, this.body, this.gravity, this.velocity, this.satellite, pointLabel(710, 650, `orbit radius ${params.orbitRadius}`, 'p3-motion-stat'));
    this.card.appendChild(this.diagram); this.root.appendChild(this.card); this.update(-.5);
  }
  update(angle) {
    const x = this.cx + Math.cos(angle) * this.rx, y = this.cy + Math.sin(angle) * this.ry;
    this.satellite.setAttribute('transform', `translate(${x} ${y}) rotate(${angle * 180 / Math.PI + 90})`);
    this.gravity.setAttribute('x1', x); this.gravity.setAttribute('y1', y); this.gravity.setAttribute('x2', x + (this.cx - x) * .38); this.gravity.setAttribute('y2', y + (this.cy - y) * .38);
    const tx = -Math.sin(angle) * 115, ty = Math.cos(angle) * this.ry / this.rx * 115;
    this.velocity.setAttribute('x1', x); this.velocity.setAttribute('y1', y); this.velocity.setAttribute('x2', x + tx); this.velocity.setAttribute('y2', y + ty);
  }
  buildTimeline(params) {
    const state = { angle: -.5 }, tl = phase3Timeline(this.root), length = this.orbit.getTotalLength();
    gsap.set(this.orbit, { strokeDasharray: length, strokeDashoffset: length });
    tl.fromTo(this.card, { scale: .96, autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: .55 }, .3)
      .to(this.orbit, { strokeDashoffset: 0, duration: 1.0 }, .55)
      .fromTo([this.body, this.satellite], { scale: .5, autoAlpha: 0, transformOrigin: 'center' }, { scale: 1, autoAlpha: 1, duration: .48, stagger: .15 }, .85)
      .to(state, { angle: state.angle + Math.PI * 2.3, duration: 4.3, ease: 'none', onUpdate: () => this.update(state.angle) }, 1.2);
    return finishPhase3(tl, this.root, params, 6.5);
  }
  teardown() { this.root?.remove(); }
  static getParamSchema() { return { type: 'object', required: ['centralBody','orbitingBody'], additionalProperties: false, properties: { centralBody: schemas.shortText('Earth', 24), orbitingBody: schemas.shortText('Satellite', 24), orbitRadius: schemas.positive(300, 500), showGravityVector: schemas.toggle(true), showVelocityVector: schemas.toggle(true), isElliptical: schemas.toggle(false) } }; }
}
