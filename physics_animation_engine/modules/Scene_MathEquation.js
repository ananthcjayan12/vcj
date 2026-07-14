import { append, duration, el, finishTimeline, root } from '../engine/renderer.js';
import { cueTimes } from './phase3/_shared.js';

function renderMath(target, expression) {
  if (window.katex) {
    try { window.katex.render(expression, target, { throwOnError: false, displayMode: true }); return; } catch (_) {}
  }
  target.textContent = expression;
}

export class Scene_MathEquation {
  setup(container, params) {
    this.root = root(container, 'Scene_MathEquation', 'scene-mathequation');
    this.grid = el('div', 'me-grid');
    const content = el('div', 'me-content');
    const kicker = el('span', 'me-kicker', { text: 'The physics in one line' });
    this.equation = el('div', 'me-equation');
    renderMath(this.equation, params.equation);
    this.highlight = el('div', 'me-highlight');
    if (params.highlight) renderMath(this.highlight, params.highlight);
    this.caption = el('p', 'me-caption', { text: params.caption || '' });
    this.rule = el('span', 'me-rule');
    append(content, kicker, this.equation, params.highlight ? this.highlight : null, this.rule, this.caption);
    append(this.root, this.grid, content);
  }

  buildTimeline(params) {
    const seconds = duration(params, 5.5);
    const cues = cueTimes(params, params.highlight ? 4 : 3);
    const tl = gsap.timeline({ paused: true });
    tl.set(this.root, { autoAlpha: 1 }, 0)
      .fromTo(this.equation, { y: 28, autoAlpha: 0, scale: .94 }, { y: 0, autoAlpha: 1, scale: 1, duration: .85, ease: 'power3.out' }, cues[0]);
    if (params.highlight) {
      tl.fromTo(this.highlight, { autoAlpha: 0, scale: .75 }, { autoAlpha: 1, scale: 1, duration: .55, ease: 'back.out(1.6)' }, cues[1])
        .to(this.highlight, { boxShadow: '0 0 55px rgba(255,210,63,.2)', duration: .7, yoyo: true, repeat: 1, ease: 'power2.inOut' }, cues[1] + .45);
    }
    const ruleCue = params.highlight ? cues[2] : cues[1];
    const captionCue = params.highlight ? cues[3] : cues[2];
    tl.fromTo(this.rule, { scaleX: 0 }, { scaleX: 1, duration: .55, ease: 'power2.inOut' }, ruleCue)
      .fromTo(this.caption, { y: 18, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .65, ease: 'power2.out' }, captionCue);
    return finishTimeline(tl, this.root, seconds);
  }

  teardown() { this.root?.remove(); }

  static getParamSchema() {
    return {
      type: 'object', required: ['equation'], additionalProperties: false,
      properties: {
        equation: { type: 'string', maxLength: 180, default: '\\sum F = ma' },
        highlight: { type: 'string', maxLength: 100, default: '' },
        caption: { type: 'string', maxLength: 150, default: '' }
      }
    };
  }
}
