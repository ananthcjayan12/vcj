import { append, duration, el, finishTimeline, root } from '../engine/renderer.js';

export class Scene_SummaryCard {
  setup(container, params) {
    this.root = root(container, 'Scene_SummaryCard', 'scene-summarycard');
    this.glow = el('div', 'sc-glow');
    this.card = el('div', 'sc-card');
    const kicker = el('span', 'sc-kicker', { text: 'Lesson complete' });
    this.heading = el('h2', 'sc-heading', { text: params.heading || 'Key Takeaways' });
    this.list = el('div', 'sc-list');
    params.points.forEach((point, index) => {
      const item = el('div', 'sc-point');
      append(item, el('span', 'sc-number', { text: String(index + 1).padStart(2, '0') }), el('p', '', { text: point }), el('span', 'sc-check', { text: '✓' }));
      this.list.appendChild(item);
    });
    append(this.card, kicker, this.heading, this.list);
    append(this.root, this.glow, this.card);
  }

  buildTimeline(params) {
    const seconds = duration(params, 7);
    const tl = gsap.timeline({ paused: true });
    const points = this.list.querySelectorAll('.sc-point');
    tl.set(this.root, { autoAlpha: 1 }, 0)
      .fromTo(this.glow, { opacity: 0, scale: .5 }, { opacity: 1, scale: 1, duration: 1.4, ease: 'power2.out' }, 0)
      .fromTo(this.card, { scale: .9, autoAlpha: 0, filter: 'blur(18px)' }, { scale: 1, autoAlpha: 1, filter: 'blur(0px)', duration: .75, ease: 'power3.out' }, .08)
      .fromTo(this.heading, { y: 18, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .5 }, .42)
      .fromTo(points, { x: -45, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: .65, stagger: .72, ease: 'power3.out' }, .85)
      .fromTo(this.list.querySelectorAll('.sc-check'), { scale: 0, rotation: -30 }, { scale: 1, rotation: 0, duration: .35, stagger: .72, ease: 'back.out(2)' }, 1.18);
    return finishTimeline(tl, this.root, seconds);
  }

  teardown() { this.root?.remove(); }

  static getParamSchema() {
    return {
      type: 'object', required: ['points'], additionalProperties: false,
      properties: {
        heading: { type: 'string', maxLength: 60, default: 'Key Takeaways' },
        points: { type: 'array', minItems: 2, maxItems: 5, default: ['Review the core idea', 'Apply it to a new example'], items: { type: 'string', maxLength: 80 } }
      }
    };
  }
}
