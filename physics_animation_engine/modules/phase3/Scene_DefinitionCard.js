import { append, cueTimes, el, finishPhase3, phase3Root, phase3Timeline, schemas } from './_shared.js';

export class Scene_DefinitionCard {
  setup(container, params) {
    const frame = phase3Root(container, 'Scene_DefinitionCard', 'Core vocabulary', params.term, 'A focused concept card for introducing precise scientific language.', 'scene-definition-card');
    this.root = frame.root;
    this.card = el('section', 'p3-definition-panel');
    this.term = el('strong', 'p3-definition-term', { text: params.term });
    this.rule = el('i', 'p3-definition-rule');
    this.definition = el('p', 'p3-definition-copy');
    this.words = params.definition.split(/\s+/).filter(Boolean).map(word => el('span', '', { text: `${word} ` }));
    append(this.definition, ...this.words);
    append(this.card, el('small', '', { text: 'Definition' }), this.term, this.rule, this.definition);
    this.example = null;
    if (params.example) {
      this.example = el('aside', 'p3-definition-example');
      append(this.example, el('b', '', { text: '↳' }), el('span', '', { html: '<small>Example</small>' }), el('p', '', { text: params.example }));
      this.card.appendChild(this.example);
    }
    this.root.appendChild(this.card);
  }

  buildTimeline(params) {
    const tl = phase3Timeline(this.root);
    const cues = cueTimes(params, this.example ? 5 : 4);
    tl.fromTo(this.card, { scale: .94, y: 28, autoAlpha: 0 }, { scale: 1, y: 0, autoAlpha: 1, duration: .65, ease: 'power3.out' }, cues[0])
      .fromTo(this.term, { x: -80, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: .65, ease: 'power3.out' }, cues[1])
      .fromTo(this.rule, { scaleX: 0 }, { scaleX: 1, duration: .55, ease: 'power2.inOut' }, cues[2])
      .fromTo(this.words, { y: 10, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .18, stagger: .045, ease: 'power2.out' }, cues[3]);
    if (this.example) tl.fromTo(this.example, { y: 24, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .5, ease: 'back.out(1.4)' }, cues[4]);
    return finishPhase3(tl, this.root, params, 5.5);
  }

  teardown() { this.root?.remove(); }
  static getParamSchema() {
    return { type: 'object', required: ['term', 'definition'], additionalProperties: false, properties: { term: schemas.shortText('Physics term', 48), definition: schemas.shortText('A clear scientific definition.', 260), example: schemas.shortText('', 180) } };
  }
}
