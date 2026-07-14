import { addArrowMarker, append, cueTimes, finishPhase3, phase3Root, phase3Timeline, pointLabel, schemas, svg, svgEl } from './_shared.js';

export class Scene_PendulumTiming {
  setup(container, params) {
    const frame = phase3Root(container, 'Scene_PendulumTiming', 'Practical timing', 'Time several oscillations', 'Counting repeated swings reduces the percentage uncertainty in one period.', 'scene-pendulum-timing');
    this.root = frame.root;
    this.card = document.createElement('section'); this.card.className = 'p3-practical-card';
    this.diagram = svg('p3-pendulum-svg', '0 0 1500 680');
    addArrowMarker(this.diagram, 'pendulum-direction', '#00f5ff');
    this.support = svgEl('path', { d: 'M420 90 H1080 M750 90 V120', class: 'p3-pendulum-support' });
    this.string = svgEl('line', { x1: 750, y1: 120, x2: 750, y2: 500, class: 'p3-pendulum-string' });
    this.bob = svgEl('circle', { cx: 750, cy: 520, r: 52, class: 'p3-pendulum-bob' });
    this.arc = svgEl('path', { d: 'M490 500 Q750 660 1010 500', class: 'p3-pendulum-arc', 'marker-end': 'url(#pendulum-direction)' });
    this.counter = svgEl('g', { class: 'p3-pendulum-counter' });
    append(this.counter, svgEl('rect', { x: 1090, y: 205, width: 300, height: 150, rx: 18 }), pointLabel(1240, 258, 'oscillations', 'p3-counter-label'), pointLabel(1240, 322, `${params.oscillations}`, 'p3-counter-value'));
    this.timer = svgEl('g', { class: 'p3-pendulum-timer' });
    append(this.timer, svgEl('circle', { cx: 1240, cy: 475, r: 95 }), pointLabel(1240, 468, `${params.totalTime} ${params.unit}`, 'p3-timer-value'), pointLabel(1240, 508, 'total time', 'p3-counter-label'));
    const period = Number(params.totalTime) / Number(params.oscillations);
    this.result = svgEl('g', { class: 'p3-pendulum-result' });
    append(this.result, svgEl('rect', { x: 120, y: 225, width: 350, height: 205, rx: 18 }), pointLabel(295, 280, 'one period', 'p3-counter-label'), pointLabel(295, 350, `T = ${Number.isFinite(period) ? period.toFixed(2) : '?'} ${params.unit}`, 'p3-result-value'), pointLabel(295, 394, 'total time ÷ oscillations', 'p3-counter-label'));
    append(this.diagram, this.support, this.arc, this.string, this.bob, this.counter, this.timer, this.result);
    this.card.appendChild(this.diagram); this.root.appendChild(this.card);
  }

  buildTimeline(params) {
    const cues = cueTimes(params, 5);
    const tl = phase3Timeline(this.root);
    tl.fromTo(this.card, { y: 25, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55, ease: 'power3.out' }, cues[0])
      .fromTo([this.string, this.bob], { scaleY: 0, transformOrigin: '750px 120px', autoAlpha: 0 }, { scaleY: 1, autoAlpha: 1, duration: .7, ease: 'power3.out' }, cues[1])
      .to([this.string, this.bob], { rotation: 24, transformOrigin: '750px 120px', duration: .7, ease: 'power2.inOut', yoyo: true, repeat: 3 }, cues[2])
      .fromTo([this.counter, this.timer], { x: 45, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: .5, stagger: .18, ease: 'power2.out' }, cues[3])
      .fromTo(this.result, { scale: .82, autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: .55, ease: 'back.out(1.5)' }, cues[4]);
    return finishPhase3(tl, this.root, params, 10);
  }

  teardown() { this.root?.remove(); }
  static getParamSchema() {
    return { type: 'object', required: ['oscillations', 'totalTime', 'unit'], additionalProperties: false, properties: {
      oscillations: { type: 'integer', minimum: 2, maximum: 50, default: 10 },
      totalTime: schemas.positive(12.4, 1000), unit: schemas.shortText('s', 8)
    } };
  }
}
