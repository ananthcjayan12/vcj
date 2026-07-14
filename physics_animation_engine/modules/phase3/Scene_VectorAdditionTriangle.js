import { addArrowMarker, append, cueTimes, drawPaths, finishPhase3, phase3Root, phase3Timeline, pointLabel, schemas, svg, svgEl } from './_shared.js';

export class Scene_VectorAdditionTriangle {
  setup(container, params) {
    const frame = phase3Root(container, 'Scene_VectorAdditionTriangle', 'Head-to-tail construction', 'Add vectors geometrically', 'The second vector starts at the first arrowhead; the resultant joins start to finish.', 'scene-vector-triangle');
    this.root = frame.root;
    this.card = document.createElement('section'); this.card.className = 'p3-vector-card';
    this.diagram = svg('p3-vector-svg', '0 0 1500 680');
    addArrowMarker(this.diagram, 'vector-a-head', '#00f5ff');
    addArrowMarker(this.diagram, 'vector-b-head', '#ffd23f');
    addArrowMarker(this.diagram, 'vector-r-head', '#ff5a36');
    this.first = svgEl('line', { x1: 260, y1: 500, x2: 870, y2: 500, class: 'p3-construction-vector first', 'marker-end': 'url(#vector-a-head)' });
    this.second = svgEl('line', { x1: 870, y1: 500, x2: 1160, y2: 190, class: 'p3-construction-vector second', 'marker-end': 'url(#vector-b-head)' });
    this.resultant = svgEl('line', { x1: 260, y1: 500, x2: 1160, y2: 190, class: 'p3-construction-vector resultant', 'marker-end': 'url(#vector-r-head)' });
    this.joint = svgEl('circle', { cx: 870, cy: 500, r: 11, class: 'p3-vector-joint' });
    append(this.diagram, this.first, this.second, this.resultant, this.joint,
      pointLabel(565, 548, params.firstLabel, 'p3-vector-name first'),
      pointLabel(1045, 365, params.secondLabel, 'p3-vector-name second'),
      pointLabel(675, 300, params.resultantLabel, 'p3-vector-name resultant'),
      pointLabel(870, 550, 'head → tail', 'p3-vector-note'));
    this.card.appendChild(this.diagram); this.root.appendChild(this.card);
  }

  buildTimeline(params) {
    const cues = cueTimes(params, 5);
    const tl = phase3Timeline(this.root);
    tl.fromTo(this.card, { y: 25, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55, ease: 'power3.out' }, cues[0]);
    drawPaths(tl, [this.first], cues[1], .85, 0);
    tl.fromTo(this.joint, { scale: 0, transformOrigin: 'center' }, { scale: 1, duration: .35, ease: 'back.out(1.8)' }, cues[2]);
    drawPaths(tl, [this.second], cues[2], .85, 0);
    drawPaths(tl, [this.resultant], cues[3], 1.05, 0);
    tl.fromTo(this.diagram.querySelectorAll('.p3-vector-name,.p3-vector-note'), { y: 12, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .4, stagger: .1, ease: 'power2.out' }, cues[4]);
    return finishPhase3(tl, this.root, params, 9);
  }

  teardown() { this.root?.remove(); }
  static getParamSchema() {
    return { type: 'object', required: ['firstLabel', 'secondLabel', 'resultantLabel'], additionalProperties: false, properties: {
      firstLabel: schemas.shortText('vector A', 35), secondLabel: schemas.shortText('vector B', 35), resultantLabel: schemas.shortText('resultant R', 35)
    } };
  }
}
