import { append, color, el, finishPhase3, phase3Root, phase3Timeline, schemas } from './_shared.js';

const REGIONS = [
  { key: 'radio', label: 'Radio', wavelength: '> 1 m', use: 'broadcasting' },
  { key: 'microwave', label: 'Microwave', wavelength: '1 m – 1 mm', use: 'communications' },
  { key: 'infrared', label: 'Infrared', wavelength: '1 mm – 700 nm', use: 'thermal imaging' },
  { key: 'visible', label: 'Visible', wavelength: '700 – 400 nm', use: 'vision' },
  { key: 'ultraviolet', label: 'Ultraviolet', wavelength: '400 – 10 nm', use: 'sterilisation' },
  { key: 'xray', label: 'X-ray', wavelength: '10 – 0.01 nm', use: 'medical imaging' },
  { key: 'gamma', label: 'Gamma', wavelength: '< 0.01 nm', use: 'radiotherapy' }
];

export class Scene_EMSpectrum {
  setup(container, params) {
    const active = REGIONS.find(region => region.key === params.highlightRegion);
    const frame = phase3Root(container, 'Scene_EMSpectrum', 'Electromagnetic waves', 'The electromagnetic spectrum', `Frequency increases as wavelength decreases. Highlighted region: ${active.label}.`, 'scene-em-spectrum');
    this.root = frame.root;
    this.panel = el('section', 'p3-spectrum-panel');
    const direction = el('div', 'p3-spectrum-direction');
    append(direction, el('span', '', { text: 'long wavelength · low frequency' }), el('i'), el('span', '', { text: 'short wavelength · high frequency' }));
    this.regions = REGIONS.map(region => {
      const node = el('article', `p3-spectrum-region is-${region.key} ${region.key === active.key ? 'is-active' : ''}`);
      append(node, el('strong', '', { text: region.label }), params.showWavelengths ? el('small', '', { text: region.wavelength }) : null);
      return node;
    });
    this.detail = el('aside', 'p3-spectrum-detail');
    append(this.detail,
      el('span', '', { text: active.label }),
      el('strong', '', { text: params.showWavelengths ? active.wavelength : 'Selected region' }),
      params.showUses ? el('p', '', { text: `Common use · ${active.use}` }) : null
    );
    append(this.panel, direction, el('div', 'p3-spectrum-bar'), this.detail);
    this.panel.querySelector('.p3-spectrum-bar').append(...this.regions);
    this.root.appendChild(this.panel);
  }
  buildTimeline(params) {
    const tl = phase3Timeline(this.root), active = this.panel.querySelector('.is-active');
    tl.fromTo(this.panel, { y: 28, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .3)
      .fromTo(this.regions, { scaleX: 0, transformOrigin: 'left' }, { scaleX: 1, duration: .48, stagger: .1, ease: 'power2.out' }, .65)
      .fromTo(this.regions.map(region => region.querySelectorAll('strong,small')), { y: 15, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .3, stagger: .035 }, 1.25)
      .to(active, { y: -18, scaleY: 1.14, duration: .5, ease: 'back.out(1.6)' }, 1.75)
      .fromTo(this.detail, { y: 24, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .5 }, 2.05)
      .to(active, { filter: 'brightness(1.35) drop-shadow(0 0 22px rgba(255,255,255,.28))', duration: .7, repeat: 2, yoyo: true }, 2.4);
    return finishPhase3(tl, this.root, params, 6);
  }
  teardown() { this.root?.remove(); }
  static getParamSchema() { return { type: 'object', additionalProperties: false, properties: { highlightRegion: { type: 'string', enum: REGIONS.map(region => region.key), default: 'visible' }, showWavelengths: schemas.toggle(true), showUses: schemas.toggle(true) } }; }
}
