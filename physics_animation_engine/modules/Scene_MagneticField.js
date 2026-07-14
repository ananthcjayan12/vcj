import { append, duration, el, finishTimeline, root, svg, svgEl } from '../engine/renderer.js';

function addText(group, x, y, text, className = '') {
  const node = svgEl('text', { x, y, class: className, 'text-anchor': 'middle' });
  node.textContent = text;
  group.appendChild(node);
  return node;
}

function buildBarMagnet(source, lines, labels, params) {
  const magnet = svgEl('g', { class: 'p2-bar-magnet' });
  append(magnet,
    svgEl('rect', { x: 505, y: 298, width: 310, height: 124, rx: 20, class: 'magnet-shell' }),
    svgEl('path', { d: 'M505 318 Q505 298 525 298 H660 V422 H525 Q505 422 505 402 Z', class: 'north-pole' }),
    svgEl('path', { d: 'M660 298 H795 Q815 298 815 318 V402 Q815 422 795 422 H660 Z', class: 'south-pole' })
  );
  addText(magnet, 582, 373, params.poleLabels.north, 'pole-letter');
  addText(magnet, 738, 373, params.poleLabels.south, 'pole-letter');
  source.appendChild(magnet);
  const count = params.fieldLineCount;
  for (let i = 0; i < count; i++) {
    const side = i % 2 ? 1 : -1;
    const layer = Math.floor(i / 2) + 1;
    const y = 340 + side * (30 + layer * 13);
    const spread = 95 + layer * 62;
    lines.push(svgEl('path', { d: `M582 ${y} C ${390 - layer * 24} ${350 + side * spread}, ${930 + layer * 24} ${350 + side * spread}, 738 ${y}`, class: 'p2-field-line', 'marker-end': 'url(#p2-field-arrow)' }));
  }
  addText(labels, 582, 466, 'north pole', 'field-label');
  addText(labels, 738, 466, 'south pole', 'field-label');
}

function buildHorseshoe(source, lines, labels, params) {
  const magnet = svgEl('g', { class: 'p2-horseshoe' });
  append(magnet,
    svgEl('path', { d: 'M470 230 V430 C470 590 850 590 850 430 V230', class: 'horse-body' }),
    svgEl('rect', { x: 428, y: 210, width: 84, height: 160, rx: 16, class: 'north-pole' }),
    svgEl('rect', { x: 808, y: 210, width: 84, height: 160, rx: 16, class: 'south-pole' })
  );
  addText(magnet, 470, 298, params.poleLabels.north, 'pole-letter');
  addText(magnet, 850, 298, params.poleLabels.south, 'pole-letter');
  source.appendChild(magnet);
  const count = params.fieldLineCount;
  for (let i = 0; i < count; i++) {
    const offset = (i - (count - 1) / 2) * 22;
    lines.push(svgEl('path', { d: `M515 ${285 + offset * .28} C610 ${260 + offset}, 710 ${260 + offset}, 805 ${285 + offset * .28}`, class: 'p2-field-line', 'marker-end': 'url(#p2-field-arrow)' }));
  }
  addText(labels, 660, 175, 'strong, nearly uniform field', 'field-label');
}

function buildWire(source, lines, labels, params) {
  const wire = svgEl('g', { class: 'p2-straight-wire' });
  append(wire,
    svgEl('circle', { cx: 660, cy: 350, r: 74, class: 'wire-halo' }),
    svgEl('circle', { cx: 660, cy: 350, r: 46, class: 'wire-core' }),
    svgEl('circle', { cx: 660, cy: 350, r: 8, class: 'wire-dot' })
  );
  source.appendChild(wire);
  const count = params.fieldLineCount;
  for (let i = 0; i < count; i++) {
    const radius = 105 + i * (265 / Math.max(1, count - 1));
    lines.push(svgEl('circle', { cx: 660, cy: 350, r: radius, class: 'p2-field-line', 'marker-end': 'url(#p2-field-arrow)' }));
  }
  addText(labels, 660, 365, 'current out of page', 'wire-label');
  addText(labels, 660, 655, 'field strength decreases with distance', 'field-label');
}

function buildSolenoid(source, lines, labels, params) {
  const coil = svgEl('g', { class: 'p2-solenoid' });
  append(coil, svgEl('rect', { x: 420, y: 270, width: 480, height: 160, rx: 80, class: 'solenoid-core' }));
  for (let i = 0; i < 10; i++) coil.appendChild(svgEl('ellipse', { cx: 450 + i * 47, cy: 350, rx: 34, ry: 112, class: 'solenoid-turn' }));
  source.appendChild(coil);
  const count = params.fieldLineCount;
  for (let i = 0; i < count; i++) {
    const offset = (i - (count - 1) / 2) * 23;
    if (Math.abs(offset) < 75) {
      lines.push(svgEl('path', { d: `M345 ${350 + offset} H975`, class: 'p2-field-line', 'marker-end': 'url(#p2-field-arrow)' }));
    } else {
      const side = offset < 0 ? -1 : 1;
      lines.push(svgEl('path', { d: `M875 ${350 + offset * .4} C1100 ${350 + side * 270}, 220 ${350 + side * 270}, 445 ${350 + offset * .4}`, class: 'p2-field-line', 'marker-end': 'url(#p2-field-arrow)' }));
    }
  }
  addText(labels, 450, 505, params.poleLabels.south, 'pole-chip south-chip');
  addText(labels, 870, 505, params.poleLabels.north, 'pole-chip north-chip');
}

export class Scene_MagneticField {
  setup(container, params) {
    this.root = root(container, 'Scene_MagneticField', 'scene-p2 scene-magnetic-field');
    const names = { bar_magnet: 'Bar magnet', horseshoe: 'Horseshoe magnet', straight_wire: 'Current-carrying wire', solenoid: 'Solenoid' };
    const header = el('header', 'p2-scene-header');
    append(header,
      el('span', 'p2-kicker', { text: 'Invisible influence' }),
      el('h2', '', { text: `${names[params.source]} field` }),
      el('p', '', { text: 'Arrowed lines show field direction; closer spacing means greater strength.' })
    );

    this.card = el('section', 'p2-field-card');
    this.diagram = svg('p2-field-svg', '0 0 1320 700');
    const defs = svgEl('defs');
    const marker = svgEl('marker', { id: 'p2-field-arrow', markerWidth: 9, markerHeight: 9, refX: 7, refY: 4.5, orient: 'auto', markerUnits: 'strokeWidth' });
    marker.appendChild(svgEl('path', { d: 'M0 0 L9 4.5 L0 9 Z', class: 'field-arrow-head' }));
    defs.appendChild(marker);
    const source = svgEl('g', { class: 'p2-field-source' });
    const labelGroup = svgEl('g', { class: 'p2-field-labels' });
    this.lines = [];
    const builders = { bar_magnet: buildBarMagnet, horseshoe: buildHorseshoe, straight_wire: buildWire, solenoid: buildSolenoid };
    builders[params.source](source, this.lines, labelGroup, params);
    if (!params.showFieldLines) this.lines.forEach(line => line.classList.add('is-hidden'));
    if (!params.showLabels) labelGroup.classList.add('is-hidden');
    append(this.diagram, defs, ...this.lines, source, labelGroup);
    this.card.appendChild(this.diagram);

    this.compass = null;
    if (params.showCompass) {
      this.compass = el('div', 'p2-field-compass');
      append(this.compass,
        el('span', 'compass-face', { html: '<small>N</small><small>E</small><small>S</small><small>W</small><i></i><b></b>' }),
        el('strong', '', { text: 'test compass' })
      );
      this.card.appendChild(this.compass);
    }
    append(this.root, header, this.card);
  }

  buildTimeline(params) {
    const seconds = duration(params, 7);
    this.lines.forEach(line => {
      if (line.classList.contains('is-hidden')) return;
      const length = line.getTotalLength();
      gsap.set(line, { strokeDasharray: length, strokeDashoffset: length });
    });
    const tl = gsap.timeline({ paused: true });
    tl.set(this.root, { autoAlpha: 1 }, 0)
      .fromTo(this.root.querySelector('.p2-scene-header'), { y: -22, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .08)
      .fromTo(this.card, { y: 30, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .28)
      .fromTo(this.root.querySelector('.p2-field-source'), { scale: .78, autoAlpha: 0, transformOrigin: 'center' }, { scale: 1, autoAlpha: 1, duration: .72, ease: 'back.out(1.55)' }, .55);
    if (params.showFieldLines) {
      tl.to(this.lines, { strokeDashoffset: 0, duration: 1.75, stagger: .045, ease: 'power1.inOut' }, 1.08);
    }
    tl.fromTo(this.root.querySelector('.p2-field-labels'), { autoAlpha: 0 }, { autoAlpha: params.showLabels ? 1 : 0, duration: .45 }, 2.5);
    if (this.compass) {
      const rotations = { bar_magnet: 62, horseshoe: 90, straight_wire: 142, solenoid: 88 };
      tl.fromTo(this.compass, { x: 24, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: .45 }, 2.4)
        .fromTo(this.compass.querySelector('.compass-face b'), { rotate: -105 }, { rotate: rotations[params.source], duration: 1.25, ease: 'elastic.out(1,.48)' }, 2.65);
    }
    return finishTimeline(tl, this.root, seconds);
  }

  teardown() { this.root?.remove(); }

  static getParamSchema() {
    return {
      type: 'object', required: ['source'], additionalProperties: false,
      properties: {
        source: { type: 'string', enum: ['bar_magnet', 'horseshoe', 'straight_wire', 'solenoid'], default: 'bar_magnet' },
        showFieldLines: { type: 'boolean', default: true },
        fieldLineCount: { type: 'integer', minimum: 4, maximum: 14, default: 8 },
        showCompass: { type: 'boolean', default: false },
        showLabels: { type: 'boolean', default: true },
        poleLabels: {
          type: 'object', required: ['north', 'south'], additionalProperties: false,
          properties: {
            north: { type: 'string', maxLength: 4, default: 'N' },
            south: { type: 'string', maxLength: 4, default: 'S' }
          }
        }
      }
    };
  }
}
