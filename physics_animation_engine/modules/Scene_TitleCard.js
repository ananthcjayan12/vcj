import { append, duration, el, finishTimeline, root } from '../engine/renderer.js';

export class Scene_TitleCard {
  setup(container, params) {
    this.root = root(container, 'Scene_TitleCard', 'scene-titlecard');
    this.grid = el('div', 'tc-grid-bg');
    this.orbit = el('div', 'tc-orbit', { html: '<i></i><i></i><i></i>' });
    const content = el('div', 'tc-content');
    this.badge = el('span', 'tc-badge', { text: params.badge || 'Physics visualised' });
    this.title = el('h2', 'tc-title');
    [...params.title].forEach(character => this.title.appendChild(el('span', 'tc-char', { text: character === ' ' ? '\u00a0' : character })));
    this.subtitle = el('p', 'tc-subtitle', { text: params.subtitle || '' });
    this.rule = el('span', 'tc-rule');
    append(content, this.badge, this.title, this.rule, this.subtitle);
    append(this.root, this.grid, this.orbit, content);
  }

  buildTimeline(params) {
    const seconds = duration(params, 5.5);
    const tl = gsap.timeline({ paused: true });
    tl.set(this.root, { autoAlpha: 1 }, 0)
      .fromTo(this.grid, { opacity: 0 }, { opacity: 1, duration: 1.1 }, 0)
      .fromTo(this.orbit, { opacity: 0, scale: .7, rotation: -14 }, { opacity: 1, scale: 1, rotation: 0, duration: 1.3, ease: 'power3.out' }, .1)
      .fromTo(this.badge, { y: -35, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .65, ease: 'back.out(1.7)' }, .35)
      .fromTo(this.title.querySelectorAll('.tc-char'), { y: 42, autoAlpha: 0, rotateX: -70 }, { y: 0, autoAlpha: 1, rotateX: 0, duration: .5, stagger: .032, ease: 'power3.out' }, .72)
      .fromTo(this.rule, { scaleX: 0 }, { scaleX: 1, duration: .7, ease: 'power3.inOut' }, 1.45)
      .fromTo(this.subtitle, { y: 24, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .7, ease: 'power2.out' }, 1.62);
    return finishTimeline(tl, this.root, seconds);
  }

  teardown() { this.root?.remove(); }

  static getParamSchema() {
    return {
      type: 'object', required: ['title'], additionalProperties: false,
      properties: {
        title: { type: 'string', maxLength: 60, default: 'Physics, in motion.' },
        subtitle: { type: 'string', maxLength: 100, default: '' },
        badge: { type: 'string', maxLength: 40, default: 'GCSE Physics' }
      }
    };
  }
}
