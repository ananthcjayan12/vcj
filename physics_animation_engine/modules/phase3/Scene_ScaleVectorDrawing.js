import { addArrowMarker, append, cueTimes, drawPaths, finishPhase3, phase3Root, phase3Timeline, pointLabel, schemas, svg, svgEl } from './_shared.js';

export class Scene_ScaleVectorDrawing {
  setup(container, params) {
    const frame = phase3Root(container, 'Scene_ScaleVectorDrawing', 'Magnitude → scale → arrow', 'Draw a vector to scale', 'A numerical magnitude becomes a measured arrow length with a labelled direction.', 'scene-scale-vector');
    this.root = frame.root;
    this.card = document.createElement('section'); this.card.className = 'p3-vector-card';
    this.diagram = svg('p3-scale-vector-svg', '0 0 1500 680');
    addArrowMarker(this.diagram, 'scale-vector-head', '#ff5a36');
    this.scaleCard = svgEl('g', { class: 'p3-scale-rule-card' });
    append(this.scaleCard, svgEl('rect', { x: 120, y: 120, width: 380, height: 150, rx: 18 }), pointLabel(310, 174, 'chosen scale', 'p3-counter-label'), pointLabel(310, 232, params.scaleStatement, 'p3-scale-statement'));
    this.ruler = svgEl('g', { class: 'p3-vector-ruler' });
    this.ruler.appendChild(svgEl('line', { x1: 290, y1: 490, x2: 1210, y2: 490 }));
    this.ticks = Array.from({ length: 11 }, (_, index) => {
      const x = 290 + index * 92;
      const tick = svgEl('line', { x1: x, y1: 468, x2: x, y2: index % 5 === 0 ? 530 : 512 });
      this.ruler.appendChild(tick);
      if (index % 2 === 0) this.ruler.appendChild(pointLabel(x, 556, `${index}`, 'p3-vector-note'));
      return tick;
    });
    this.arrow = svgEl('line', { x1: 290, y1: 420, x2: 1030, y2: 420, class: 'p3-construction-vector resultant', 'marker-end': 'url(#scale-vector-head)' });
    this.measure = svgEl('line', { x1: 290, y1: 360, x2: 1030, y2: 360, class: 'p3-measure-bracket' });
    append(this.diagram, this.scaleCard, this.ruler, this.measure, this.arrow,
      pointLabel(660, 330, `${params.drawnLength} cm on paper`, 'p3-scale-statement'),
      pointLabel(660, 400, `${params.vectorLabel}: ${params.magnitude} ${params.unit}`, 'p3-vector-name resultant'),
      pointLabel(1110, 405, params.directionLabel, 'p3-vector-note'));
    this.card.appendChild(this.diagram); this.root.appendChild(this.card);
  }

  buildTimeline(params) {
    const cues = cueTimes(params, 5);
    const tl = phase3Timeline(this.root);
    tl.fromTo(this.card, { y: 25, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55, ease: 'power3.out' }, cues[0])
      .fromTo(this.scaleCard, { x: -35, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: .5, ease: 'power2.out' }, cues[1])
      .fromTo(this.ruler, { y: 35, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55, ease: 'power3.out' }, cues[2])
      .fromTo(this.ticks, { scaleY: 0, transformOrigin: 'bottom' }, { scaleY: 1, duration: .22, stagger: .035, ease: 'power2.out' }, cues[2]);
    drawPaths(tl, [this.measure], cues[3], .65, 0);
    drawPaths(tl, [this.arrow], cues[4], 1.05, 0);
    tl.fromTo(this.diagram.querySelectorAll('.p3-vector-name,.p3-vector-note'), { autoAlpha: 0 }, { autoAlpha: 1, duration: .4, stagger: .08, ease: 'power2.out' }, cues[4] + .35);
    return finishPhase3(tl, this.root, params, 9);
  }

  teardown() { this.root?.remove(); }
  static getParamSchema() {
    return { type: 'object', required: ['vectorLabel', 'magnitude', 'unit', 'scaleStatement', 'drawnLength', 'directionLabel'], additionalProperties: false, properties: {
      vectorLabel: schemas.shortText('force', 30), magnitude: schemas.positive(10, 100000), unit: schemas.shortText('N', 12),
      scaleStatement: schemas.shortText('1 cm represents 2 N', 60), drawnLength: schemas.positive(5, 50), directionLabel: schemas.shortText('east', 24)
    } };
  }
}
