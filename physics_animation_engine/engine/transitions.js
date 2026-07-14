export function revealScene(timeline, sceneRoot, at = 0) {
  timeline.set(sceneRoot, { autoAlpha: 1 }, at);
  return timeline;
}

export function crossfade(target, duration = 0.45) {
  return gsap.timeline({ paused: true }).to(target, { autoAlpha: 0, duration, ease: 'power2.inOut' });
}

export function slide(target, direction = 1, duration = 0.55) {
  return gsap.timeline({ paused: true }).fromTo(target, { x: direction * 80, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration, ease: 'power3.out' });
}
