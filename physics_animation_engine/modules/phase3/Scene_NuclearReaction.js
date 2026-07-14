import { append, el, finishPhase3, phase3Root, phase3Timeline, pointLabel, schemas, svg, svgEl } from './_shared.js';

function nucleus(x, y, radius, labelText, className) {
  const group = svgEl('g', { class: `p3-reaction-nucleus ${className}` });
  append(group, svgEl('circle', { cx: x, cy: y, r: radius }), pointLabel(x, y + 7, labelText, 'p3-nucleus-label'));
  return group;
}

export class Scene_NuclearReaction {
  setup(container, params) {
    const frame = phase3Root(container, 'Scene_NuclearReaction', 'Nuclear energy', params.type === 'fission' ? 'Nuclear fission' : 'Nuclear fusion', params.type === 'fission' ? 'A heavy nucleus splits after absorbing a neutron.' : 'Light nuclei combine to form a heavier, more stable nucleus.', 'scene-nuclear-reaction');
    this.root = frame.root;
    this.card = el('section', 'p3-reaction-card');
    this.diagram = svg('p3-reaction-svg', '0 0 1420 700');
    const first = params.reactants[0] || 'Reactant', second = params.reactants[1] || '';
    this.reactantA = nucleus(params.type === 'fission' ? 470 : 390, 345, params.type === 'fission' ? 105 : 70, first, 'reactant-a');
    this.reactantB = nucleus(params.type === 'fission' ? 170 : 640, 345, params.type === 'fission' ? 25 : 70, second, 'reactant-b');
    const productLabels = params.products.slice(0, 3);
    this.products = productLabels.map((product, index) => nucleus(1020 + (index === 1 ? 130 : 0), 260 + index * 105, index === 2 ? 32 : 74, product, `product-${index}`));
    this.burst = svgEl('path', { d: 'M760 210 L790 300 L885 270 L820 350 L900 420 L790 395 L760 490 L730 395 L620 420 L700 350 L635 270 L730 300 Z', class: 'p3-energy-burst' });
    this.energyLabel = pointLabel(760, 365, 'ENERGY', 'p3-energy-label');
    append(this.diagram, this.reactantA, this.reactantB, this.burst, this.energyLabel, ...this.products);
    this.equation = el('aside', 'p3-reaction-equation');
    append(this.equation, el('span', '', { text: params.reactants.join(' + ') }), el('i', '', { text: '→' }), el('strong', '', { text: params.products.join(' + ') }));
    this.card.append(this.diagram, this.equation); this.root.appendChild(this.card);
  }
  buildTimeline(params) {
    const tl = phase3Timeline(this.root);
    tl.fromTo(this.card, { y: 25, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .3)
      .fromTo([this.reactantA, this.reactantB], { scale: .55, autoAlpha: 0, transformOrigin: 'center' }, { scale: 1, autoAlpha: 1, duration: .52, stagger: .12, ease: 'back.out(1.7)' }, .62)
      .to(this.reactantB, { x: params.type === 'fission' ? 275 : -135, duration: .72, ease: 'power2.in' }, 1.15)
      .to([this.reactantA, this.reactantB], { x: '+=8', duration: .06, repeat: 8, yoyo: true }, 1.75)
      .fromTo(this.burst, { scale: .2, autoAlpha: 0, transformOrigin: 'center' }, { scale: 1.35, autoAlpha: 1, duration: .22, repeat: 1, yoyo: true }, 2.2)
      .to([this.reactantA, this.reactantB], { scale: .4, autoAlpha: 0, duration: .22 }, 2.25)
      .fromTo(this.products, { scale: .35, autoAlpha: 0, transformOrigin: 'center' }, { scale: 1, autoAlpha: 1, duration: .48, stagger: .1, ease: 'back.out(1.8)' }, 2.42)
      .fromTo(this.equation, { y: 20, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .45 }, 3.05);
    if (!params.showEnergyRelease) gsap.set([this.burst, this.energyLabel], { display: 'none' });
    return finishPhase3(tl, this.root, params, 6.3);
  }
  teardown() { this.root?.remove(); }
  static getParamSchema() { return { type: 'object', required: ['type', 'reactants', 'products'], additionalProperties: false, properties: { type: { type: 'string', enum: ['fission', 'fusion'], default: 'fission' }, reactants: { type: 'array', minItems: 1, maxItems: 3, default: ['U-235', 'neutron'], items: schemas.shortText('', 24) }, products: { type: 'array', minItems: 1, maxItems: 4, default: ['Ba-141', 'Kr-92'], items: schemas.shortText('', 28) }, showEnergyRelease: schemas.toggle(true) } }; }
}
