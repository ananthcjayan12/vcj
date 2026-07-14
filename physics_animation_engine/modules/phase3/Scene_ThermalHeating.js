import { append, drawPaths, finishPhase3, phase3Root, phase3Timeline, pointLabel, schemas, svg, svgEl } from './_shared.js';

function heatingPoints(params) {
  const changes = params.stateChanges.filter(change => change.at > Math.min(params.startTemp, params.endTemp) && change.at < Math.max(params.startTemp, params.endTemp)).sort((a, b) => a.at - b.at);
  const segments = changes.length + 1;
  const points = [{ temp: params.startTemp, weight: 0 }];
  changes.forEach((change, index) => {
    const base = (index + .62) / segments;
    points.push({ temp: change.at, weight: base - .12, change });
    points.push({ temp: change.at, weight: base + .12, change });
  });
  points.push({ temp: params.endTemp, weight: 1 });
  return points;
}

export class Scene_ThermalHeating {
  setup(container, params) {
    const frame = phase3Root(container, 'Scene_ThermalHeating', 'Energy and state', `Heating ${params.substance}`, `${params.startTemp}°C to ${params.endTemp}°C with state-change plateaus computed from the supplied temperatures.`, 'scene-thermal-heating');
    this.root = frame.root;
    this.card = document.createElement('section'); this.card.className = 'p3-graph-card';
    this.diagram = svg('p3-heating-svg', '0 0 1420 700');
    const min = Math.min(params.startTemp, params.endTemp) - 10, max = Math.max(params.startTemp, params.endTemp) + 10;
    const mapY = value => 555 - (value - min) / (max - min) * 430;
    const points = heatingPoints(params).map(point => ({ ...point, x: 150 + point.weight * 1120, y: mapY(point.temp) }));
    this.curve = svgEl('path', { d: points.map((point, index) => `${index ? 'L' : 'M'}${point.x} ${point.y}`).join(' '), class: 'p3-heating-curve' });
    append(this.diagram,
      svgEl('line', { x1: 130, y1: 575, x2: 1310, y2: 575, class: 'p3-chart-axis' }),
      svgEl('line', { x1: 130, y1: 575, x2: 130, y2: 95, class: 'p3-chart-axis' }),
      pointLabel(720, 645, 'Energy supplied →', 'p3-axis-label'),
      pointLabel(55, 330, 'Temperature (°C)', 'p3-axis-label vertical'),
      this.curve
    );
    this.markers = [];
    params.stateChanges.forEach(change => {
      const match = points.find(point => point.change?.type === change.type);
      if (!match) return;
      const group = svgEl('g', { class: 'p3-state-change' });
      append(group,
        svgEl('line', { x1: match.x, y1: match.y, x2: match.x, y2: match.y - 70 }),
        svgEl('rect', { x: match.x - 72, y: match.y - 118, width: 144, height: 42, rx: 8 }),
        pointLabel(match.x, match.y - 91, `${change.type} · ${change.at}°C`, 'p3-state-label')
      );
      this.diagram.appendChild(group); this.markers.push(group);
    });
    this.cursor = svgEl('circle', { r: 12, class: 'p3-heating-cursor' }); this.diagram.appendChild(this.cursor);
    this.card.appendChild(this.diagram); this.root.appendChild(this.card);
  }
  buildTimeline(params) {
    const tl = phase3Timeline(this.root), length = this.curve.getTotalLength(), state = { progress: 0 };
    gsap.set(this.curve, { strokeDasharray: length, strokeDashoffset: length });
    tl.fromTo(this.card, { y: 25, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .3)
      .to(this.curve, { strokeDashoffset: 0, duration: 3.3, ease: 'none' }, .75)
      .to(state, { progress: 1, duration: 3.3, ease: 'none', onUpdate: () => { const point = this.curve.getPointAtLength(length * state.progress); this.cursor.setAttribute('cx', point.x); this.cursor.setAttribute('cy', point.y); } }, .75)
      .fromTo(this.markers, { y: 15, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .4, stagger: .28 }, 2.1);
    return finishPhase3(tl, this.root, params, 6.5);
  }
  teardown() { this.root?.remove(); }
  static getParamSchema() {
    return { type: 'object', required: ['substance', 'startTemp', 'endTemp'], additionalProperties: false, properties: { substance: schemas.shortText('Water', 30), startTemp: { type: 'number', minimum: -273, maximum: 3000, default: 20 }, endTemp: { type: 'number', minimum: -273, maximum: 3000, default: 120 }, stateChanges: { type: 'array', maxItems: 4, default: [], items: { type: 'object', required: ['at', 'type'], additionalProperties: false, properties: { at: { type: 'number', minimum: -273, maximum: 3000, default: 100 }, type: { type: 'string', enum: ['melting', 'boiling', 'freezing', 'condensing'], default: 'boiling' } } } } } };
  }
}
