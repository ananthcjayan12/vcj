import { append, color, duration, el, finishTimeline, formatNumber, root, svg, svgEl } from '../engine/renderer.js';

function flowPath(startY, endY) {
  return `M 365 ${startY} C 580 ${startY}, 650 ${endY}, 920 ${endY}`;
}

export class Scene_SankeyDiagram {
  setup(container, params) {
    this.root = root(container, 'Scene_SankeyDiagram', 'scene-p2 scene-sankey-diagram');
    const inputValue = Math.max(1, params.inputEnergy.value);
    const usefulValue = params.outputs.reduce((sum, output) => sum + (output.useful ? output.value : 0), 0);
    const outputValue = params.outputs.reduce((sum, output) => sum + output.value, 0);
    const efficiency = usefulValue / inputValue * 100;

    const header = el('header', 'p2-scene-header');
    append(header,
      el('span', 'p2-kicker', { text: 'Energy pathways' }),
      el('h2', '', { text: 'Where does the energy go?' }),
      el('p', '', { text: 'Every branch is scaled from the values in the scene specification.' })
    );

    this.canvas = el('section', 'p2-sankey-canvas');
    this.diagram = svg('p2-sankey-svg', '0 0 1320 680');
    const defs = svgEl('defs');
    const glow = svgEl('filter', { id: 'p2-sankey-glow', x: '-30%', y: '-30%', width: '160%', height: '160%' });
    append(glow, svgEl('feGaussianBlur', { stdDeviation: '7', result: 'blur' }), svgEl('feMerge'));
    glow.lastChild.append(svgEl('feMergeNode', { in: 'blur' }), svgEl('feMergeNode', { in: 'SourceGraphic' }));
    defs.appendChild(glow);
    this.diagram.appendChild(defs);

    this.inputPath = svgEl('path', {
      class: 'p2-sankey-flow input-flow', d: 'M 70 340 C 170 340, 250 340, 365 340',
      stroke: color('neutral'), 'stroke-width': '82'
    });
    const inputNode = svgEl('g', { class: 'p2-sankey-input-node' });
    append(inputNode,
      svgEl('rect', { x: '64', y: '260', width: '300', height: '160', rx: '24' }),
      svgEl('text', { x: '105', y: '316', class: 'node-label' }),
      svgEl('text', { x: '105', y: '372', class: 'node-value' })
    );
    inputNode.children[1].textContent = params.inputEnergy.label;
    inputNode.children[2].textContent = `${formatNumber(inputValue)} ${params.inputEnergy.unit}`;
    append(this.diagram, this.inputPath, inputNode);

    const count = params.outputs.length;
    const spacing = Math.min(160, 500 / Math.max(1, count - 1));
    const firstY = 340 - spacing * (count - 1) / 2;
    this.branches = params.outputs.map((output, index) => {
      const y = firstY + spacing * index;
      const width = Math.max(16, output.value / inputValue * 112);
      const group = svgEl('g', { class: `p2-sankey-output ${output.useful ? 'is-useful' : 'is-wasted'}` });
      const path = svgEl('path', {
        class: 'p2-sankey-flow output-flow', d: flowPath(340, y),
        stroke: color(output.color), 'stroke-width': width
      });
      const node = svgEl('rect', { x: '920', y: y - 52, width: '330', height: '104', rx: '17' });
      const label = svgEl('text', { x: '955', y: y - 9, class: 'node-label' });
      const value = svgEl('text', { x: '955', y: y + 28, class: 'output-value' });
      const tag = svgEl('text', { x: '1213', y: y + 5, class: 'output-tag', 'text-anchor': 'end' });
      label.textContent = output.label;
      value.textContent = `${formatNumber(output.value)} ${params.inputEnergy.unit}`;
      tag.textContent = output.useful ? 'USEFUL' : 'DISSIPATED';
      append(group, path, node, label, value, tag);
      this.diagram.appendChild(group);
      return { group, path };
    });

    const balance = el('div', `p2-energy-balance ${Math.abs(outputValue - inputValue) < .01 ? 'is-balanced' : 'is-unbalanced'}`);
    append(balance,
      el('span', '', { text: 'Energy balance' }),
      el('strong', '', { text: `${formatNumber(inputValue)} ${params.inputEnergy.unit} in · ${formatNumber(outputValue)} ${params.inputEnergy.unit} out` }),
      el('i', '', { text: Math.abs(outputValue - inputValue) < .01 ? 'conserved' : 'check values' })
    );
    append(this.canvas, this.diagram, balance);

    this.efficiency = null;
    if (params.showEfficiency) {
      this.efficiency = el('aside', 'p2-efficiency-card');
      const ring = el('span', 'p2-efficiency-ring');
      ring.style.setProperty('--efficiency', `${Math.min(100, Math.max(0, efficiency)) * 3.6}deg`);
      append(ring, el('b', '', { text: `${formatNumber(efficiency)}%` }));
      append(this.efficiency,
        ring,
        el('span', '', { html: '<small>overall efficiency</small><strong>useful ÷ input × 100</strong>' })
      );
    }
    append(this.root, header, this.canvas, this.efficiency);
  }

  buildTimeline(params) {
    const seconds = duration(params, 7);
    [this.inputPath, ...this.branches.map(branch => branch.path)].forEach(path => {
      const length = path.getTotalLength();
      gsap.set(path, { strokeDasharray: length, strokeDashoffset: length });
    });
    const tl = gsap.timeline({ paused: true });
    tl.set(this.root, { autoAlpha: 1 }, 0)
      .fromTo(this.root.querySelector('.p2-scene-header'), { y: -22, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .08)
      .fromTo(this.canvas, { y: 28, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .3)
      .to(this.inputPath, { strokeDashoffset: 0, duration: 1.05, ease: 'power2.inOut' }, .65)
      .fromTo(this.root.querySelector('.p2-sankey-input-node'), { scale: .9, autoAlpha: 0, transformOrigin: 'center' }, { scale: 1, autoAlpha: 1, duration: .45 }, .85);
    this.branches.forEach((branch, index) => {
      const start = 1.45 + index * .23;
      tl.to(branch.path, { strokeDashoffset: 0, duration: 1.15, ease: 'power2.inOut' }, start)
        .fromTo([...branch.group.children].slice(1), { x: 28, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: .42, stagger: .05 }, start + .55);
    });
    tl.fromTo(this.root.querySelector('.p2-energy-balance'), { y: 16, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .4 }, 3.35);
    if (this.efficiency) {
      tl.fromTo(this.efficiency, { scale: .78, autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: .58, ease: 'back.out(1.7)' }, 3.65)
        .fromTo(this.efficiency.querySelector('.p2-efficiency-ring'), { '--efficiency': '0deg' }, { '--efficiency': this.efficiency.querySelector('.p2-efficiency-ring').style.getPropertyValue('--efficiency'), duration: .9 }, 3.7);
    }
    return finishTimeline(tl, this.root, seconds);
  }

  teardown() { this.root?.remove(); }

  static getParamSchema() {
    return {
      type: 'object', required: ['inputEnergy', 'outputs'], additionalProperties: false,
      properties: {
        inputEnergy: {
          type: 'object', required: ['label', 'value'], additionalProperties: false,
          properties: {
            label: { type: 'string', maxLength: 48, default: 'Input energy' },
            value: { type: 'number', minimum: 1, maximum: 100000, default: 100 },
            unit: { type: 'string', maxLength: 10, default: 'J' }
          }
        },
        outputs: {
          type: 'array', minItems: 1, maxItems: 4, default: [{ label: 'Useful', value: 100, color: 'energy', useful: true }],
          items: {
            type: 'object', required: ['label', 'value'], additionalProperties: false,
            properties: {
              label: { type: 'string', maxLength: 38, default: 'Output' },
              value: { type: 'number', minimum: 0, maximum: 100000, default: 0 },
              color: { type: 'string', enum: ['velocity', 'force', 'label', 'energy'], default: 'energy' },
              useful: { type: 'boolean', default: false }
            }
          }
        },
        showEfficiency: { type: 'boolean', default: true }
      }
    };
  }
}
