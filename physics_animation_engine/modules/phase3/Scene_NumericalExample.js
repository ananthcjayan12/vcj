import { append, cueTimes, el, finishPhase3, phase3Root, phase3Timeline, schemas } from './_shared.js';

export class Scene_NumericalExample {
  setup(container, params) {
    const frame = phase3Root(container, 'Scene_NumericalExample', 'Worked example', params.title, 'A stepwise calculation where the active reasoning stays visually explicit.', 'scene-numerical-example');
    this.root = frame.root;
    this.panel = el('section', 'p3-worked-panel');
    this.steps = params.steps.map((step, index) => {
      const node = el('article', 'p3-worked-step');
      append(node,
        el('span', '', { text: String(index + 1).padStart(2, '0') }),
        el('div', '', { html: `<small>${step.label}</small>` }),
        el('strong', '', { text: step.content })
      );
      return node;
    });
    append(this.panel, ...this.steps);
    this.progress = el('aside', 'p3-worked-progress');
    append(this.progress, el('small', '', { text: 'Method' }), el('strong', '', { text: `${this.steps.length} clear steps` }), el('span'));
    this.root.append(this.panel, this.progress);
  }
  buildTimeline(params) {
    const tl = phase3Timeline(this.root);
    const cues = cueTimes(params, this.steps.length + 2);
    tl.fromTo(this.panel, { y: 28, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55, ease: 'power3.out' }, cues[0])
      .fromTo(this.progress, { x: 30, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: .45, ease: 'power2.out' }, cues[1]);
    this.steps.forEach((step, index) => {
      const at = cues[index + 2];
      tl.fromTo(step, { x: -40, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: .45, ease: 'power3.out' }, at)
        .to(step, { borderColor: 'rgba(255,210,63,.52)', backgroundColor: 'rgba(255,210,63,.065)', duration: .28 }, at + .18);
      if (index) tl.to(this.steps[index - 1], { opacity: .48, borderColor: 'rgba(255,255,255,.07)', duration: .28 }, at + .18);
      tl.to(this.progress.querySelector('span'), { width: `${(index + 1) / this.steps.length * 100}%`, duration: .45 }, at + .15);
    });
    return finishPhase3(tl, this.root, params, Math.max(6, 2.2 + this.steps.length * .8));
  }
  teardown() { this.root?.remove(); }
  static getParamSchema() {
    return { type: 'object', required: ['title', 'steps'], additionalProperties: false, properties: { title: schemas.shortText('Worked example', 70), steps: { type: 'array', minItems: 2, maxItems: 6, default: [], items: { type: 'object', required: ['label', 'content'], additionalProperties: false, properties: { label: schemas.shortText('', 55), content: schemas.shortText('', 100) } } } } };
  }
}
