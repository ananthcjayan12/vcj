import { append, duration, el, finishTimeline, root, svg, svgEl } from '../engine/renderer.js';

function componentSymbol(component, x, y) {
  const group = svgEl('g', { class: `cd-component cd-${component.type}`, transform: `translate(${x} ${y})` });
  const plate = svgEl('rect', { class: 'cd-component-plate', x: -72, y: -50, width: 144, height: 100, rx: 14 });
  group.appendChild(plate);
  if (component.type === 'cell') {
    append(group, svgEl('line', { x1: -13, y1: -25, x2: -13, y2: 25 }), svgEl('line', { x1: 13, y1: -14, x2: 13, y2: 14 }));
  } else if (component.type === 'resistor') {
    group.appendChild(svgEl('path', { d: 'M-47 0 L-34 -17 L-17 17 L0 -17 L17 17 L34 -17 L47 0' }));
  } else if (component.type === 'lamp') {
    append(group, svgEl('circle', { cx: 0, cy: 0, r: 27 }), svgEl('line', { x1: -18, y1: -18, x2: 18, y2: 18 }), svgEl('line', { x1: 18, y1: -18, x2: -18, y2: 18 }));
  } else {
    const circle = svgEl('circle', { cx: 0, cy: 0, r: 27 }); const text = svgEl('text', { x: 0, y: 9, 'text-anchor': 'middle' }); text.textContent = component.type === 'voltmeter' ? 'V' : 'A'; append(group, circle, text);
  }
  const label = svgEl('text', { class: 'cd-component-label', x: 0, y: 78, 'text-anchor': 'middle' }); label.textContent = component.label || component.type;
  group.appendChild(label);
  return group;
}

export class Scene_CircuitDiagram {
  setup(container, params) {
    this.params = params;
    this.root = root(container, 'Scene_CircuitDiagram', 'scene-circuitdiagram');
    const header = el('div', 'cd-header');
    append(header, el('span', 'scene-kicker', { text: `${params.type} circuit` }), el('h2', '', { text: 'Follow the current around the loop' }), el('p', '', { text: `${params.currentDirection === 'electron' ? 'Electron' : 'Conventional'} current direction` }));
    const card = el('div', 'cd-card'); this.canvas = svg('cd-svg', '0 0 1500 700');
    const wireD = params.type === 'parallel' ? 'M250 150 H1250 V550 H250 Z M600 150 V550 M900 150 V550' : 'M250 150 H1250 V550 H250 Z';
    this.wire = svgEl('path', { class: 'cd-wire', d: wireD }); this.canvas.appendChild(this.wire);
    const positions = { top: [750,150], right: [1250,350], bottom: [750,550], left: [250,350] };
    this.components = params.components.map((component, index) => {
      const fallback = [[750,150],[1250,350],[750,550],[250,350]][index % 4];
      const [x,y] = positions[component.position] || fallback;
      const symbol = componentSymbol(component, x, y); this.canvas.appendChild(symbol); return symbol;
    });
    this.dots = [];
    if (params.showCurrentFlow) for (let i = 0; i < 11; i++) { const dot = svgEl('circle', { class: 'cd-current-dot', r: 8 }); this.dots.push(dot); this.canvas.appendChild(dot); }
    const legend = el('div', 'cd-direction', { html: `<i>→</i><span><small>Current flow</small>${params.currentDirection === 'electron' ? 'Electron flow' : 'Conventional current'}</span>` });
    append(card, this.canvas, params.showCurrentFlow ? legend : null); append(this.root, header, card); this.state = { progress: 0 };
  }

  moveDots() {
    const length = this.wire.getTotalLength();
    this.dots.forEach((dot, index) => {
      const direction = this.params.currentDirection === 'electron' ? -1 : 1;
      const p = ((this.state.progress * direction + index / this.dots.length) % 1 + 1) % 1;
      const point = this.wire.getPointAtLength(p * length); dot.setAttribute('cx', point.x); dot.setAttribute('cy', point.y);
    });
  }

  buildTimeline(params) {
    const seconds = duration(params, 7);
    const length = this.wire.getTotalLength(); gsap.set(this.wire, { strokeDasharray: length, strokeDashoffset: length }); this.moveDots();
    const tl = gsap.timeline({ paused: true });
    tl.set(this.root, { autoAlpha: 1 }, 0)
      .fromTo(this.root.querySelector('.cd-header'), { x: -30, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: .6 }, .08)
      .to(this.wire, { strokeDashoffset: 0, duration: 1, ease: 'power2.inOut' }, .1)
      .fromTo(this.components, { scale: 0, autoAlpha: 0, transformOrigin: 'center' }, { scale: 1, autoAlpha: 1, duration: .48, stagger: .18, ease: 'back.out(1.6)' }, .62)
      .fromTo(this.root.querySelectorAll('.cd-component-label'), { autoAlpha: 0, y: 10 }, { autoAlpha: 1, y: 0, duration: .35, stagger: .14 }, 1.15);
    if (params.showCurrentFlow) {
      tl.fromTo(this.dots, { autoAlpha: 0, scale: 0, transformOrigin: 'center' }, { autoAlpha: 1, scale: 1, duration: .28, stagger: .04 }, 1.75)
        .to(this.state, { progress: 2.8, duration: Math.max(1.5, seconds - 2.2), ease: 'none', onUpdate: () => this.moveDots() }, 1.9)
        .fromTo(this.root.querySelector('.cd-direction'), { autoAlpha: 0, x: 20 }, { autoAlpha: 1, x: 0, duration: .45 }, 2);
    }
    return finishTimeline(tl, this.root, seconds);
  }

  teardown() { this.root?.remove(); }

  static getParamSchema() {
    return { type: 'object', required: ['type','components'], additionalProperties: false, properties: {
      type: { type: 'string', enum: ['series','parallel','mixed'], default: 'series' },
      components: { type: 'array', minItems: 2, maxItems: 8, default: [], items: { type: 'object', required: ['type','position'], properties: {
        type: { type: 'string', enum: ['cell','resistor','lamp','ammeter','voltmeter'], default: 'resistor' }, label: { type: 'string', maxLength: 30, default: '' },
        position: { type: 'string', enum: ['top','right','bottom','left'], default: 'top' }
      }}}, showCurrentFlow: { type: 'boolean', default: true }, currentDirection: { type: 'string', enum: ['conventional','electron'], default: 'conventional' }
    }};
  }
}
