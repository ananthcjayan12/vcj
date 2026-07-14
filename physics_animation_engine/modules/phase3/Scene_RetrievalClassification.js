import { append, cueTimes, el, finishPhase3, phase3Root, phase3Timeline, schemas } from './_shared.js';

export class Scene_RetrievalClassification {
  setup(container, params) {
    const frame = phase3Root(container, 'Scene_RetrievalClassification', 'Pause and classify', params.prompt, 'Make the decision first, then reveal whether each quantity needs direction.', 'scene-retrieval-classification');
    this.root = frame.root;
    this.panel = el('section', 'p3-retrieval-panel');
    this.bank = el('div', 'p3-retrieval-bank');
    this.scalar = el('div', 'p3-sort-zone is-scalar');
    this.vector = el('div', 'p3-sort-zone is-vector');
    append(this.scalar, el('strong', '', { text: 'Scalar' }), el('small', '', { text: 'magnitude only' }));
    append(this.vector, el('strong', '', { text: 'Vector' }), el('small', '', { text: 'magnitude + direction' }));
    this.items = params.items.map((item, index) => {
      const chip = el('span', `p3-sort-chip is-${item.type}`, { text: item.label });
      chip.style.setProperty('--sort-index', index);
      this.bank.appendChild(chip);
      return { chip, type: item.type };
    });
    this.cover = el('div', 'p3-answer-cover', { text: 'Pause • decide • then reveal' });
    append(this.panel, this.bank, this.scalar, this.vector, this.cover);
    this.root.appendChild(this.panel);
  }

  buildTimeline(params) {
    const cues = cueTimes(params, 5);
    const tl = phase3Timeline(this.root);
    tl.fromTo(this.panel, { y: 24, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55, ease: 'power3.out' }, cues[0])
      .fromTo(this.items.map(item => item.chip), { y: -30, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .4, stagger: .12, ease: 'back.out(1.5)' }, cues[1])
      .fromTo([this.scalar, this.vector], { y: 30, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .45, stagger: .15, ease: 'power2.out' }, cues[2])
      .to(this.cover, { y: 45, autoAlpha: 0, duration: .45, ease: 'power2.in' }, cues[3]);
    this.items.forEach((item, index) => {
      const destination = item.type === 'scalar' ? this.scalar : this.vector;
      const sourceBox = item.chip.getBoundingClientRect();
      const targetBox = destination.getBoundingClientRect();
      const x = targetBox.left + targetBox.width / 2 - (sourceBox.left + sourceBox.width / 2);
      const y = targetBox.top + 160 + (index % 3) * 70 - (sourceBox.top + sourceBox.height / 2);
      tl.to(item.chip, { x, y, duration: .7, ease: 'power3.inOut' }, cues[4] + index * .12);
    });
    return finishPhase3(tl, this.root, params, 10);
  }

  teardown() { this.root?.remove(); }
  static getParamSchema() {
    return { type: 'object', required: ['prompt', 'items'], additionalProperties: false, properties: {
      prompt: schemas.shortText('Scalar or vector?', 70),
      items: { type: 'array', minItems: 2, maxItems: 6, default: [], items: { type: 'object', required: ['label', 'type'], additionalProperties: false, properties: {
        label: schemas.shortText('speed', 30), type: { type: 'string', enum: ['scalar', 'vector'], default: 'scalar' }
      } } }
    } };
  }
}
