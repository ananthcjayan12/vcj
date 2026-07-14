import { append, color, duration, el, finishTimeline, formatNumber, root } from '../engine/renderer.js';

export class Scene_EnergyBars {
  setup(container, params) {
    this.root = root(container, 'Scene_EnergyBars', 'scene-p2 scene-energy-bars');
    const header = el('header', 'p2-scene-header');
    append(header,
      el('span', 'p2-kicker', { text: 'Conservation over time' }),
      el('h2', '', { text: 'Energy changes form, not amount' }),
      el('p', '', { text: 'Each store follows reusable keyframes across the scene duration.' })
    );

    this.chart = el('section', 'p2-energy-chart');
    const scale = el('div', 'p2-energy-scale');
    [100, 75, 50, 25, 0].forEach(percent => {
      const tick = el('span', '', { text: `${formatNumber(params.totalEnergy * percent / 100)} J` });
      tick.style.bottom = `${percent}%`;
      scale.appendChild(tick);
    });

    this.plot = el('div', 'p2-energy-plot');
    this.totalLine = el('div', 'p2-total-energy-line');
    append(this.totalLine, el('span', '', { text: `Total = ${formatNumber(params.totalEnergy)} J` }));
    if (!params.showTotalLine) this.totalLine.hidden = true;

    this.bars = params.bars.map((bar, index) => {
      const column = el('article', 'p2-energy-column');
      const well = el('div', 'p2-energy-well');
      const fill = el('i');
      fill.style.setProperty('--energy-color', color(bar.color));
      const value = el('b', '', { text: `${formatNumber(bar.keyframes[0])} J` });
      append(well, fill, value);
      append(column, well, el('strong', '', { text: bar.label }), el('small', '', { text: `store ${String(index + 1).padStart(2, '0')}` }));
      this.plot.appendChild(column);
      return { column, fill, value, keyframes: bar.keyframes, state: { value: bar.keyframes[0] } };
    });
    append(this.plot, this.totalLine);
    append(this.chart, scale, this.plot);

    this.readout = el('aside', 'p2-energy-readout');
    this.sumValue = el('strong', '', { text: '0 J' });
    this.progressValue = el('b', '', { text: 't = 0%' });
    append(this.readout,
      el('span', '', { text: 'Live store total' }),
      this.sumValue,
      el('small', '', { text: 'sum of displayed stores' }),
      this.progressValue
    );
    append(this.root, header, this.chart, this.readout);
  }

  renderBars(progress, totalEnergy) {
    let sum = 0;
    this.bars.forEach(bar => {
      const segments = Math.max(1, bar.keyframes.length - 1);
      const scaled = Math.min(.999999, Math.max(0, progress)) * segments;
      const index = Math.floor(scaled);
      const local = scaled - index;
      const from = bar.keyframes[index] ?? bar.keyframes.at(-1) ?? 0;
      const to = bar.keyframes[index + 1] ?? from;
      const value = from + (to - from) * local;
      sum += value;
      bar.fill.style.height = `${Math.min(100, Math.max(0, value / totalEnergy * 100))}%`;
      bar.value.textContent = `${formatNumber(value)} J`;
    });
    this.sumValue.textContent = `${formatNumber(sum)} J`;
    this.progressValue.textContent = `t = ${Math.round(progress * 100)}%`;
    this.readout.classList.toggle('is-conserved', Math.abs(sum - totalEnergy) < .6);
  }

  buildTimeline(params) {
    const seconds = duration(params, 7.5);
    const state = { progress: 0 };
    this.renderBars(0, params.totalEnergy);
    const tl = gsap.timeline({ paused: true });
    tl.set(this.root, { autoAlpha: 1 }, 0)
      .fromTo(this.root.querySelector('.p2-scene-header'), { y: -22, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .08)
      .fromTo(this.chart, { y: 28, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .6 }, .28)
      .fromTo(this.bars.map(bar => bar.column), { y: 45, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .5, stagger: .12, ease: 'back.out(1.5)' }, .55)
      .fromTo(this.totalLine, { scaleX: 0 }, { scaleX: 1, duration: .7, ease: 'power2.out' }, .8)
      .fromTo(this.readout, { x: 32, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: .5 }, 1.05)
      .to(state, {
        progress: 1,
        duration: Math.max(1.3, seconds - 2.15),
        ease: 'none',
        onUpdate: () => this.renderBars(state.progress, params.totalEnergy)
      }, 1.25);
    return finishTimeline(tl, this.root, seconds);
  }

  teardown() { this.root?.remove(); }

  static getParamSchema() {
    return {
      type: 'object', required: ['bars', 'totalEnergy'], additionalProperties: false,
      properties: {
        bars: {
          type: 'array', minItems: 1, maxItems: 5, default: [{ label: 'Energy', color: 'energy', keyframes: [0, 100] }],
          items: {
            type: 'object', required: ['label', 'keyframes'], additionalProperties: false,
            properties: {
              label: { type: 'string', maxLength: 22, default: 'Energy' },
              color: { type: 'string', enum: ['velocity', 'force', 'label', 'energy'], default: 'energy' },
              keyframes: { type: 'array', minItems: 2, maxItems: 12, default: [0, 100], items: { type: 'number', minimum: 0, maximum: 100000, default: 0 } }
            }
          }
        },
        totalEnergy: { type: 'number', minimum: 1, maximum: 100000, default: 100 },
        showTotalLine: { type: 'boolean', default: true }
      }
    };
  }
}
