import { addArrowMarker, append, clamp, drawPaths, finishPhase3, phase3Root, phase3Timeline, pointLabel, schemas, svg, svgEl } from './_shared.js';

function opticalShape(type) {
  const shapes = {
    converging_lens: 'M700 105 Q790 350 700 595 M740 105 Q650 350 740 595',
    diverging_lens: 'M680 105 Q745 350 680 595 M760 105 Q695 350 760 595',
    concave_mirror: 'M735 105 Q635 350 735 595',
    convex_mirror: 'M695 105 Q795 350 695 595',
    prism: 'M650 555 L760 125 L870 555 Z'
  };
  return shapes[type];
}

export class Scene_RayDiagram {
  setup(container, params) {
    const name = params.opticalElement.replaceAll('_', ' ');
    const frame = phase3Root(container, 'Scene_RayDiagram', 'Geometrical optics', name, 'Principal rays are generated from object distance and focal length.', 'scene-ray-diagram');
    this.root = frame.root;
    this.card = document.createElement('section'); this.card.className = 'p3-ray-card';
    this.diagram = svg('p3-ray-svg', '0 0 1420 700');
    addArrowMarker(this.diagram, 'p3-ray-arrow', '#ffd23f'); addArrowMarker(this.diagram, 'p3-object-arrow', '#00f5ff');
    const centre = 720, axisY = 380, scale = 2, u = clamp(params.objectDistance, 60, 300), fSign = ['diverging_lens','convex_mirror'].includes(params.opticalElement) ? -1 : 1;
    const f = params.focalLength * fSign, v = Math.abs(u - f) < 1 ? 500 : f * u / (u - f), magnification = -v / u;
    const objectX = centre - u * scale, imageX = centre + clamp(v * scale, -520, 520), objectTop = axisY - 155, imageTop = axisY + clamp(magnification * -155, -220, 220);
    this.element = svgEl('path', { d: opticalShape(params.opticalElement), class: `p3-optical-element is-${params.opticalElement}` });
    this.object = svgEl('line', { x1: objectX, y1: axisY, x2: objectX, y2: objectTop, class: 'p3-object-arrow', 'marker-end': 'url(#p3-object-arrow)' });
    this.image = svgEl('line', { x1: imageX, y1: axisY, x2: imageX, y2: imageTop, class: 'p3-image-arrow', 'marker-end': 'url(#p3-ray-arrow)' });
    if (!params.showImage || params.opticalElement === 'prism') this.image.classList.add('is-hidden');
    this.rays = [];
    if (params.opticalElement === 'prism') {
      this.rays.push(svgEl('path', { d: `M${objectX} ${objectTop} L675 300 L785 330 L1260 235`, class: 'p3-principal-ray ray-one', 'marker-end': 'url(#p3-ray-arrow)' }));
      this.rays.push(svgEl('path', { d: `M${objectX} ${objectTop + 45} L690 355 L800 390 L1260 330`, class: 'p3-principal-ray ray-two', 'marker-end': 'url(#p3-ray-arrow)' }));
    } else {
      this.rays.push(svgEl('path', { d: `M${objectX} ${objectTop} L720 ${objectTop} L${imageX} ${imageTop}`, class: 'p3-principal-ray ray-one', 'marker-end': 'url(#p3-ray-arrow)' }));
      this.rays.push(svgEl('path', { d: `M${objectX} ${objectTop} L720 380 L${imageX} ${imageTop}`, class: 'p3-principal-ray ray-two', 'marker-end': 'url(#p3-ray-arrow)' }));
    }
    append(this.diagram, svgEl('line', { x1: 80, y1: axisY, x2: 1340, y2: axisY, class: 'p3-optical-axis' }), this.element, this.object, this.image, ...this.rays);
    if (params.showFocalPoints && params.opticalElement !== 'prism') {
      append(this.diagram,
        svgEl('circle', { cx: centre - Math.abs(params.focalLength) * scale, cy: axisY, r: 8, class: 'p3-focal-point' }),
        svgEl('circle', { cx: centre + Math.abs(params.focalLength) * scale, cy: axisY, r: 8, class: 'p3-focal-point' }),
        pointLabel(centre - Math.abs(params.focalLength) * scale, axisY + 35, 'F', 'p3-svg-label'), pointLabel(centre + Math.abs(params.focalLength) * scale, axisY + 35, 'F', 'p3-svg-label')
      );
    }
    append(this.diagram, pointLabel(objectX, 625, `u = ${params.objectDistance}`, 'p3-motion-stat'), pointLabel(imageX, 625, params.opticalElement === 'prism' ? 'dispersion' : `v ≈ ${Math.abs(v).toFixed(1)}`, 'p3-motion-stat'));
    this.card.appendChild(this.diagram); this.root.appendChild(this.card);
  }
  buildTimeline(params) {
    const tl = phase3Timeline(this.root);
    tl.fromTo(this.card, { y: 25, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .3)
      .fromTo(this.element, { scaleY: .2, autoAlpha: 0, transformOrigin: 'center' }, { scaleY: 1, autoAlpha: 1, duration: .65 }, .6)
      .fromTo(this.object, { scaleY: 0, transformOrigin: 'bottom' }, { scaleY: 1, duration: .5 }, .9);
    drawPaths(tl, this.rays, 1.25, 1.1, .18);
    if (!this.image.classList.contains('is-hidden')) tl.fromTo(this.image, { scaleY: 0, autoAlpha: 0, transformOrigin: 'bottom' }, { scaleY: 1, autoAlpha: 1, duration: .5 }, 2.45);
    return finishPhase3(tl, this.root, params, 6.2);
  }
  teardown() { this.root?.remove(); }
  static getParamSchema() { return { type: 'object', additionalProperties: false, properties: { opticalElement: { type: 'string', enum: ['converging_lens','diverging_lens','concave_mirror','convex_mirror','prism'], default: 'converging_lens' }, objectDistance: schemas.positive(200, 300), focalLength: schemas.positive(100, 250), showFocalPoints: schemas.toggle(true), showImage: schemas.toggle(true) } }; }
}
