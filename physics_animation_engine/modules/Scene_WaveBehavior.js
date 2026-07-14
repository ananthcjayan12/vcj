import { append, duration, el, finishTimeline, root, svg, svgEl } from '../engine/renderer.js';

function line(x1, y1, x2, y2, className) {
  return svgEl('line', { x1, y1, x2, y2, class: className });
}

function label(x, y, text, className = 'p2-wave-label') {
  const node = svgEl('text', { x, y, class: className, 'text-anchor': 'middle' });
  node.textContent = text;
  return node;
}

function addIncoming(group, angle, count = 6) {
  const skew = Math.tan((90 - Math.min(82, Math.max(8, angle))) * Math.PI / 180) * 95;
  for (let index = 0; index < count; index++) {
    const x = 110 + index * 92;
    group.appendChild(line(x - skew, 575, x + skew, 150, 'p2-wavefront incoming-front'));
  }
}

function addReflection(outgoing, angle) {
  const skew = Math.tan((90 - Math.min(82, Math.max(8, angle))) * Math.PI / 180) * 95;
  for (let index = 0; index < 6; index++) {
    const x = 650 - index * 92;
    outgoing.push(line(x + skew, 575, x - skew, 150, 'p2-wavefront outgoing-front reflected-front'));
  }
}

function addRefraction(outgoing, angle, speedRatio) {
  const refracted = Math.asin(Math.min(.98, Math.sin(angle * Math.PI / 180) * speedRatio)) * 180 / Math.PI;
  const skew = Math.tan((90 - Math.min(82, Math.max(8, refracted))) * Math.PI / 180) * 95;
  for (let index = 0; index < 6; index++) {
    const x = 805 + index * 92;
    outgoing.push(line(x - skew, 575, x + skew, 150, 'p2-wavefront outgoing-front refracted-front'));
  }
  return refracted;
}

function addDiffraction(outgoing, gapWidth) {
  const gap = gapWidth === 'wide' ? 150 : 72;
  for (let index = 0; index < 6; index++) {
    const radius = 75 + index * 95;
    outgoing.push(svgEl('path', { d: `M760 ${350 - gap / 2} A${radius} ${radius} 0 0 1 760 ${350 + gap / 2}`, class: 'p2-wavefront outgoing-front diffraction-front' }));
  }
  return gap;
}

export class Scene_WaveBehavior {
  setup(container, params) {
    this.root = root(container, 'Scene_WaveBehavior', 'scene-p2 scene-wave-behavior');
    const descriptions = {
      reflection: 'Wavefronts return to the original medium at the same angle.',
      refraction: 'A speed change bends the wave as it enters a new medium.',
      diffraction: 'Wavefronts spread after passing through a gap.'
    };
    const header = el('header', 'p2-scene-header');
    append(header,
      el('span', 'p2-kicker', { text: 'Wave interactions' }),
      el('h2', '', { text: params.behavior[0].toUpperCase() + params.behavior.slice(1) }),
      el('p', '', { text: descriptions[params.behavior] })
    );

    this.card = el('section', 'p2-wave-card');
    this.diagram = svg('p2-wave-behavior-svg', '0 0 1320 700');
    const defs = svgEl('defs');
    const marker = svgEl('marker', { id: 'p2-wave-ray-arrow', markerWidth: 9, markerHeight: 9, refX: 7, refY: 4.5, orient: 'auto' });
    marker.appendChild(svgEl('path', { d: 'M0 0 L9 4.5 L0 9 Z', class: 'wave-ray-arrow' }));
    defs.appendChild(marker);
    const medium1 = svgEl('rect', { x: 0, y: 0, width: params.behavior === 'diffraction' ? 1320 : 660, height: 700, class: 'p2-wave-medium medium-one' });
    const medium2 = svgEl('rect', { x: 660, y: 0, width: 660, height: 700, class: 'p2-wave-medium medium-two' });
    if (params.behavior === 'reflection' || params.behavior === 'diffraction') medium2.classList.add('same-medium');
    append(this.diagram, defs, medium1, medium2);

    this.incomingGroup = svgEl('g', { class: 'p2-incoming-wavefronts' });
    addIncoming(this.incomingGroup, params.behavior === 'diffraction' ? 90 : params.incidentAngle);
    this.outgoing = [];
    let secondaryAngle = params.incidentAngle;

    if (params.behavior === 'reflection') {
      addReflection(this.outgoing, params.incidentAngle);
      this.boundary = line(660, 80, 660, 620, 'p2-wave-boundary reflective-boundary');
    } else if (params.behavior === 'refraction') {
      const speedRatio = params.medium2.speed === params.medium1.speed ? 1 : params.medium2.speed === 'slow' ? .68 : 1.28;
      secondaryAngle = addRefraction(this.outgoing, params.incidentAngle, speedRatio);
      this.boundary = line(660, 80, 660, 620, 'p2-wave-boundary refractive-boundary');
    } else {
      const gap = addDiffraction(this.outgoing, params.gapWidth);
      const upper = line(660, 70, 660, 350 - gap / 2, 'p2-wave-boundary barrier-boundary');
      const lower = line(660, 350 + gap / 2, 660, 630, 'p2-wave-boundary barrier-boundary');
      this.boundary = [upper, lower];
    }
    append(this.diagram, this.incomingGroup, ...(Array.isArray(this.boundary) ? this.boundary : [this.boundary]), ...this.outgoing);

    this.rays = svgEl('g', { class: 'p2-wave-rays' });
    if (params.behavior !== 'diffraction') {
      append(this.rays,
        line(210, 515, 660, 350, 'p2-wave-ray incident-ray'),
        line(660, 350, params.behavior === 'reflection' ? 230 : 1120, params.behavior === 'reflection' ? 170 : 350 - Math.tan((90 - secondaryAngle) * Math.PI / 180) * 165, 'p2-wave-ray result-ray')
      );
      this.rays.lastChild.setAttribute('marker-end', 'url(#p2-wave-ray-arrow)');
    }
    this.normal = line(430, 350, 890, 350, 'p2-wave-normal');
    if (!params.showNormal || params.behavior === 'diffraction') this.normal.classList.add('is-hidden');
    append(this.diagram, this.rays, this.normal);

    this.angleGroup = svgEl('g', { class: 'p2-wave-angles' });
    if (params.showAngles && params.behavior !== 'diffraction') {
      const arc1 = svgEl('path', { d: 'M585 350 A75 75 0 0 1 602 307', class: 'p2-angle-arc' });
      append(this.angleGroup, arc1, label(575, 290, `${params.incidentAngle}°`, 'p2-angle-label'));
      const resultText = params.behavior === 'reflection' ? `${params.incidentAngle}°` : `${Math.round(secondaryAngle)}°`;
      append(this.angleGroup, svgEl('path', { d: 'M735 350 A75 75 0 0 0 718 307', class: 'p2-angle-arc' }), label(752, 290, resultText, 'p2-angle-label'));
    }
    this.diagram.appendChild(this.angleGroup);
    append(this.diagram,
      label(180, 82, params.medium1.label, 'p2-medium-label'),
      label(1140, 82, params.behavior === 'reflection' || params.behavior === 'diffraction' ? params.medium1.label : params.medium2.label, 'p2-medium-label')
    );
    this.card.appendChild(this.diagram);

    this.fact = el('aside', 'p2-wave-fact');
    const factValue = params.behavior === 'reflection' ? 'angle i = angle r' : params.behavior === 'refraction' ? `${params.medium1.speed} → ${params.medium2.speed}` : `${params.gapWidth} gap → ${params.gapWidth === 'narrow' ? 'more' : 'less'} spreading`;
    append(this.fact,
      el('small', '', { text: 'Observed relationship' }),
      el('strong', '', { text: factValue }),
      el('span', '', { text: params.behavior === 'diffraction' ? 'Gap width changes the curvature.' : 'The normal is the angle reference.' })
    );
    append(this.root, header, this.card, this.fact);
  }

  buildTimeline(params) {
    const seconds = duration(params, 7);
    this.outgoing.forEach(front => {
      const length = front.getTotalLength();
      gsap.set(front, { strokeDasharray: length, strokeDashoffset: length });
    });
    const boundaries = Array.isArray(this.boundary) ? this.boundary : [this.boundary];
    boundaries.forEach(boundary => {
      const length = boundary.getTotalLength();
      gsap.set(boundary, { strokeDasharray: length, strokeDashoffset: length });
    });
    const tl = gsap.timeline({ paused: true });
    tl.set(this.root, { autoAlpha: 1 }, 0)
      .fromTo(this.root.querySelector('.p2-scene-header'), { y: -22, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .08)
      .fromTo(this.card, { y: 28, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .28)
      .to(boundaries, { strokeDashoffset: 0, duration: .65, stagger: .08 }, .58)
      .fromTo(this.incomingGroup, { x: -260, autoAlpha: .2 }, { x: 0, autoAlpha: 1, duration: 1.45, ease: 'power1.inOut' }, .82)
      .to(this.outgoing, { strokeDashoffset: 0, duration: 1.45, stagger: .075, ease: 'power1.inOut' }, 2.0);
    const incidentRays = this.root.querySelectorAll('.incident-ray');
    const resultRays = this.root.querySelectorAll('.result-ray');
    if (incidentRays.length) tl.fromTo(incidentRays, { strokeDasharray: 620, strokeDashoffset: 620 }, { strokeDashoffset: 0, duration: .85 }, 1.25);
    if (resultRays.length) tl.fromTo(resultRays, { strokeDasharray: 620, strokeDashoffset: 620 }, { strokeDashoffset: 0, duration: .9 }, 2.15);
    if (params.showNormal && params.behavior !== 'diffraction') tl.fromTo(this.normal, { scaleX: 0 }, { scaleX: 1, duration: .5 }, 2.65);
    if (params.showAngles && params.behavior !== 'diffraction') tl.fromTo(this.angleGroup, { scale: .8, autoAlpha: 0, transformOrigin: 'center' }, { scale: 1, autoAlpha: 1, duration: .45 }, 2.85);
    tl.fromTo(this.fact, { x: 30, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: .5 }, 3.25);
    return finishTimeline(tl, this.root, seconds);
  }

  teardown() { this.root?.remove(); }

  static getParamSchema() {
    const medium = {
      type: 'object', required: ['label', 'speed'], additionalProperties: false,
      properties: {
        label: { type: 'string', maxLength: 20, default: 'Medium' },
        speed: { type: 'string', enum: ['fast', 'slow'], default: 'fast' }
      }
    };
    return {
      type: 'object', required: ['behavior', 'medium1', 'medium2'], additionalProperties: false,
      properties: {
        behavior: { type: 'string', enum: ['reflection', 'refraction', 'diffraction'], default: 'reflection' },
        incidentAngle: { type: 'number', minimum: 5, maximum: 85, default: 45 },
        medium1: medium,
        medium2: medium,
        showNormal: { type: 'boolean', default: true },
        showAngles: { type: 'boolean', default: true },
        gapWidth: { type: 'string', enum: ['narrow', 'wide'], default: 'narrow' }
      }
    };
  }
}
