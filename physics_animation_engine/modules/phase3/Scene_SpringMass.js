import { addArrowMarker, append, clamp, finishPhase3, phase3Root, phase3Timeline, pointLabel, schemas, svg, svgEl } from './_shared.js';

function springPath(endX) {
  const startX = 160, y = 310, turns = 12, usable = Math.max(180, endX - startX - 35);
  let d = `M ${startX} ${y} L ${startX + 25} ${y}`;
  for (let index = 0; index <= turns; index++) d += ` L ${startX + 25 + usable * index / turns} ${y + (index % 2 ? 38 : -38)}`;
  return `${d} L ${endX} ${y}`;
}

export class Scene_SpringMass {
  setup(container, params) {
    const frame = phase3Root(container, 'Scene_SpringMass', 'Hooke’s law', 'Spring–mass oscillator', `k = ${params.springConstant} N/m · mass = ${params.mass} kg · amplitude = ${params.displacement}`, 'scene-spring-mass');
    this.root = frame.root;
    this.card = document.createElement('section'); this.card.className = 'p3-spring-card';
    this.diagram = svg('p3-spring-svg', '0 0 1420 700');
    addArrowMarker(this.diagram, 'p3-spring-arrow', '#ff5a36');
    this.equilibriumX = 830; this.amplitude = clamp(params.displacement * 2.2, 70, 260);
    this.spring = svgEl('path', { d: springPath(this.equilibriumX), class: 'p3-spring-line' });
    this.mass = svgEl('g', { class: 'p3-spring-block' });
    append(this.mass, svgEl('rect', { x: -75, y: -70, width: 150, height: 140, rx: 18 }), pointLabel(0, 8, `${params.mass} kg`, 'p3-block-label'));
    this.force = svgEl('line', { class: 'p3-spring-force', 'marker-end': 'url(#p3-spring-arrow)' });
    if (!params.showForceArrow) this.force.classList.add('is-hidden');
    this.graph = svgEl('g', { class: 'p3-spring-graph' });
    append(this.graph,
      svgEl('rect', { x: 1040, y: 85, width: 300, height: 270, rx: 16 }),
      svgEl('line', { x1: 1075, y1: 220, x2: 1310, y2: 220, class: 'axis' }),
      svgEl('line', { x1: 1192, y1: 115, x2: 1192, y2: 325, class: 'axis' })
    );
    this.graphLine = svgEl('path', { class: 'p3-spring-graph-line' }); this.graph.appendChild(this.graphLine);
    if (!params.showGraph) this.graph.classList.add('is-hidden');
    append(this.diagram,
      svgEl('rect', { x: 85, y: 165, width: 75, height: 290, class: 'p3-spring-wall' }),
      svgEl('line', { x1: 160, y1: 310, x2: 980, y2: 310, class: 'p3-equilibrium-line' }),
      this.spring, this.force, this.mass, this.graph,
      pointLabel(650, 590, 'F = −kx', 'p3-motion-stat')
    );
    this.card.appendChild(this.diagram); this.root.appendChild(this.card);
  }
  update(progress, params) {
    const displacement = Math.cos(progress * Math.PI * 4) * this.amplitude;
    const x = this.equilibriumX + displacement;
    this.spring.setAttribute('d', springPath(x - 75)); this.mass.setAttribute('transform', `translate(${x} 310)`);
    const direction = displacement > 0 ? -1 : 1, forceLength = 65 + Math.abs(displacement) * .36;
    this.force.setAttribute('x1', x); this.force.setAttribute('y1', 220); this.force.setAttribute('x2', x + direction * forceLength); this.force.setAttribute('y2', 220);
    const graphX = 1192 + displacement / this.amplitude * 100, graphY = 220 + displacement / this.amplitude * 90;
    this.graphLine.setAttribute('d', `M1192 220 L${graphX} ${graphY}`);
  }
  buildTimeline(params) {
    const state = { progress: 0 }; this.update(0, params);
    const tl = phase3Timeline(this.root);
    const length = this.spring.getTotalLength(); gsap.set(this.spring, { strokeDasharray: length, strokeDashoffset: length });
    tl.fromTo(this.card, { y: 25, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .3)
      .to(this.spring, { strokeDashoffset: 0, duration: .9 }, .65)
      .fromTo(this.mass, { scale: .65, autoAlpha: 0, transformOrigin: 'center' }, { scale: 1, autoAlpha: 1, duration: .45 }, .95);
    const visibleExtras = [this.force, this.graph].filter(node => !node.classList.contains('is-hidden'));
    if (visibleExtras.length) tl.fromTo(visibleExtras, { autoAlpha: 0 }, { autoAlpha: 1, duration: .4, stagger: .12 }, 1.2);
    tl.to(state, { progress: 1, duration: 4.2, ease: 'none', onUpdate: () => this.update(state.progress, params) }, 1.35);
    return finishPhase3(tl, this.root, params, 6.5);
  }
  teardown() { this.root?.remove(); }
  static getParamSchema() { return { type: 'object', additionalProperties: false, properties: { springConstant: schemas.positive(15, 500), mass: schemas.positive(2, 100), displacement: schemas.positive(80, 200), showForceArrow: schemas.toggle(true), showGraph: schemas.toggle(true) } }; }
}
