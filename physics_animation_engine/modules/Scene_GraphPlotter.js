import { append, color, duration, el, finishTimeline, root, svg, svgEl } from '../engine/renderer.js';

const AREA = { x: 180, y: 80, w: 900, h: 500 };

function mapPoint(point, xAxis, yAxis) {
  const x = AREA.x + ((point[0] - xAxis.min) / (xAxis.max - xAxis.min || 1)) * AREA.w;
  const y = AREA.y + AREA.h - ((point[1] - yAxis.min) / (yAxis.max - yAxis.min || 1)) * AREA.h;
  return [x, y];
}

export class Scene_GraphPlotter {
  setup(container, params) {
    this.root = root(container, 'Scene_GraphPlotter', 'scene-graphplotter');
    const copy = el('div', 'gp-copy');
    append(copy, el('span', 'scene-kicker', { text: 'Live data visualisation' }), el('h2', '', { text: params.title || 'Motion graph' }), el('p', '', { text: `${params.yAxis.label} plotted against ${params.xAxis.label}` }));
    this.graph = svg('gp-graph', '0 0 1260 700');
    const defs = svgEl('defs');
    const filter = svgEl('filter', { id: `graph-glow-${Math.random().toString(36).slice(2)}`, x: '-50%', y: '-50%', width: '200%', height: '200%' });
    filter.appendChild(svgEl('feGaussianBlur', { stdDeviation: '5', result: 'blur' }));
    defs.appendChild(filter);
    this.graph.appendChild(defs);
    this.xAxis = svgEl('line', { class: 'gp-axis', x1: AREA.x, y1: AREA.y + AREA.h, x2: AREA.x + AREA.w, y2: AREA.y + AREA.h });
    this.yAxis = svgEl('line', { class: 'gp-axis', x1: AREA.x, y1: AREA.y + AREA.h, x2: AREA.x, y2: AREA.y });
    append(this.graph, this.xAxis, this.yAxis);

    for (let i = 0; i <= 5; i++) {
      const gx = AREA.x + i * AREA.w / 5;
      const gy = AREA.y + i * AREA.h / 5;
      append(this.graph,
        svgEl('line', { class: 'gp-gridline', x1: gx, y1: AREA.y, x2: gx, y2: AREA.y + AREA.h }),
        svgEl('line', { class: 'gp-gridline', x1: AREA.x, y1: gy, x2: AREA.x + AREA.w, y2: gy })
      );
      const xValue = params.xAxis.min + i * (params.xAxis.max - params.xAxis.min) / 5;
      const yValue = params.yAxis.max - i * (params.yAxis.max - params.yAxis.min) / 5;
      const xt = svgEl('text', { class: 'gp-tick', x: gx, y: AREA.y + AREA.h + 38, 'text-anchor': 'middle' }); xt.textContent = Number(xValue.toFixed(1));
      const yt = svgEl('text', { class: 'gp-tick', x: AREA.x - 28, y: gy + 6, 'text-anchor': 'end' }); yt.textContent = Number(yValue.toFixed(1));
      append(this.graph, xt, yt);
    }
    const xLabel = svgEl('text', { class: 'gp-label', x: AREA.x + AREA.w / 2, y: 675, 'text-anchor': 'middle' }); xLabel.textContent = `${params.xAxis.label} (${params.xAxis.unit || ''})`;
    const yLabel = svgEl('text', { class: 'gp-label', x: 43, y: AREA.y + AREA.h / 2, transform: `rotate(-90 43 ${AREA.y + AREA.h / 2})`, 'text-anchor': 'middle' }); yLabel.textContent = `${params.yAxis.label} (${params.yAxis.unit || ''})`;
    append(this.graph, xLabel, yLabel);

    this.curves = params.curves.map((curve, index) => {
      const points = curve.dataPoints.map(point => mapPoint(point, params.xAxis, params.yAxis));
      const polyline = svgEl('polyline', { class: `gp-curve ${curve.style === 'dashed' ? 'dashed' : ''}`, points: points.map(p => p.join(',')).join(' '), stroke: color(curve.color), fill: 'none' });
      const tracer = svgEl('circle', { class: 'gp-tracer', cx: points[0]?.[0] || AREA.x, cy: points[0]?.[1] || AREA.y + AREA.h, r: 9, fill: color(curve.color) });
      const legend = el('div', 'gp-legend-item', { html: `<i style="--legend:${color(curve.color)}"></i>${curve.label}` });
      this.graph.appendChild(polyline); this.graph.appendChild(tracer);
      return { polyline, tracer, points, legend, state: { progress: 0 }, index };
    });

    this.annotations = (params.annotations || []).map(annotation => {
      const [x, y] = mapPoint([annotation.x, annotation.y], params.xAxis, params.yAxis);
      const group = svgEl('g', { class: 'gp-annotation', transform: `translate(${x} ${y})` });
      const line = svgEl('line', { x1: 0, y1: 0, x2: 0, y2: -55 });
      const rect = svgEl('rect', { x: -120, y: -105, width: 240, height: 45, rx: 8 });
      const text = svgEl('text', { x: 0, y: -77, 'text-anchor': 'middle' }); text.textContent = annotation.text;
      append(group, line, rect, text); this.graph.appendChild(group);
      return { group, x: annotation.x };
    });
    const legend = el('div', 'gp-legend'); append(legend, this.curves.map(item => item.legend));
    const chartCard = el('div', 'gp-card'); append(chartCard, this.graph, legend);
    append(this.root, copy, chartCard);
  }

  buildTimeline(params) {
    const seconds = duration(params, 7);
    const tl = gsap.timeline({ paused: true });
    tl.set(this.root, { autoAlpha: 1 }, 0)
      .fromTo(this.root.querySelector('.gp-copy'), { x: -35, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: .65 }, .08)
      .fromTo(this.xAxis, { attr: { x2: AREA.x } }, { attr: { x2: AREA.x + AREA.w }, duration: .7, ease: 'power2.inOut' }, .15)
      .fromTo(this.yAxis, { attr: { y2: AREA.y + AREA.h } }, { attr: { y2: AREA.y }, duration: .7, ease: 'power2.inOut' }, .15)
      .fromTo(this.graph.querySelectorAll('.gp-gridline, .gp-tick, .gp-label'), { autoAlpha: 0 }, { autoAlpha: 1, duration: .45, stagger: .018 }, .55)
      .fromTo(this.root.querySelector('.gp-legend'), { autoAlpha: 0, y: 12 }, { autoAlpha: 1, y: 0, duration: .4 }, .78);
    this.curves.forEach((curve, curveIndex) => {
      const length = curve.polyline.getTotalLength();
      gsap.set(curve.polyline, { strokeDasharray: length, strokeDashoffset: length });
      tl.to(curve.polyline, { strokeDashoffset: 0, duration: Math.max(2.4, seconds - 2.4), ease: 'power1.inOut' }, .9 + curveIndex * .25)
        .to(curve.state, { progress: 1, duration: Math.max(2.4, seconds - 2.4), ease: 'power1.inOut', onUpdate: () => {
          const total = curve.polyline.getTotalLength();
          const point = curve.polyline.getPointAtLength(total * curve.state.progress);
          curve.tracer.setAttribute('cx', point.x); curve.tracer.setAttribute('cy', point.y);
        }}, .9 + curveIndex * .25);
    });
    this.annotations.forEach((annotation, index) => tl.fromTo(annotation.group, { autoAlpha: 0, scale: .7, transformOrigin: 'center' }, { autoAlpha: 1, scale: 1, duration: .42, ease: 'back.out(1.8)' }, Math.min(seconds - 1.2, 2.6 + index * .6)));
    return finishTimeline(tl, this.root, seconds);
  }

  teardown() { this.root?.remove(); }

  static getParamSchema() {
    const axis = { type: 'object', required: ['label','min','max'], properties: { label: { type: 'string', maxLength: 30, default: 'Axis' }, min: { type: 'number', default: 0 }, max: { type: 'number', default: 10 }, unit: { type: 'string', maxLength: 12, default: '' } } };
    return { type: 'object', required: ['xAxis','yAxis','curves'], additionalProperties: false, properties: {
      title: { type: 'string', maxLength: 70, default: 'Graph' }, xAxis: axis, yAxis: axis,
      curves: { type: 'array', minItems: 1, maxItems: 4, default: [], items: { type: 'object', required: ['label','dataPoints'], properties: {
        label: { type: 'string', maxLength: 40, default: 'Series' }, color: { type: 'string', enum: ['velocity','force','label','energy'], default: 'velocity' },
        dataPoints: { type: 'array', minItems: 2, maxItems: 30, default: [[0,0],[10,10]], items: { type: 'array', minItems: 2, maxItems: 2, items: { type: 'number', default: 0 } } },
        style: { type: 'string', enum: ['solid','dashed'], default: 'solid' }
      }}}, annotations: { type: 'array', maxItems: 5, default: [], items: { type: 'object', required: ['x','y','text'], properties: { x: { type: 'number', default: 0 }, y: { type: 'number', default: 0 }, text: { type: 'string', maxLength: 60, default: 'Point of interest' } } } }
    }};
  }
}
