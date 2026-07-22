import assert from 'node:assert/strict';
import {ActorBox, Bounds, SafeArea, overlapSize, solveChoreography, translatedBounds} from '../src/choreography-core';

const safe: SafeArea = {left: 100, right: 1820, top: 100, bottom: 980};

function box(left: number, top: number, width: number, height: number): Bounds {
  return {left, top, right: left + width, bottom: top + height, width, height};
}

function corrected(actor: ActorBox, solution: ReturnType<typeof solveChoreography>) {
  const correction = solution.corrections.find(item => item.id === actor.id)!;
  return translatedBounds(actor.bounds, correction.dx, correction.dy, correction.scale);
}

{
  const diagram: ActorBox = {
    id: 'diagram', bounds: box(330, 260, 820, 560), priority: 880, gap: 32,
    maxShift: 120, minScale: 0.94, canScale: true, canFade: false,
  };
  const card: ActorBox = {
    id: 'card', bounds: box(1130, 350, 500, 140), priority: 640, gap: 28,
    maxShift: 260, minScale: 0.94, canScale: true, canFade: true,
  };
  const solution = solveChoreography([diagram, card], safe);
  const overlap = overlapSize(corrected(diagram, solution), corrected(card, solution));
  assert.ok(overlap.x <= 0 || overlap.y <= 0, 'known 20px diagram/card overlap should be removed');
  const cardCorrection = solution.corrections.find(item => item.id === 'card')!;
  assert.notEqual(cardCorrection.reason, 'focus-fade', 'ordinary overlap should be solved by restaging, not hiding');
  assert.equal(solution.unresolved.length, 0);
}

{
  const first: ActorBox = {
    id: 'first-label', bounds: box(820, 700, 150, 40), priority: 320, gap: 10,
    maxShift: 180, minScale: 1, canScale: false, canFade: true, groupId: 'diagram',
  };
  const second: ActorBox = {
    id: 'second-label', bounds: box(900, 700, 170, 40), priority: 320, gap: 10,
    maxShift: 180, minScale: 1, canScale: false, canFade: true, groupId: 'diagram',
  };
  const parent: ActorBox = {
    id: 'diagram', bounds: box(300, 220, 1000, 650), priority: 880, gap: 32,
    fixed: true, maxShift: 0, minScale: 1, canScale: false, canFade: false,
  };
  const solution = solveChoreography([parent, first, second], safe);
  const overlap = overlapSize(corrected(first, solution), corrected(second, solution));
  assert.ok(overlap.x <= 0 || overlap.y <= 0, 'labels inside one diagram should orbit away from each other');
  assert.equal(solution.unresolved.length, 0);
}

{
  const title: ActorBox = {
    id: 'title', bounds: box(210, 100, 1500, 120), priority: 1000, gap: 32,
    fixed: true, maxShift: 0, minScale: 1, canScale: false, canFade: false,
  };
  const decorative: ActorBox = {
    id: 'decorative', bounds: box(200, 40, 1520, 900), priority: 100, gap: 32,
    maxShift: 10, minScale: 0.98, canScale: false, canFade: true,
  };
  const solution = solveChoreography([title, decorative], safe);
  const correction = solution.corrections.find(item => item.id === 'decorative')!;
  assert.equal(correction.opacity, 0, 'an impossible low-priority collision should leave clean focus instead of failing');
  assert.equal(solution.unresolved.length, 0);
}

{
  const actor: ActorBox = {
    id: 'edge-card', bounds: box(1760, 300, 200, 160), priority: 640, gap: 28,
    maxShift: 260, minScale: 0.94, canScale: true, canFade: true,
  };
  const solution = solveChoreography([actor], safe);
  const bounds = corrected(actor, solution);
  assert.ok(bounds.right <= safe.right + 0.5, 'safe-area overflow should be corrected before rendering');
  assert.equal(solution.unresolved.length, 0);
}

console.log('kinetic choreography tests passed');
