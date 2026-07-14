import { addArrowMarker, append, clamp, finishPhase3, phase3Root, phase3Timeline, pointLabel, schemas, svg, svgEl } from './_shared.js';

function trajectory(speed, angleDegrees, gravity) {
  const angle = angleDegrees * Math.PI / 180;
  const flightTime = Math.max(.2, 2 * speed * Math.sin(angle) / gravity);
  const range = Math.max(.2, speed * Math.cos(angle) * flightTime);
  const height = Math.max(.1, speed ** 2 * Math.sin(angle) ** 2 / (2 * gravity));
  const points = [];
  for (let index = 0; index <= 60; index++) {
    const t = flightTime * index / 60;
    points.push({ t, x: speed * Math.cos(angle) * t, y: speed * Math.sin(angle) * t - .5 * gravity * t * t });
  }
  return { angle, flightTime, range, height, points };
}

export class Scene_ProjectileMotion {
  setup(container, params) {
    const motion = trajectory(params.launchSpeed, params.launchAngle, params.gravity);
    this.motion = motion;
    const frame = phase3Root(container, 'Scene_ProjectileMotion', 'Computed mechanics', 'Projectile motion', `Launch speed ${params.launchSpeed} m/s · angle ${params.launchAngle}° · gravity ${params.gravity} m/s²`, 'scene-projectile-motion');
    this.root = frame.root;
    this.card = document.createElement('section'); this.card.className = 'p3-motion-card';
    this.diagram = svg('p3-projectile-svg', '0 0 1420 700');
    addArrowMarker(this.diagram, 'p3-projectile-arrow', '#00f5ff');
    const originX = 115, groundY = 585;
    const xScale = 1180 / motion.range;
    const yScale = Math.min(360 / motion.height, xScale);
    const pathData = motion.points.map((point, index) => `${index ? 'L' : 'M'} ${originX + point.x * xScale} ${groundY - point.y * yScale}`).join(' ');
    this.path = svgEl('path', { d: pathData, class: 'p3-projectile-path' });
    this.projectile = svgEl('circle', { cx: originX, cy: groundY, r: 16, class: 'p3-projectile-ball' });
    this.components = svgEl('g', { class: 'p3-projectile-components' });
    this.vx = svgEl('line', { class: 'p3-component vx', 'marker-end': 'url(#p3-projectile-arrow)' });
    this.vy = svgEl('line', { class: 'p3-component vy', 'marker-end': 'url(#p3-projectile-arrow)' });
    this.vxLabel = pointLabel(0, 0, '', 'p3-component-label');
    this.vyLabel = pointLabel(0, 0, '', 'p3-component-label');
    append(this.components, this.vx, this.vy, this.vxLabel, this.vyLabel);
    if (!params.showComponents) this.components.classList.add('is-hidden');
    append(this.diagram,
      svgEl('line', { x1: 65, y1: groundY, x2: 1360, y2: groundY, class: 'p3-ground-line' }),
      svgEl('path', { d: `M70 ${groundY} L140 ${groundY - 45} L155 ${groundY}`, class: 'p3-launcher' }),
      this.path, this.components, this.projectile,
      pointLabel(180, 650, `Range ${motion.range.toFixed(1)} m`, 'p3-motion-stat'),
      pointLabel(710, 650, `Peak ${motion.height.toFixed(1)} m`, 'p3-motion-stat'),
      pointLabel(1210, 650, `Flight ${motion.flightTime.toFixed(2)} s`, 'p3-motion-stat')
    );
    this.card.appendChild(this.diagram); this.root.appendChild(this.card);
  }
  update(progress, params) {
    const length = this.path.getTotalLength();
    const point = this.path.getPointAtLength(length * progress);
    const t = this.motion.flightTime * progress;
    const vx = params.launchSpeed * Math.cos(this.motion.angle);
    const vy = params.launchSpeed * Math.sin(this.motion.angle) - params.gravity * t;
    this.projectile.setAttribute('cx', point.x); this.projectile.setAttribute('cy', point.y);
    const horizontal = clamp(Math.abs(vx) * 3.2, 48, 150);
    const vertical = clamp(Math.abs(vy) * 3.2, 20, 150) * (vy >= 0 ? -1 : 1);
    for (const [line, x2, y2] of [[this.vx, point.x + horizontal, point.y], [this.vy, point.x, point.y + vertical]]) {
      line.setAttribute('x1', point.x); line.setAttribute('y1', point.y); line.setAttribute('x2', x2); line.setAttribute('y2', y2);
    }
    this.vxLabel.setAttribute('x', point.x + horizontal / 2); this.vxLabel.setAttribute('y', point.y - 15); this.vxLabel.textContent = `vₓ ${vx.toFixed(1)}`;
    this.vyLabel.setAttribute('x', point.x + 46); this.vyLabel.setAttribute('y', point.y + vertical / 2); this.vyLabel.textContent = `vᵧ ${vy.toFixed(1)}`;
  }
  buildTimeline(params) {
    const state = { progress: 0 }; this.update(0, params);
    const tl = phase3Timeline(this.root);
    const length = this.path.getTotalLength(); gsap.set(this.path, { strokeDasharray: length, strokeDashoffset: length });
    tl.fromTo(this.card, { y: 28, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .3)
      .to(this.path, { strokeDashoffset: 0, duration: 1.0, ease: 'power2.inOut' }, .7)
      .fromTo(this.projectile, { scale: 0, transformOrigin: 'center' }, { scale: 1, duration: .35, ease: 'back.out(2)' }, .8)
      .to(state, { progress: 1, duration: 3.4, ease: 'none', onUpdate: () => this.update(state.progress, params) }, 1.35);
    return finishPhase3(tl, this.root, params, 6.5);
  }
  teardown() { this.root?.remove(); }
  static getParamSchema() {
    return { type: 'object', additionalProperties: false, properties: { launchAngle: { type: 'number', minimum: 5, maximum: 85, default: 45 }, launchSpeed: schemas.positive(20, 150), gravity: schemas.positive(9.81, 30), showComponents: schemas.toggle(true) } };
  }
}
