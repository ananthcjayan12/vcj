const SVG_NS = 'http://www.w3.org/2000/svg';

export const colors = {
  velocity: '#00f5ff',
  cyan: '#00f5ff',
  force: '#ff5a36',
  orange: '#ff5a36',
  label: '#ffd23f',
  yellow: '#ffd23f',
  energy: '#39ff14',
  green: '#39ff14',
  neutral: '#f5f4ef'
};

export function el(tag, className, attributes = {}) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  Object.entries(attributes).forEach(([key, value]) => {
    if (key === 'text') node.textContent = value;
    else if (key === 'html') node.innerHTML = value;
    else node.setAttribute(key, value);
  });
  return node;
}

export function svg(className, viewBox = '0 0 100 100') {
  const node = document.createElementNS(SVG_NS, 'svg');
  if (className) node.setAttribute('class', className);
  node.setAttribute('viewBox', viewBox);
  node.setAttribute('preserveAspectRatio', 'xMidYMid meet');
  return node;
}

export function svgEl(tag, attributes = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, value));
  return node;
}

export function color(name = 'neutral') {
  return colors[name] || name || colors.neutral;
}

export function root(container, sceneName, className) {
  const node = el('section', `scene-root ${className}`);
  node.dataset.scene = sceneName;
  const watermark = el('span', 'scene-watermark', { text: sceneName.replace('Scene_', '').replace(/([a-z])([A-Z])/g, '$1 / $2') });
  node.appendChild(watermark);
  container.appendChild(node);
  return node;
}

export function append(parent, ...children) {
  children.flat().filter(Boolean).forEach(child => parent.appendChild(child));
  return parent;
}

export function duration(params, fallback = 6) {
  return Math.max(2, Number(params.duration) || fallback);
}

export function finishTimeline(tl, sceneRoot, seconds, fade = 0.45) {
  const fadeAt = Math.max(0, seconds - fade);
  tl.to(sceneRoot, { autoAlpha: 0, duration: fade, ease: 'power2.in' }, fadeAt);
  if (tl.duration() < seconds) tl.to({}, { duration: seconds - tl.duration() });
  return tl;
}

export function escapeText(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' }[char]));
}

export function formatNumber(value) {
  return Number.isInteger(Number(value)) ? String(value) : Number(value).toFixed(1);
}
