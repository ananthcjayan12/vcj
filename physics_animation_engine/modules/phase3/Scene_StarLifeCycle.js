import { append, el, finishPhase3, phase3Root, phase3Timeline, schemas } from './_shared.js';

const STAGE_LABELS = { nebula: 'Nebula', protostar: 'Protostar', main_sequence: 'Main sequence', red_giant: 'Red giant', red_supergiant: 'Red supergiant', planetary_nebula: 'Planetary nebula', white_dwarf: 'White dwarf', supernova: 'Supernova', neutron_star: 'Neutron star', black_hole: 'Black hole' };

export class Scene_StarLifeCycle {
  setup(container, params) {
    const frame = phase3Root(container, 'Scene_StarLifeCycle', 'Stellar evolution', `${params.starType} star life cycle`, 'Stage order, labels, and visual character come directly from the supplied sequence.', 'scene-star-life-cycle');
    this.root = frame.root;
    this.panel = el('section', 'p3-star-panel');
    this.flow = el('div', 'p3-star-flow');
    this.stages = params.stages.map((stage, index) => {
      const wrapper = el('article', 'p3-star-stage');
      const star = el('span', `p3-star is-${stage}`); star.textContent = stage === 'black_hole' ? '●' : '✦';
      append(wrapper, star, el('strong', '', { text: STAGE_LABELS[stage] || stage.replaceAll('_', ' ') }), el('small', '', { text: String(index + 1).padStart(2, '0') }));
      if (index < params.stages.length - 1) wrapper.appendChild(el('i', 'p3-star-arrow', { text: '→' }));
      return wrapper;
    });
    append(this.flow, ...this.stages); this.panel.appendChild(this.flow);
    this.summary = el('aside', 'p3-star-summary');
    append(this.summary, el('span', '', { text: params.starType }), el('strong', '', { text: `${params.stages.length} evolutionary stages` }), el('p', '', { text: 'Mass determines the final path.' }));
    this.panel.appendChild(this.summary); this.root.appendChild(this.panel);
  }
  buildTimeline(params) {
    const tl = phase3Timeline(this.root);
    tl.fromTo(this.panel, { y: 26, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .3);
    this.stages.forEach((stage, index) => {
      const at = .65 + index * .42;
      tl.fromTo(stage.querySelector('.p3-star'), { scale: .15, autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: .48, ease: 'back.out(1.8)' }, at)
        .fromTo(stage.querySelectorAll('strong,small'), { y: 12, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .3, stagger: .06 }, at + .18);
      const arrow = stage.querySelector('.p3-star-arrow'); if (arrow) tl.fromTo(arrow, { scaleX: 0, autoAlpha: 0 }, { scaleX: 1, autoAlpha: 1, duration: .3 }, at + .28);
    });
    tl.fromTo(this.summary, { x: 28, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: .45 }, 1.0 + this.stages.length * .42);
    return finishPhase3(tl, this.root, params, Math.max(6, 2.3 + this.stages.length * .45));
  }
  teardown() { this.root?.remove(); }
  static getParamSchema() { return { type: 'object', required: ['starType','stages'], additionalProperties: false, properties: { starType: { type: 'string', enum: ['average','massive'], default: 'average' }, stages: { type: 'array', minItems: 3, maxItems: 7, default: ['nebula','protostar','main_sequence','red_giant','white_dwarf'], items: { type: 'string', enum: Object.keys(STAGE_LABELS), default: 'main_sequence' } } } }; }
}
