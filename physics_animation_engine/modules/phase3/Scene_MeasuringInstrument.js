import { append, cueTimes, el, finishPhase3, phase3Root, phase3Timeline, schemas } from './_shared.js';

const LABELS = {
  ruler: 'Ruler',
  vernier_calipers: 'Vernier calipers',
  micrometer: 'Micrometer',
  measuring_cylinder: 'Measuring cylinder',
  stopwatch: 'Stopwatch'
};

export class Scene_MeasuringInstrument {
  setup(container, params) {
    const name = LABELS[params.instrument] || params.instrument;
    const frame = phase3Root(container, 'Scene_MeasuringInstrument', 'Choose • align • read', name, 'The instrument, zero reference, and reading are revealed as one measurement action.', 'scene-measuring-instrument');
    this.root = frame.root;
    this.panel = el('section', 'p3-measure-panel');
    this.object = el('div', 'p3-measure-object', { text: params.objectLabel || params.quantity });
    this.instrument = el('div', `p3-instrument is-${params.instrument}`);
    this.instrumentLabel = el('strong', '', { text: name });
    this.scale = el('div', 'p3-instrument-scale');
    this.ticks = Array.from({ length: 21 }, (_, index) => el('i', index % 5 === 0 ? 'major' : ''));
    append(this.scale, ...this.ticks);
    this.zero = el('span', 'p3-zero-mark', { text: '0' });
    this.cursor = el('b', 'p3-reading-cursor');
    this.readout = el('aside', 'p3-measure-readout');
    append(this.readout, el('small', '', { text: params.quantity }), el('strong', '', { text: `${params.reading} ${params.unit}` }), el('span', '', { text: 'read at eye level' }));
    append(this.instrument, this.instrumentLabel, this.scale, this.zero, this.cursor);
    append(this.panel, this.object, this.instrument, this.readout);
    this.root.appendChild(this.panel);
  }

  buildTimeline(params) {
    const cues = cueTimes(params, 5);
    const tl = phase3Timeline(this.root);
    tl.fromTo(this.panel, { y: 24, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55, ease: 'power3.out' }, cues[0])
      .fromTo(this.instrument, { x: -90, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: .7, ease: 'power3.out' }, cues[1])
      .fromTo(this.object, { x: 70, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: .55, ease: 'power2.out' }, cues[2])
      .fromTo(this.ticks, { scaleY: 0, transformOrigin: 'bottom' }, { scaleY: 1, duration: .22, stagger: .025, ease: 'power2.out' }, cues[3])
      .fromTo(this.cursor, { left: '7%', autoAlpha: 0 }, { left: '72%', autoAlpha: 1, duration: .9, ease: 'power2.inOut' }, cues[3])
      .fromTo(this.readout, { scale: .8, autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: .5, ease: 'back.out(1.5)' }, cues[4]);
    return finishPhase3(tl, this.root, params, 8);
  }

  teardown() { this.root?.remove(); }
  static getParamSchema() {
    return {
      type: 'object', required: ['instrument', 'quantity', 'reading', 'unit'], additionalProperties: false,
      properties: {
        instrument: { type: 'string', enum: ['ruler', 'vernier_calipers', 'micrometer', 'measuring_cylinder', 'stopwatch'], default: 'ruler' },
        quantity: schemas.shortText('length', 30), objectLabel: schemas.shortText('object', 36),
        reading: schemas.shortText('12.4', 18), unit: schemas.shortText('cm', 12)
      }
    };
  }
}
