import { append, cueTimes, el, finishPhase3, phase3Root, phase3Timeline, schemas } from './_shared.js';

export class Scene_MultipleMeasurementAverage {
  setup(container, params) {
    const frame = phase3Root(container, 'Scene_MultipleMeasurementAverage', 'Repeat • compare • average', params.quantity, 'Repeated readings expose scatter; the mean provides one representative result.', 'scene-measurement-average');
    this.root = frame.root;
    this.panel = el('section', 'p3-average-panel');
    this.readings = params.readings.map((value, index) => {
      const node = el('article', 'p3-reading-chip');
      append(node, el('small', '', { text: `reading ${index + 1}` }), el('strong', '', { text: `${value} ${params.unit}` }));
      return node;
    });
    const total = params.readings.reduce((sum, value) => sum + Number(value), 0);
    const average = total / params.readings.length;
    this.calculation = el('div', 'p3-average-calculation');
    append(this.calculation,
      el('span', '', { text: params.readings.join(' + ') }),
      el('i', '', { text: `÷ ${params.readings.length}` }),
      el('strong', '', { text: `${Number.isFinite(average) ? average.toFixed(params.decimalPlaces) : '?'} ${params.unit}` })
    );
    this.meanLine = el('div', 'p3-mean-line');
    append(this.panel, el('div', 'p3-reading-row'), this.meanLine, this.calculation);
    this.panel.querySelector('.p3-reading-row').append(...this.readings);
    this.root.appendChild(this.panel);
  }

  buildTimeline(params) {
    const cues = cueTimes(params, this.readings.length + 3);
    const tl = phase3Timeline(this.root);
    tl.fromTo(this.panel, { y: 24, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55, ease: 'power3.out' }, cues[0]);
    this.readings.forEach((reading, index) => {
      tl.fromTo(reading, { y: -24, scale: .8, autoAlpha: 0 }, { y: 0, scale: 1, autoAlpha: 1, duration: .42, ease: 'back.out(1.5)' }, cues[index + 1]);
    });
    tl.fromTo(this.meanLine, { scaleX: 0 }, { scaleX: 1, duration: .65, ease: 'power2.inOut' }, cues[this.readings.length + 1])
      .fromTo(this.calculation, { y: 25, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55, ease: 'power3.out' }, cues[this.readings.length + 2])
      .fromTo(this.calculation.querySelector('strong'), { scale: .7 }, { scale: 1, duration: .45, ease: 'back.out(1.8)' }, cues[this.readings.length + 2] + .3);
    return finishPhase3(tl, this.root, params, 10);
  }

  teardown() { this.root?.remove(); }
  static getParamSchema() {
    return { type: 'object', required: ['quantity', 'readings', 'unit'], additionalProperties: false, properties: {
      quantity: schemas.shortText('Repeated length measurements', 70),
      readings: { type: 'array', minItems: 2, maxItems: 6, default: [12.3, 12.4, 12.5], items: { type: 'number', minimum: -100000, maximum: 100000 } },
      unit: schemas.shortText('cm', 12), decimalPlaces: { type: 'integer', minimum: 0, maximum: 3, default: 1 }
    } };
  }
}
