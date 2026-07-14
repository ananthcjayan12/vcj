import { append, duration, el, finishTimeline, root, svg, svgEl } from '../engine/renderer.js';

export class Scene_WaveForm {
  setup(container, params) {
    this.params = params;
    this.root = root(container, 'Scene_WaveForm', 'scene-waveform');
    const header = el('div', 'wf-header');
    append(header, el('span', 'scene-kicker', { text: `${params.waveType} wave` }), el('h2', '', { text: 'A wave transfers energy, not matter' }), el('p', '', { text: `${params.frequency} Hz · ${params.wavelength} px wavelength · ${params.amplitude} px amplitude` }));
    const card = el('div', 'wf-card');
    this.canvas = svg('wf-svg', '0 0 1600 650');
    this.eq = svgEl('line', { class: 'wf-equilibrium', x1: 90, x2: 1510, y1: 330, y2: 330 });
    this.path = svgEl('path', { class: 'wf-wave', d: '' });
    append(this.canvas, this.eq, this.path);
    this.particles = [];
    if (params.particleView || params.waveType === 'longitudinal') {
      for (let i = 0; i < 30; i++) {
        const dot = svgEl('circle', { class: 'wf-particle', cx: 100 + i * 48, cy: 330, r: 7 });
        this.particles.push(dot); this.canvas.appendChild(dot);
      }
    }
    this.labels = el('div', 'wf-labels');
    if (params.showLabels) {
      const requested = params.labels || [];
      if (requested.includes('amplitude')) this.labels.appendChild(el('div', 'wf-measure amplitude-measure', { html: `<i></i><span>Amplitude <b>${params.amplitude}px</b></span>` }));
      if (requested.includes('wavelength')) this.labels.appendChild(el('div', 'wf-measure wavelength-measure', { html: `<i></i><span>Wavelength <b>λ = ${params.wavelength}px</b></span>` }));
      if (requested.includes('frequency')) this.labels.appendChild(el('div', 'wf-stat', { html: `<small>Frequency</small><strong>${params.frequency}<em>Hz</em></strong>` }));
      if (requested.includes('period')) this.labels.appendChild(el('div', 'wf-stat period-stat', { html: `<small>Period</small><strong>${(1 / params.frequency).toFixed(2)}<em>s</em></strong>` }));
    }
    append(card, this.canvas, this.labels); append(this.root, header, card);
    this.state = { time: 0 };
    this.draw(0);
  }

  draw(time) {
    const { amplitude: A, wavelength: lambda, frequency: f, waveType } = this.params;
    if (waveType === 'transverse') {
      let d = '';
      for (let x = 90; x <= 1510; x += 8) {
        const envelope = Math.min(1, Math.max(0, (x - 90) / 150));
        const y = 330 + A * envelope * Math.sin(((x - 90) / lambda) * Math.PI * 2 - time * f * Math.PI * 2);
        d += `${x === 90 ? 'M' : 'L'}${x},${y}`;
      }
      this.path.setAttribute('d', d);
      this.particles.forEach((dot, i) => {
        const x = 100 + i * 48; const y = 330 + A * Math.sin(((x - 90) / lambda) * Math.PI * 2 - time * f * Math.PI * 2);
        dot.setAttribute('cy', y);
      });
    } else {
      this.path.setAttribute('d', '');
      this.particles.forEach((dot, i) => {
        const base = 100 + i * 48;
        const x = base + Math.min(A, 65) * Math.sin((base / lambda) * Math.PI * 2 - time * f * Math.PI * 2);
        dot.setAttribute('cx', x); dot.setAttribute('cy', 330);
        dot.setAttribute('r', 7 + 2 * Math.sin((base / lambda) * Math.PI * 2 - time * f * Math.PI * 2));
      });
    }
  }

  buildTimeline(params) {
    const seconds = duration(params, 7);
    const tl = gsap.timeline({ paused: true });
    tl.set(this.root, { autoAlpha: 1 }, 0)
      .fromTo(this.root.querySelector('.wf-header'), { y: -25, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .6 }, .08)
      .fromTo(this.eq, { attr: { x2: 90 } }, { attr: { x2: 1510 }, duration: .8, ease: 'power2.inOut' }, .12)
      .fromTo(this.path, { autoAlpha: 0 }, { autoAlpha: 1, duration: .4 }, .4)
      .fromTo(this.particles, { scale: 0, transformOrigin: 'center' }, { scale: 1, duration: .32, stagger: .025, ease: 'back.out(1.7)' }, .42)
      .to(this.state, { time: seconds * .56, duration: seconds - .65, ease: 'none', onUpdate: () => this.draw(this.state.time) }, .55)
      .fromTo(this.labels.children, { autoAlpha: 0, y: 18 }, { autoAlpha: 1, y: 0, duration: .48, stagger: .16, ease: 'power2.out' }, 1.35);
    return finishTimeline(tl, this.root, seconds);
  }

  teardown() { this.root?.remove(); }

  static getParamSchema() {
    return { type: 'object', required: ['waveType','amplitude','wavelength','frequency'], additionalProperties: false, properties: {
      waveType: { type: 'string', enum: ['transverse','longitudinal'], default: 'transverse' }, amplitude: { type: 'number', minimum: 20, maximum: 150, default: 90 },
      wavelength: { type: 'number', minimum: 100, maximum: 400, default: 320 }, frequency: { type: 'number', minimum: .5, maximum: 4, default: 1 },
      showLabels: { type: 'boolean', default: true }, labels: { type: 'array', maxItems: 4, default: ['amplitude','wavelength'], items: { type: 'string', enum: ['amplitude','wavelength','frequency','period'], default: 'amplitude' } },
      particleView: { type: 'boolean', default: false }
    }};
  }
}
