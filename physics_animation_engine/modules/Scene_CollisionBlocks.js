import { append, color, duration, el, finishTimeline, formatNumber, root } from '../engine/renderer.js';

const EPSILON = 0.0001;

function solveCollision(block1, block2, type) {
  const m1 = Math.max(EPSILON, Number(block1.mass));
  const m2 = Math.max(EPSILON, Number(block2.mass));
  const u1 = Number(block1.velocity);
  const u2 = Number(block2.velocity);
  const initialMomentum = m1 * u1 + m2 * u2;

  if (type === 'inelastic') {
    const commonVelocity = initialMomentum / (m1 + m2);
    return { u1, u2, v1: commonVelocity, v2: commonVelocity, initialMomentum, finalMomentum: initialMomentum };
  }

  if (type === 'explosion') {
    const centreVelocity = initialMomentum / (m1 + m2);
    const separationSpeed = Math.max(6, Math.abs(u1 - u2));
    const v1 = centreVelocity - (m2 / (m1 + m2)) * separationSpeed;
    const v2 = centreVelocity + (m1 / (m1 + m2)) * separationSpeed;
    return { u1, u2, v1, v2, initialMomentum, finalMomentum: m1 * v1 + m2 * v2 };
  }

  const v1 = ((m1 - m2) * u1 + 2 * m2 * u2) / (m1 + m2);
  const v2 = (2 * m1 * u1 + (m2 - m1) * u2) / (m1 + m2);
  return { u1, u2, v1, v2, initialMomentum, finalMomentum: m1 * v1 + m2 * v2 };
}

function makeBlock(params, index) {
  const block = el('div', `p2-collision-block block-${index}`);
  block.style.setProperty('--block-color', color(params.color));
  block.style.setProperty('--block-size', `${Math.min(250, 150 + Math.sqrt(params.mass) * 28)}px`);
  const identity = el('span', 'p2-block-identity');
  append(identity, el('strong', '', { text: params.label }), el('small', '', { text: `${formatNumber(params.mass)} kg` }));
  const velocity = el('span', 'p2-velocity-tag');
  append(velocity, el('i', '', { text: '→' }), el('b', '', { text: `${formatNumber(params.velocity)} m/s` }));
  append(block, identity, velocity);
  return { node: block, velocity, velocityValue: velocity.querySelector('b'), velocityArrow: velocity.querySelector('i') };
}

function momentumRow(label, before, after, maxMagnitude, accent) {
  const row = el('div', 'p2-momentum-row');
  const makeMeter = (value, state) => {
    const cell = el('div', `p2-momentum-meter ${value < 0 ? 'is-negative' : ''}`);
    const rail = el('span');
    const fill = el('i');
    fill.style.setProperty('--meter-color', accent);
    fill.style.setProperty('--meter-width', `${Math.max(4, Math.abs(value) / maxMagnitude * 100)}%`);
    append(rail, fill);
    append(cell, el('small', '', { text: state }), rail, el('b', '', { text: `${formatNumber(value)} kg·m/s` }));
    return cell;
  };
  append(row, el('strong', '', { text: label }), makeMeter(before, 'before'), makeMeter(after, 'after'));
  return row;
}

export class Scene_CollisionBlocks {
  setup(container, params) {
    this.root = root(container, 'Scene_CollisionBlocks', 'scene-p2 scene-collision-blocks');
    this.solution = solveCollision(params.block1, params.block2, params.collisionType);

    const header = el('header', 'p2-scene-header');
    append(header,
      el('span', 'p2-kicker', { text: 'Momentum laboratory' }),
      el('h2', '', { text: `${params.collisionType[0].toUpperCase()}${params.collisionType.slice(1)} collision` }),
      el('p', '', { text: 'The scene engine calculates the outcome from mass and velocity.' })
    );

    this.track = el('div', `p2-collision-track is-${params.collisionType}`);
    this.block1 = makeBlock(params.block1, 1);
    this.block2 = makeBlock(params.block2, 2);
    if (!params.showVelocityLabels) {
      this.block1.velocity.hidden = true;
      this.block2.velocity.hidden = true;
    }
    this.flash = el('span', 'p2-impact-flash');
    this.impactLabel = el('span', 'p2-impact-label', { text: params.collisionType === 'explosion' ? 'energy released' : 'impact' });
    append(this.track, el('span', 'p2-track-line'), this.block1.node, this.block2.node, this.flash, this.impactLabel);

    this.momentum = null;
    if (params.showMomentumBars) {
      this.momentum = el('section', 'p2-momentum-panel');
      const values = [
        params.block1.mass * this.solution.u1,
        params.block2.mass * this.solution.u2,
        params.block1.mass * this.solution.v1,
        params.block2.mass * this.solution.v2
      ];
      const maxMagnitude = Math.max(1, ...values.map(Math.abs));
      const heading = el('div', 'p2-momentum-heading');
      append(heading,
        el('span', '', { text: 'Object momentum' }),
        el('b', '', { text: `Σp ${formatNumber(this.solution.initialMomentum)} → ${formatNumber(this.solution.finalMomentum)} kg·m/s` })
      );
      append(this.momentum,
        heading,
        momentumRow(params.block1.label, values[0], values[2], maxMagnitude, color(params.block1.color)),
        momentumRow(params.block2.label, values[1], values[3], maxMagnitude, color(params.block2.color))
      );
    }

    this.resultBadge = el('div', 'p2-result-badge');
    append(this.resultBadge,
      el('small', '', { text: 'conservation check' }),
      el('strong', '', { text: `Δp = ${formatNumber(this.solution.finalMomentum - this.solution.initialMomentum)} kg·m/s` }),
      el('span', '', { text: 'Momentum conserved' })
    );
    append(this.root, header, this.track, this.momentum, this.resultBadge);
  }

  buildTimeline(params) {
    const seconds = duration(params, 7.5);
    const explosion = params.collisionType === 'explosion';
    const inelastic = params.collisionType === 'inelastic';
    const impactAt = explosion ? 1.55 : 2.4;
    const maxSpeed = Math.max(1, Math.abs(this.solution.v1), Math.abs(this.solution.v2));
    const post1 = this.solution.v1 / maxSpeed * 285;
    const post2 = this.solution.v2 / maxSpeed * 285;

    gsap.set(this.block1.node, { x: explosion ? 430 : 0 });
    gsap.set(this.block2.node, { x: explosion ? -230 : 0 });

    const tl = gsap.timeline({ paused: true });
    tl.set(this.root, { autoAlpha: 1 }, 0)
      .fromTo(this.root.querySelector('.p2-scene-header'), { y: -24, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55, ease: 'power3.out' }, .08)
      .fromTo(this.track, { scaleX: .84, autoAlpha: 0 }, { scaleX: 1, autoAlpha: 1, duration: .65, ease: 'power3.out' }, .18)
      .fromTo([this.block1.node, this.block2.node], { y: -45, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55, stagger: .12, ease: 'back.out(1.8)' }, .42);

    if (!explosion) {
      tl.to(this.block1.node, { x: 650, duration: 1.45, ease: 'power2.in' }, .85)
        .to(this.block2.node, { x: Math.max(-80, this.solution.u2 * 8), duration: 1.45, ease: 'none' }, .85);
    } else {
      tl.to([this.block1.node, this.block2.node], { x: index => index ? -230 : 430, duration: .55, ease: 'sine.inOut' }, .82);
    }

    tl.fromTo(this.flash, { scale: .2, autoAlpha: 0 }, { scale: 2.2, autoAlpha: 1, duration: .14, repeat: 1, yoyo: true, ease: 'power2.out' }, impactAt)
      .fromTo(this.impactLabel, { y: 12, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .28, repeat: 1, yoyo: true, repeatDelay: .35 }, impactAt)
      .add(() => {
        [[this.block1, this.solution.v1], [this.block2, this.solution.v2]].forEach(([block, value]) => {
          block.velocityValue.textContent = `${formatNumber(value)} m/s`;
          block.velocityArrow.textContent = value < 0 ? '←' : '→';
        });
      }, impactAt + .2)
      .to(this.block1.node, { x: inelastic ? 650 + post1 * .45 : 650 + post1, duration: 1.45, ease: 'power2.out' }, impactAt + .22)
      .to(this.block2.node, { x: inelastic ? post2 * .45 : post2, duration: 1.45, ease: 'power2.out' }, impactAt + .22);

    if (this.momentum) {
      tl.fromTo(this.momentum, { y: 30, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .5 }, impactAt + .75)
        .fromTo(this.momentum.querySelectorAll('.p2-momentum-meter i'), { scaleX: 0 }, { scaleX: 1, duration: .65, stagger: .08, ease: 'power2.out' }, impactAt + 1.05);
    }
    tl.fromTo(this.resultBadge, { x: 30, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: .5 }, impactAt + 1.55);
    return finishTimeline(tl, this.root, seconds);
  }

  teardown() { this.root?.remove(); }

  static getParamSchema() {
    const block = {
      type: 'object', required: ['mass', 'velocity', 'label'], additionalProperties: false,
      properties: {
        mass: { type: 'number', minimum: .1, maximum: 100, default: 1 },
        velocity: { type: 'number', minimum: -30, maximum: 30, default: 0 },
        label: { type: 'string', maxLength: 20, default: 'm' },
        color: { type: 'string', enum: ['velocity', 'force', 'label', 'energy'], default: 'velocity' }
      }
    };
    return {
      type: 'object', required: ['block1', 'block2', 'collisionType'], additionalProperties: false,
      properties: {
        block1: block,
        block2: block,
        collisionType: { type: 'string', enum: ['elastic', 'inelastic', 'explosion'], default: 'elastic' },
        showMomentumBars: { type: 'boolean', default: true },
        showVelocityLabels: { type: 'boolean', default: true }
      }
    };
  }
}
