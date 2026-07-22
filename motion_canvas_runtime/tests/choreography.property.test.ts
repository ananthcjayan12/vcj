import assert from 'node:assert/strict';
import {ActorBox, overlapSize, solveChoreography, translatedBounds} from '../src/choreography-core';

const safe = {left: 100, right: 1820, top: 100, bottom: 980};
let seed = 123456789;
const random = () => {
  seed = (1664525 * seed + 1013904223) >>> 0;
  return seed / 0x100000000;
};

for (let scenario = 0; scenario < 400; scenario += 1) {
  const actors: ActorBox[] = [];
  const count = 2 + Math.floor(random() * 5);
  for (let index = 0; index < count; index += 1) {
    const width = 160 + random() * 620;
    const height = 80 + random() * 360;
    const left = 40 + random() * (1840 - width);
    const top = 40 + random() * (1000 - height);
    actors.push({
      id: `s${scenario}-a${index}`,
      bounds: {left, right: left + width, top, bottom: top + height, width, height},
      priority: index === 0 ? 900 : 100 + Math.floor(random() * 700),
      gap: 20 + Math.floor(random() * 16),
      fixed: index === 0 && random() < .2,
      maxShift: 160 + random() * 220,
      minScale: .9,
      canScale: true,
      canFade: index !== 0,
    });
  }
  const solution = solveChoreography(actors, safe);
  const visible = actors.map(actor => {
    const correction = solution.corrections.find(item => item.id === actor.id)!;
    return {actor, correction, bounds: translatedBounds(actor.bounds, correction.dx, correction.dy, correction.scale)};
  }).filter(item => item.correction.opacity > .2);
  for (const item of visible) {
    if (!item.actor.fixed) {
      assert.ok(item.bounds.left >= safe.left - 1 && item.bounds.right <= safe.right + 1 && item.bounds.top >= safe.top - 1 && item.bounds.bottom <= safe.bottom + 1, `scenario ${scenario} left actor outside safe area`);
    }
  }
  for (let index = 0; index < visible.length; index += 1) {
    for (let other = index + 1; other < visible.length; other += 1) {
      const overlap = overlapSize(visible[index].bounds, visible[other].bounds);
      assert.ok(overlap.x <= .5 || overlap.y <= .5, `scenario ${scenario} retained overlap`);
    }
  }
}
console.log('kinetic choreography property tests passed');
