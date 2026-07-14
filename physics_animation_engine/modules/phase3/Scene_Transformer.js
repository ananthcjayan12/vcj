import { append, drawPaths, el, finishPhase3, formatNumber, phase3Root, phase3Timeline, pointLabel, schemas, svg, svgEl } from './_shared.js';

export class Scene_Transformer {
  setup(container, params) {
    this.outputVoltage = params.inputVoltage * params.secondaryTurns / params.primaryTurns;
    const mode = params.secondaryTurns > params.primaryTurns ? 'step-up' : params.secondaryTurns < params.primaryTurns ? 'step-down' : 'isolation';
    const frame = phase3Root(container, 'Scene_Transformer', 'Turns ratio', `${mode} transformer`, `Voltage is calculated automatically from Vₛ / Vₚ = Nₛ / Nₚ.`, 'scene-transformer');
    this.root = frame.root;
    this.card = el('section', 'p3-transformer-card');
    this.diagram = svg('p3-transformer-svg', '0 0 1420 700');
    this.core = svgEl('path', { d: 'M360 120 H1060 V570 H360 Z M500 235 V455 H920 V235 Z', class: 'p3-transformer-core', 'fill-rule': 'evenodd' });
    this.primary = svgEl('g', { class: 'p3-transformer-coil primary' });
    this.secondary = svgEl('g', { class: 'p3-transformer-coil secondary' });
    const pCount = Math.min(12, Math.max(4, Math.round(params.primaryTurns / 20))), sCount = Math.min(12, Math.max(4, Math.round(params.secondaryTurns / 20)));
    for (let index = 0; index < pCount; index++) this.primary.appendChild(svgEl('ellipse', { cx: 485, cy: 260 + index * 190 / Math.max(1, pCount - 1), rx: 55, ry: 25 }));
    for (let index = 0; index < sCount; index++) this.secondary.appendChild(svgEl('ellipse', { cx: 935, cy: 260 + index * 190 / Math.max(1, sCount - 1), rx: 55, ry: 25 }));
    this.fields = [0,1,2].map(index => svgEl('path', { d: `M515 ${280 + index * 55} C650 ${190 + index * 45}, 785 ${190 + index * 45}, 905 ${280 + index * 55}`, class: 'p3-transformer-field' }));
    if (!params.showFieldLines) this.fields.forEach(path => path.classList.add('is-hidden'));
    append(this.diagram, this.core, ...this.fields, this.primary, this.secondary,
      pointLabel(485, 625, `Primary · ${params.primaryTurns} turns`, 'p3-transformer-label'),
      pointLabel(935, 625, `Secondary · ${params.secondaryTurns} turns`, 'p3-transformer-label')
    );
    this.result = el('aside', 'p3-transformer-result');
    append(this.result,
      el('small', '', { text: 'Calculated output' }),
      el('strong', '', { text: `${formatNumber(this.outputVoltage)} V` }),
      el('span', '', { text: `${params.inputVoltage} V × ${params.secondaryTurns}/${params.primaryTurns}` }),
      el('b', '', { text: mode })
    );
    this.card.append(this.diagram, this.result); this.root.appendChild(this.card);
  }
  buildTimeline(params) {
    const tl = phase3Timeline(this.root);
    tl.fromTo(this.card, { y: 26, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .3)
      .fromTo(this.core, { scale: .82, autoAlpha: 0, transformOrigin: 'center' }, { scale: 1, autoAlpha: 1, duration: .65 }, .55)
      .fromTo([...this.primary.children, ...this.secondary.children], { scaleX: 0, autoAlpha: 0, transformOrigin: 'center' }, { scaleX: 1, autoAlpha: 1, duration: .28, stagger: .035 }, 1.05)
      .fromTo(this.result, { x: 30, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: .5, ease: 'back.out(1.5)' }, 2.15);
    if (params.showFieldLines) drawPaths(tl, this.fields, 1.55, .8, .1);
    return finishPhase3(tl, this.root, params, 6);
  }
  teardown() { this.root?.remove(); }
  static getParamSchema() { return { type: 'object', required: ['primaryTurns', 'secondaryTurns', 'inputVoltage'], additionalProperties: false, properties: { primaryTurns: { type: 'integer', minimum: 1, maximum: 2000, default: 100 }, secondaryTurns: { type: 'integer', minimum: 1, maximum: 2000, default: 50 }, inputVoltage: schemas.positive(240, 10000), showFieldLines: schemas.toggle(true) } }; }
}
