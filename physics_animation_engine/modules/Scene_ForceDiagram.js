import { append, color, duration, el, finishTimeline, formatNumber, root } from '../engine/renderer.js';

const angles = { up: -90, down: 90, left: 180, right: 0 };

function objectVisual(object) {
  const node = el('div', `fd-object fd-${object.type || 'block'}`);
  if (object.type === 'car') append(node, el('span', 'fd-wheel wheel-a'), el('span', 'fd-wheel wheel-b'));
  if (object.type === 'rocket') append(node, el('span', 'fd-nose'), el('span', 'fd-fin fin-a'), el('span', 'fd-fin fin-b'));
  append(node, el('strong', '', { text: object.label || 'Object' }));
  if (object.mass !== undefined && object.mass !== null) node.appendChild(el('small', '', { text: `${formatNumber(object.mass)} kg` }));
  return node;
}

export class Scene_ForceDiagram {
  setup(container, params) {
    this.root = root(container, 'Scene_ForceDiagram', 'scene-forcediagram');
    const header = el('div', 'fd-header');
    append(header, el('span', 'scene-kicker', { text: 'Free-body diagram' }), el('h2', '', { text: 'Forces acting on the object' }), el('p', '', { text: 'Arrow length represents relative force magnitude' }));
    this.surface = el('div', `fd-surface surface-${params.surface || 'none'}`);
    this.surface.style.setProperty('--surface-angle', `${params.surfaceAngle || 0}deg`);
    this.object = objectVisual(params.object);
    const diagram = el('div', 'fd-diagram');
    this.vectors = params.forces.map(force => {
      const angle = force.direction === 'angle' ? Number(force.angle || 0) : angles[force.direction] ?? 0;
      const vector = el('div', 'fd-vector');
      vector.style.setProperty('--angle', `${angle}deg`);
      vector.style.setProperty('--counter-angle', `${-angle}deg`);
      vector.style.setProperty('--length', `${Math.min(280, Math.max(28, Number(force.magnitude) * 28))}px`);
      vector.style.setProperty('--vector-color', color(force.color));
      append(vector, el('span', 'fd-shaft'), el('span', 'fd-arrowhead'), el('span', 'fd-vector-label', { text: force.label }));
      return vector;
    });
    append(diagram, this.surface, this.object, this.vectors);
    this.net = el('div', `fd-net ${Number(params.netForceValue) === 0 ? 'balanced' : 'unbalanced'}`);
    append(this.net, el('span', 'fd-net-dot'), el('span', '', { text: Number(params.netForceValue) === 0 ? 'ΣF = 0 N' : `ΣF = ${formatNumber(params.netForceValue)} N` }), el('b', '', { text: Number(params.netForceValue) === 0 ? 'BALANCED' : 'ACCELERATING' }));
    append(this.root, header, diagram, params.showNetForce ? this.net : null);
  }

  buildTimeline(params) {
    const seconds = duration(params, 7);
    const tl = gsap.timeline({ paused: true });
    tl.set(this.root, { autoAlpha: 1 }, 0)
      .fromTo(this.root.querySelector('.fd-header'), { y: -20, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .08)
      .fromTo(this.surface, { scaleX: 0 }, { scaleX: 1, duration: .9, ease: 'power2.inOut' }, .15)
      .fromTo(this.object, { scale: 0, rotation: -7 }, { scale: 1, rotation: 0, duration: .72, ease: 'elastic.out(1,.6)' }, .5)
      .fromTo(this.object.querySelectorAll('strong, small'), { autoAlpha: 0, y: 8 }, { autoAlpha: 1, y: 0, duration: .35, stagger: .12 }, .85)
      .fromTo(this.vectors.map(v => v.querySelector('.fd-shaft')), { scaleX: 0 }, { scaleX: 1, duration: .55, stagger: .36, ease: 'power2.out' }, 1.15)
      .fromTo(this.vectors.map(v => v.querySelector('.fd-arrowhead')), { scale: 0 }, { scale: 1, duration: .25, stagger: .36, ease: 'back.out(2)' }, 1.53)
      .fromTo(this.vectors.map(v => v.querySelector('.fd-vector-label')), { autoAlpha: 0, y: 8 }, { autoAlpha: 1, y: 0, duration: .35, stagger: .36 }, 1.68);
    if (params.showNetForce) tl.fromTo(this.net, { y: 18, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55, ease: 'power2.out' }, 3.1);
    if (params.showAcceleration && Number(params.netForceValue) !== 0) tl.to(this.object, { x: Math.sign(params.netForceValue) * 180, duration: Math.max(1, seconds - 4), ease: 'power1.in' }, 3.6);
    return finishTimeline(tl, this.root, seconds);
  }

  teardown() { this.root?.remove(); }

  static getParamSchema() {
    return {
      type: 'object', required: ['object', 'forces'], additionalProperties: false,
      properties: {
        object: { type: 'object', required: ['type', 'label'], properties: {
          type: { type: 'string', enum: ['block','circle','triangle','car','rocket'], default: 'block' },
          label: { type: 'string', maxLength: 40, default: 'Object' }, mass: { type: 'number', minimum: 0, maximum: 100000, default: 1 }
        }},
        surface: { type: 'string', enum: ['none','table','floor','incline'], default: 'floor' },
        surfaceAngle: { type: 'number', minimum: -60, maximum: 60, default: 0 },
        forces: { type: 'array', minItems: 1, maxItems: 6, default: [], items: { type: 'object', required: ['label','direction','magnitude'], properties: {
          label: { type: 'string', maxLength: 50, default: 'Force' }, direction: { type: 'string', enum: ['up','down','left','right','angle'], default: 'right' },
          angle: { type: 'number', minimum: -360, maximum: 360, default: 0 }, magnitude: { type: 'number', minimum: 1, maximum: 10, default: 5 },
          color: { type: 'string', enum: ['velocity','force','label','energy','orange','yellow','cyan','green'], default: 'force' }
        }}},
        showNetForce: { type: 'boolean', default: true }, netForceValue: { type: 'number', default: 0 }, showAcceleration: { type: 'boolean', default: false }
      }
    };
  }
}
