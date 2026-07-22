import assert from 'node:assert/strict';
import {ActorBox, Bounds, overlapSize, solveChoreography, translatedBounds} from '../src/choreography-core';

const safe = {left: 100, right: 1820, top: 100, bottom: 980};
const canvas = (left: number, right: number, top: number, bottom: number): Bounds => ({
  left: left + 960,
  right: right + 960,
  top: top + 540,
  bottom: bottom + 540,
  width: right - left,
  height: bottom - top,
});

function verify(name: string, diagramBounds: Bounds, cardBounds: Bounds, cardWidth: number) {
  const diagram: ActorBox = {id: `${name}-diagram`, bounds: diagramBounds, priority: 880, gap: 32, maxShift: 120, minScale: .94, canScale: true, canFade: false};
  const card: ActorBox = {id: `${name}-card`, bounds: cardBounds, priority: 640, gap: 28, maxShift: 260, minScale: .94, canScale: true, canFade: true};
  const solution = solveChoreography([diagram, card], safe);
  const diagramCorrection = solution.corrections.find(item => item.id === diagram.id)!;
  const cardCorrection = solution.corrections.find(item => item.id === card.id)!;
  const first = translatedBounds(diagram.bounds, diagramCorrection.dx, diagramCorrection.dy, diagramCorrection.scale);
  const second = translatedBounds(card.bounds, cardCorrection.dx, cardCorrection.dy, cardCorrection.scale);
  const overlap = overlapSize(first, second);
  assert.ok(overlap.x <= 0 || overlap.y <= 0, `${name} should be restaged without overlap`);
  assert.notEqual(cardCorrection.reason, 'focus-fade', `${name} should keep its ${cardWidth}px card visible`);
  assert.equal(solution.unresolved.length, 0, `${name} should finish cleanly`);
  console.log(name, cardCorrection);
}

verify('reel_009', canvas(-630, 190, -240, 320), canvas(170, 670, -190, -50), 500);
verify('reel_017', canvas(-820, 100, -240, 320), canvas(60, 780, -170, 90), 720);
