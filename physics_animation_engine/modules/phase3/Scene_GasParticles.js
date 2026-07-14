import { append, clamp, el, finishPhase3, lerp, phase3Root, phase3Timeline, schemas } from './_shared.js';

const SPEED = { low: .7, medium: 1.15, high: 1.8 };
const bounce = value => { const wrapped = ((value % 2) + 2) % 2; return wrapped <= 1 ? wrapped : 2 - wrapped; };

export class Scene_GasParticles {
  setup(container, params) {
    const frame = phase3Root(container, 'Scene_GasParticles', 'Kinetic theory', 'Gas pressure in a container', `${params.temperature} temperature · ${params.containerType} container · change: ${params.changeTo.replaceAll('_', ' ')}`, 'scene-gas-particles');
    this.root = frame.root;
    this.panel = el('section', 'p3-gas-panel');
    this.chamber = el('div', `p3-gas-chamber is-${params.containerType}`);
    this.piston = params.containerType === 'piston' ? el('div', 'p3-piston', { html: '<span></span><strong>piston</strong>' }) : null;
    if (this.piston) this.chamber.appendChild(this.piston);
    this.particles = [];
    for (let index = 0; index < 32; index++) {
      const particle = el('i', 'p3-gas-particle');
      particle.dataset.x = String((index * 37 % 97) / 100); particle.dataset.y = String((index * 61 % 91) / 100);
      particle.dataset.vx = String(.55 + index % 5 * .13); particle.dataset.vy = String(.45 + index % 7 * .09);
      this.particles.push(particle); this.chamber.appendChild(particle);
    }
    this.arrows = [];
    if (params.showPressureArrows) for (let index = 0; index < 6; index++) {
      const arrow = el('span', `p3-pressure-arrow side-${index % 2}`); arrow.style.top = `${16 + Math.floor(index / 2) * 30}%`; this.arrows.push(arrow); this.chamber.appendChild(arrow);
    }
    this.readout = el('aside', 'p3-gas-readout');
    append(this.readout, el('small', '', { text: 'particle model' }), el('strong', '', { text: params.temperature }), el('span', '', { text: 'collision frequency' }), el('b', '', { text: params.changeTo === 'smaller_volume' ? 'increasing as V falls' : 'increasing as T rises' }));
    append(this.panel, this.chamber, this.readout); this.root.appendChild(this.panel);
  }
  update(progress, params) {
    const initial = SPEED[params.temperature], target = params.changeTo === 'higher_temp' ? initial * 1.8 : initial;
    const speed = lerp(initial, target, progress), volume = params.changeTo === 'smaller_volume' ? lerp(1, .68, progress) : 1;
    this.chamber.style.setProperty('--gas-volume', volume);
    this.particles.forEach((particle, index) => {
      const x = bounce(Number(particle.dataset.x) + progress * speed * Number(particle.dataset.vx)) * 92 * volume;
      const y = bounce(Number(particle.dataset.y) + progress * speed * Number(particle.dataset.vy)) * 88;
      particle.style.transform = `translate(${x * 11.4}px, ${y * 4.2}px)`;
    });
    this.arrows.forEach(arrow => arrow.style.setProperty('--pressure-scale', String(lerp(.65, params.changeTo ? 1.45 : 1, progress))));
    this.readout.querySelector('strong').textContent = params.changeTo === 'higher_temp' && progress > .55 ? 'high' : params.temperature;
  }
  buildTimeline(params) {
    const state = { progress: 0 }; this.update(0, params);
    const tl = phase3Timeline(this.root);
    tl.fromTo(this.panel, { y: 25, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .3)
      .fromTo(this.chamber, { scale: .94, autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: .55 }, .55)
      .fromTo(this.particles, { scale: 0, autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: .22, stagger: .02 }, .82)
      .fromTo(this.readout, { x: 28, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: .45 }, 1.05)
      .to(state, { progress: 1, duration: 4.35, ease: 'none', onUpdate: () => this.update(state.progress, params) }, 1.15);
    if (this.piston && params.changeTo === 'smaller_volume') tl.to(this.piston, { x: -270, duration: 3.3, ease: 'power1.inOut' }, 1.65);
    return finishPhase3(tl, this.root, params, 6.5);
  }
  teardown() { this.root?.remove(); }
  static getParamSchema() { return { type: 'object', additionalProperties: false, properties: { containerType: { type: 'string', enum: ['fixed', 'piston'], default: 'fixed' }, temperature: { type: 'string', enum: ['low', 'medium', 'high'], default: 'medium' }, showPressureArrows: schemas.toggle(true), changeTo: { type: 'string', enum: ['higher_temp', 'smaller_volume', 'none'], default: 'higher_temp' } } }; }
}
