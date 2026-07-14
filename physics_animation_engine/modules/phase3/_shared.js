import { append, color, duration, el, finishTimeline, formatNumber, root, svg, svgEl } from '../../engine/renderer.js';

export { append, color, duration, el, finishTimeline, formatNumber, svg, svgEl };

export const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
export const lerp = (from, to, progress) => from + (to - from) * progress;

export function phase3Root(container, sceneName, kicker, title, description, className = '') {
  const sceneRoot = root(container, sceneName, `scene-p3 ${className}`.trim());
  const header = el('header', 'p3-scene-header');
  append(header,
    el('span', 'p3-kicker', { text: kicker }),
    el('h2', '', { text: title }),
    el('p', '', { text: description })
  );
  sceneRoot.appendChild(header);
  return { root: sceneRoot, header };
}

export function phase3Timeline(sceneRoot, seconds = 6) {
  return gsap.timeline({ paused: true })
    .set(sceneRoot, { autoAlpha: 1 }, 0)
    .fromTo(sceneRoot.querySelector('.p3-scene-header'), { y: -22, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55, ease: 'power3.out' }, .08);
}

export function drawPaths(timeline, paths, at = .8, drawDuration = 1.1, stagger = .08) {
  const targets = [...paths].filter(Boolean);
  targets.forEach(path => {
    const length = path.getTotalLength();
    gsap.set(path, { strokeDasharray: length, strokeDashoffset: length });
  });
  if (targets.length) timeline.to(targets, { strokeDashoffset: 0, duration: drawDuration, stagger, ease: 'power2.inOut' }, at);
  return timeline;
}

export function addArrowMarker(svgNode, id, fill = '#ffd23f') {
  let defs = svgNode.querySelector('defs');
  if (!defs) {
    defs = svgEl('defs');
    svgNode.prepend(defs);
  }
  const marker = svgEl('marker', { id, markerWidth: 10, markerHeight: 10, refX: 8, refY: 5, orient: 'auto', markerUnits: 'strokeWidth' });
  marker.appendChild(svgEl('path', { d: 'M0 0 L10 5 L0 10 Z', fill }));
  defs.appendChild(marker);
  return marker;
}

export function pointLabel(x, y, text, className = 'p3-svg-label') {
  const node = svgEl('text', { x, y, class: className, 'text-anchor': 'middle' });
  node.textContent = text;
  return node;
}

export function finishPhase3(timeline, sceneRoot, params, fallback = 6) {
  return finishTimeline(timeline, sceneRoot, duration(params, fallback));
}

export const schemas = {
  shortText: (defaultValue = '', maxLength = 80) => ({ type: 'string', maxLength, default: defaultValue }),
  positive: (defaultValue = 1, maximum = 10000) => ({ type: 'number', minimum: 0.01, maximum, default: defaultValue }),
  toggle: (defaultValue = true) => ({ type: 'boolean', default: defaultValue }),
  color: { type: 'string', enum: ['velocity', 'force', 'label', 'energy'], default: 'velocity' }
};
