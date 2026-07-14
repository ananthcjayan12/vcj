import { append, el, finishPhase3, phase3Root, phase3Timeline, schemas } from './_shared.js';

export class Scene_ComparisonTable {
  setup(container, params) {
    const frame = phase3Root(container, 'Scene_ComparisonTable', 'Side-by-side reasoning', `${params.heading1} vs ${params.heading2}`, 'Compare scientific ideas with aligned, reusable evidence rows.', 'scene-comparison-table');
    this.root = frame.root;
    this.table = el('section', 'p3-comparison');
    const header = el('div', 'p3-comparison-row is-header');
    append(header, el('strong', '', { text: params.heading1 }), el('strong', '', { text: params.heading2 }));
    this.rows = params.rows.map((row, index) => {
      const node = el('div', 'p3-comparison-row');
      append(node, el('span', '', { html: `<b>${String(index + 1).padStart(2, '0')}</b>` }), el('p', '', { text: row.col1 }), el('p', '', { text: row.col2 }));
      return node;
    });
    this.gridLines = [el('i', 'p3-table-line vertical'), el('i', 'p3-table-line horizontal')];
    append(this.table, header, ...this.rows, ...this.gridLines);
    this.root.appendChild(this.table);
  }
  buildTimeline(params) {
    const tl = phase3Timeline(this.root);
    tl.fromTo(this.table, { y: 28, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .35)
      .fromTo(this.gridLines, { scale: 0 }, { scale: 1, duration: .7, stagger: .08 }, .55)
      .fromTo(this.table.querySelectorAll('.is-header strong'), { y: -22, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .45, stagger: .12 }, .85)
      .fromTo(this.rows, { x: 45, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: .48, stagger: .18, ease: 'power3.out' }, 1.15);
    return finishPhase3(tl, this.root, params, 6);
  }
  teardown() { this.root?.remove(); }
  static getParamSchema() {
    return { type: 'object', required: ['heading1', 'heading2', 'rows'], additionalProperties: false, properties: { heading1: schemas.shortText('Option A', 40), heading2: schemas.shortText('Option B', 40), rows: { type: 'array', minItems: 1, maxItems: 5, default: [], items: { type: 'object', required: ['col1', 'col2'], additionalProperties: false, properties: { col1: schemas.shortText('', 120), col2: schemas.shortText('', 120) } } } } };
  }
}
