import { append, duration, el, finishTimeline, root } from '../engine/renderer.js';

const DECAY = {
  alpha: { symbol: 'α', name: 'alpha particle', stopsAt: 'paper', description: '2 protons + 2 neutrons' },
  beta: { symbol: 'β⁻', name: 'beta particle', stopsAt: 'aluminium', description: 'high-speed electron' },
  gamma: { symbol: 'γ', name: 'gamma ray', stopsAt: 'lead', description: 'electromagnetic radiation' }
};

function isotopeCard(nucleus, role) {
  const card = el('div', `p2-isotope-card is-${role}`);
  const notation = el('span', 'p2-isotope-notation');
  append(notation,
    el('sup', '', { text: nucleus.massNumber }),
    el('sub', '', { text: nucleus.atomicNumber }),
    el('strong', '', { text: nucleus.element })
  );
  append(card, el('small', '', { text: role }), notation);
  return card;
}

export class Scene_NuclearDecay {
  setup(container, params) {
    this.root = root(container, 'Scene_NuclearDecay', 'scene-p2 scene-nuclear-decay');
    const decay = DECAY[params.decayType];
    const header = el('header', 'p2-scene-header');
    append(header,
      el('span', 'p2-kicker', { text: 'Radioactive emissions' }),
      el('h2', '', { text: `${decay.name[0].toUpperCase()}${decay.name.slice(1)} decay` }),
      el('p', '', { text: `${params.parentNucleus.element}-${params.parentNucleus.massNumber} transforms and releases ${decay.description}.` })
    );

    this.lab = el('section', 'p2-decay-lab');
    this.source = el('div', 'p2-decay-source');
    this.parent = isotopeCard(params.parentNucleus, 'parent');
    this.daughter = isotopeCard(params.daughterNucleus, 'daughter');
    this.daughter.style.visibility = 'hidden';
    append(this.source, el('span', 'p2-nucleus-glow'), this.parent, this.daughter);

    this.particle = el('div', `p2-decay-particle is-${params.decayType}`);
    append(this.particle,
      el('span', '', { text: decay.symbol }),
      el('small', '', { text: decay.name })
    );
    this.trail = el('span', `p2-decay-trail is-${params.decayType}`);

    this.barrierArea = el('div', 'p2-barrier-area');
    this.barriers = params.barriers.map((material, index) => {
      const barrier = el('div', `p2-radiation-barrier is-${material}`);
      barrier.style.setProperty('--barrier-index', index);
      append(barrier,
        el('span', '', { text: material === 'aluminium' ? 'Al' : material === 'lead' ? 'Pb' : '▤' }),
        el('strong', '', { text: material }),
        el('small', '', { text: material === decay.stopsAt ? `stops ${params.decayType}` : 'penetrated' })
      );
      this.barrierArea.appendChild(barrier);
      return barrier;
    });
    if (!params.showPenetration) this.barrierArea.hidden = true;

    this.verdict = el('aside', 'p2-penetration-verdict');
    append(this.verdict,
      el('span', '', { text: decay.symbol }),
      el('div', '', { html: `<small>penetration result</small><strong>${params.showPenetration ? `Stopped by ${decay.stopsAt}` : 'Emission path shown'}</strong>` })
    );
    append(this.lab, this.source, this.trail, this.particle, this.barrierArea, this.verdict);

    this.equation = el('div', 'p2-decay-equation');
    const parent = `${params.parentNucleus.massNumber} ${params.parentNucleus.element}`;
    const daughter = `${params.daughterNucleus.massNumber} ${params.daughterNucleus.element}`;
    append(this.equation,
      el('span', '', { text: parent }), el('i', '', { text: '→' }),
      el('span', '', { text: daughter }), el('b', '', { text: `+ ${decay.symbol}` })
    );
    append(this.root, header, this.lab, this.equation);
  }

  buildTimeline(params) {
    const seconds = duration(params, 7);
    const decay = DECAY[params.decayType];
    const stoppingIndex = params.showPenetration ? params.barriers.indexOf(decay.stopsAt) : -1;
    const distance = stoppingIndex >= 0 ? 525 + stoppingIndex * 220 : 525 + params.barriers.length * 220 + 180;
    const particleDuration = params.decayType === 'alpha' ? 1.15 : params.decayType === 'beta' ? .9 : .72;
    const tl = gsap.timeline({ paused: true });
    tl.set(this.root, { autoAlpha: 1 }, 0)
      .fromTo(this.root.querySelector('.p2-scene-header'), { y: -22, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .08)
      .fromTo(this.lab, { y: 28, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .28)
      .fromTo(this.parent, { scale: .72, autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: .62, ease: 'back.out(1.7)' }, .52)
      .to(this.source, { x: -8, duration: .06, repeat: 9, yoyo: true, ease: 'none' }, 1.25)
      .fromTo(this.root.querySelector('.p2-nucleus-glow'), { scale: .4, autoAlpha: 0 }, { scale: 1.65, autoAlpha: .85, duration: .22, repeat: 1, yoyo: true }, 1.7)
      .to(this.parent, { scale: .82, autoAlpha: 0, duration: .22 }, 1.78)
      .set(this.daughter, { visibility: 'visible' }, 1.78)
      .fromTo(this.daughter, { scale: .72, autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: .45, ease: 'back.out(1.7)' }, 1.82)
      .fromTo(this.particle, { scale: .2, autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: .24 }, 1.75)
      .fromTo(this.trail, { scaleX: 0, autoAlpha: 0 }, { scaleX: 1, autoAlpha: .75, duration: particleDuration, ease: 'power1.in' }, 1.92)
      .to(this.particle, { x: distance, duration: particleDuration, ease: params.decayType === 'gamma' ? 'none' : 'power1.out' }, 1.92);
    if (params.showPenetration) {
      tl.fromTo(this.barriers, { y: 35, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .42, stagger: .12 }, .88)
        .fromTo(this.verdict, { x: 25, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: .45 }, 3.2);
      const penetrated = this.barriers.slice(0, stoppingIndex < 0 ? this.barriers.length : stoppingIndex);
      if (penetrated.length) tl.to(penetrated, { boxShadow: '0 0 32px rgba(0,245,255,.35)', duration: .15, stagger: .14, repeat: 1, yoyo: true }, 2.18);
      if (stoppingIndex >= 0) tl.to(this.barriers[stoppingIndex], { x: 8, duration: .055, repeat: 7, yoyo: true }, 1.92 + particleDuration);
    } else {
      tl.fromTo(this.verdict, { x: 25, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: .45 }, 3.05);
    }
    tl.fromTo(this.equation, { y: 20, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .5 }, 3.45);
    return finishTimeline(tl, this.root, seconds);
  }

  teardown() { this.root?.remove(); }

  static getParamSchema() {
    const nucleus = {
      type: 'object', required: ['element', 'massNumber', 'atomicNumber'], additionalProperties: false,
      properties: {
        element: { type: 'string', maxLength: 18, default: 'U' },
        massNumber: { type: 'integer', minimum: 1, maximum: 300, default: 238 },
        atomicNumber: { type: 'integer', minimum: 1, maximum: 118, default: 92 }
      }
    };
    return {
      type: 'object', required: ['decayType', 'parentNucleus', 'daughterNucleus'], additionalProperties: false,
      properties: {
        decayType: { type: 'string', enum: ['alpha', 'beta', 'gamma'], default: 'alpha' },
        parentNucleus: nucleus,
        daughterNucleus: nucleus,
        showPenetration: { type: 'boolean', default: true },
        barriers: { type: 'array', minItems: 1, maxItems: 3, default: ['paper', 'aluminium', 'lead'], items: { type: 'string', enum: ['paper', 'aluminium', 'lead'], default: 'paper' } }
      }
    };
  }
}
