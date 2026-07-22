export interface Bounds {
  left: number;
  right: number;
  top: number;
  bottom: number;
  width: number;
  height: number;
}

export interface SafeArea {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

export interface ActorBox {
  id: string;
  bounds: Bounds;
  priority: number;
  gap: number;
  fixed?: boolean;
  maxShift?: number;
  minScale?: number;
  canScale?: boolean;
  canFade?: boolean;
  groupId?: string;
}

export interface ActorCorrection {
  id: string;
  dx: number;
  dy: number;
  scale: number;
  opacity: number;
  reason: 'none' | 'safe-area' | 'nudge' | 'scale' | 'focus-fade';
}

export interface ChoreographySolution {
  corrections: ActorCorrection[];
  unresolved: Array<{first: string; second?: string; amount: number}>;
}

interface MutableState extends ActorCorrection {
  actor: ActorBox;
}

const EPSILON = 0.5;
const DEFAULT_MAX_SHIFT = 240;

export function translatedBounds(bounds: Bounds, dx: number, dy: number, scale = 1): Bounds {
  const cx = (bounds.left + bounds.right) / 2 + dx;
  const cy = (bounds.top + bounds.bottom) / 2 + dy;
  const width = bounds.width * scale;
  const height = bounds.height * scale;
  return {
    left: cx - width / 2,
    right: cx + width / 2,
    top: cy - height / 2,
    bottom: cy + height / 2,
    width,
    height,
  };
}

export function overlapSize(first: Bounds, second: Bounds) {
  return {
    x: Math.min(first.right, second.right) - Math.max(first.left, second.left),
    y: Math.min(first.bottom, second.bottom) - Math.max(first.top, second.top),
  };
}

function pairIgnored(first: ActorBox, second: ActorBox): boolean {
  return Boolean(
    first.groupId && second.id === first.groupId ||
    second.groupId && first.id === second.groupId,
  );
}

function conflictAmount(first: Bounds, second: Bounds, gap: number): number {
  const overlap = overlapSize(first, second);
  if (overlap.x > EPSILON && overlap.y > EPSILON) {
    return Math.max(overlap.x, overlap.y) + Math.sqrt(overlap.x * overlap.y);
  }
  if (overlap.x > EPSILON) {
    const verticalGap = first.bottom <= second.top
      ? second.top - first.bottom
      : second.bottom <= first.top
        ? first.top - second.bottom
        : 0;
    return Math.max(0, gap - verticalGap);
  }
  if (overlap.y > EPSILON) {
    const horizontalGap = first.right <= second.left
      ? second.left - first.right
      : second.right <= first.left
        ? first.left - second.right
        : 0;
    return Math.max(0, gap - horizontalGap);
  }
  return 0;
}

function overflowAmount(bounds: Bounds, safe: SafeArea): number {
  return Math.max(0, safe.left - bounds.left) +
    Math.max(0, bounds.right - safe.right) +
    Math.max(0, safe.top - bounds.top) +
    Math.max(0, bounds.bottom - safe.bottom);
}

function clampToSafe(bounds: Bounds, safe: SafeArea): {dx: number; dy: number} {
  let dx = 0;
  let dy = 0;
  if (bounds.left < safe.left) dx += safe.left - bounds.left;
  if (bounds.right + dx > safe.right) dx += safe.right - (bounds.right + dx);
  if (bounds.top < safe.top) dy += safe.top - bounds.top;
  if (bounds.bottom + dy > safe.bottom) dy += safe.bottom - (bounds.bottom + dy);
  return {dx, dy};
}

function boundsFor(state: MutableState): Bounds {
  return translatedBounds(state.actor.bounds, state.dx, state.dy, state.scale);
}

function globalScore(states: MutableState[], safe: SafeArea): number {
  let score = 0;
  for (const state of states) {
    if (state.opacity <= 0.2) continue;
    const bounds = boundsFor(state);
    score += overflowAmount(bounds, safe) * 500_000;
    score += Math.hypot(state.dx, state.dy) * Math.max(1, state.actor.priority / 90);
    score += (1 - state.scale) * 40_000 * Math.max(1, state.actor.priority / 300);
  }
  for (let index = 0; index < states.length; index += 1) {
    const first = states[index];
    if (first.opacity <= 0.2) continue;
    for (let otherIndex = index + 1; otherIndex < states.length; otherIndex += 1) {
      const second = states[otherIndex];
      if (second.opacity <= 0.2 || pairIgnored(first.actor, second.actor)) continue;
      const amount = conflictAmount(
        boundsFor(first),
        boundsFor(second),
        Math.max(first.actor.gap, second.actor.gap),
      );
      if (amount > 0) score += amount * amount * 250_000;
    }
  }
  return score;
}

function chooseMover(first: MutableState, second: MutableState): MutableState | null {
  if (first.actor.fixed && second.actor.fixed) return null;
  if (first.actor.fixed) return second;
  if (second.actor.fixed) return first;
  if (first.actor.priority !== second.actor.priority) {
    return first.actor.priority < second.actor.priority ? first : second;
  }
  const firstCapacity = first.actor.maxShift ?? DEFAULT_MAX_SHIFT;
  const secondCapacity = second.actor.maxShift ?? DEFAULT_MAX_SHIFT;
  if (firstCapacity !== secondCapacity) return firstCapacity > secondCapacity ? first : second;
  return first.actor.id.localeCompare(second.actor.id) > 0 ? first : second;
}

function candidateOffsets(mover: Bounds, obstacle: Bounds, gap: number): Array<{dx: number; dy: number}> {
  const moveLeft = obstacle.left - gap - mover.right;
  const moveRight = obstacle.right + gap - mover.left;
  const moveUp = obstacle.top - gap - mover.bottom;
  const moveDown = obstacle.bottom + gap - mover.top;
  const horizontal = Math.abs(moveLeft) <= Math.abs(moveRight) ? moveLeft : moveRight;
  const vertical = Math.abs(moveUp) <= Math.abs(moveDown) ? moveUp : moveDown;
  return [
    {dx: horizontal, dy: 0},
    {dx: 0, dy: vertical},
    {dx: horizontal, dy: vertical * 0.35},
    {dx: horizontal * 0.35, dy: vertical},
    {dx: moveLeft, dy: 0},
    {dx: moveRight, dy: 0},
    {dx: 0, dy: moveUp},
    {dx: 0, dy: moveDown},
  ];
}

function quantize(value: number): number {
  return Math.round(value / 2) * 2;
}

function setCandidate(
  state: MutableState,
  dx: number,
  dy: number,
  safe: SafeArea,
): boolean {
  const maxShift = state.actor.maxShift ?? DEFAULT_MAX_SHIFT;
  let nextDx = state.dx + dx;
  let nextDy = state.dy + dy;
  const length = Math.hypot(nextDx, nextDy);
  if (length > maxShift && length > 0) {
    const factor = maxShift / length;
    nextDx *= factor;
    nextDy *= factor;
  }
  const candidateBounds = translatedBounds(state.actor.bounds, nextDx, nextDy, state.scale);
  const safeCorrection = clampToSafe(candidateBounds, safe);
  nextDx += safeCorrection.dx;
  nextDy += safeCorrection.dy;
  if (Math.hypot(nextDx, nextDy) > maxShift + 0.5) return false;
  state.dx = quantize(nextDx);
  state.dy = quantize(nextDy);
  return true;
}

function worstConflict(states: MutableState[]) {
  let worst: {first: MutableState; second: MutableState; amount: number} | null = null;
  for (let index = 0; index < states.length; index += 1) {
    const first = states[index];
    if (first.opacity <= 0.2) continue;
    for (let otherIndex = index + 1; otherIndex < states.length; otherIndex += 1) {
      const second = states[otherIndex];
      if (second.opacity <= 0.2 || pairIgnored(first.actor, second.actor)) continue;
      const amount = conflictAmount(
        boundsFor(first),
        boundsFor(second),
        Math.max(first.actor.gap, second.actor.gap),
      );
      if (amount > EPSILON && (!worst || amount > worst.amount)) {
        worst = {first, second, amount};
      }
    }
  }
  return worst;
}


function forceResolve(states: MutableState[], safe: SafeArea) {
  for (let iteration = 0; iteration < 12; iteration += 1) {
    const conflict = worstConflict(states);
    if (!conflict) break;
    const mover = chooseMover(conflict.first, conflict.second);
    if (!mover) break;
    const obstacle = mover === conflict.first ? conflict.second : conflict.first;
    const original = {...mover};
    let best = {...original};
    let bestScore = globalScore(states, safe);
    for (const candidate of candidateOffsets(
      boundsFor(mover),
      boundsFor(obstacle),
      Math.max(mover.actor.gap, obstacle.actor.gap),
    )) {
      Object.assign(mover, original);
      const previousMax = mover.actor.maxShift;
      mover.actor = {...mover.actor, maxShift: Math.max(previousMax ?? 0, 520)};
      setCandidate(mover, candidate.dx, candidate.dy, safe);
      const score = globalScore(states, safe);
      if (score + 1 < bestScore) {
        best = {...mover, actor: original.actor};
        bestScore = score;
      }
      mover.actor = original.actor;
    }
    Object.assign(mover, best);
    mover.actor = original.actor;
    if (bestScore + 1 < globalScore(states.map(state => state === mover ? original : state), safe)) {
      if (mover.reason === 'none') mover.reason = 'nudge';
      continue;
    }
    Object.assign(mover, original);
    if (!mover.actor.fixed && mover.scale > 0.86) {
      mover.scale = Math.max(0.86, mover.scale - 0.06);
      mover.reason = 'scale';
      continue;
    }
    if (mover.actor.priority < 950) {
      mover.opacity = 0;
      mover.reason = 'focus-fade';
      continue;
    }
    const alternate = mover === conflict.first ? conflict.second : conflict.first;
    if (alternate.actor.priority < 950) {
      alternate.opacity = 0;
      alternate.reason = 'focus-fade';
      continue;
    }
    break;
  }

  for (let iteration = 0; iteration < states.length * 2; iteration += 1) {
    const conflict = worstConflict(states);
    if (!conflict) break;
    const candidates = [conflict.first, conflict.second]
      .filter(state => state.actor.priority < 950)
      .sort((first, second) => first.actor.priority - second.actor.priority || second.actor.id.localeCompare(first.actor.id));
    const loser = candidates[0];
    if (!loser) break;
    loser.opacity = 0;
    loser.reason = 'focus-fade';
  }

  for (const state of states) {
    if (state.opacity <= 0.2) continue;
    let overflow = overflowAmount(boundsFor(state), safe);
    if (overflow <= EPSILON || state.actor.fixed) continue;
    const correction = clampToSafe(boundsFor(state), safe);
    const previousMax = state.actor.maxShift;
    state.actor = {...state.actor, maxShift: Math.max(previousMax ?? 0, 520)};
    setCandidate(state, correction.dx, correction.dy, safe);
    state.actor = {...state.actor, maxShift: previousMax};
    overflow = overflowAmount(boundsFor(state), safe);
    while (overflow > EPSILON && state.scale > 0.86 && state.actor.canScale !== false) {
      state.scale = Math.max(0.86, state.scale - 0.02);
      const next = clampToSafe(boundsFor(state), safe);
      const originalActor = state.actor;
      state.actor = {...state.actor, maxShift: 520};
      setCandidate(state, next.dx, next.dy, safe);
      state.actor = originalActor;
      overflow = overflowAmount(boundsFor(state), safe);
      state.reason = 'scale';
    }
    if (overflow > EPSILON && state.actor.priority < 950) {
      state.opacity = 0;
      state.reason = 'focus-fade';
    }
  }
}

export function solveChoreography(actors: ActorBox[], safe: SafeArea): ChoreographySolution {
  const states: MutableState[] = actors.map(actor => ({
    actor,
    id: actor.id,
    dx: 0,
    dy: 0,
    scale: 1,
    opacity: 1,
    reason: 'none',
  }));

  for (const state of states) {
    if (state.actor.fixed) continue;
    const correction = clampToSafe(boundsFor(state), safe);
    if (Math.abs(correction.dx) > EPSILON || Math.abs(correction.dy) > EPSILON) {
      setCandidate(state, correction.dx, correction.dy, safe);
      state.reason = 'safe-area';
    }
  }

  for (let iteration = 0; iteration < 24; iteration += 1) {
    const conflict = worstConflict(states);
    if (!conflict) break;
    let mover = chooseMover(conflict.first, conflict.second);
    if (!mover) break;
    let obstacle = mover === conflict.first ? conflict.second : conflict.first;
    const baseline = globalScore(states, safe);
    const original = {...mover};
    let best = {...original};
    let bestScore = baseline;
    const moverBounds = boundsFor(mover);
    const obstacleBounds = boundsFor(obstacle);
    for (const candidate of candidateOffsets(
      moverBounds,
      obstacleBounds,
      Math.max(mover.actor.gap, obstacle.actor.gap),
    )) {
      Object.assign(mover, original);
      if (!setCandidate(mover, candidate.dx, candidate.dy, safe)) continue;
      const score = globalScore(states, safe);
      if (score + 1 < bestScore) {
        best = {...mover};
        bestScore = score;
      }
    }
    Object.assign(mover, best);
    if (bestScore + 1 < baseline) {
      if (mover.reason === 'none') mover.reason = 'nudge';
      continue;
    }

    Object.assign(mover, original);
    const minimumScale = mover.actor.minScale ?? 0.94;
    if (mover.actor.canScale !== false && mover.scale > minimumScale + 0.005) {
      mover.scale = Math.max(minimumScale, Math.round((mover.scale - 0.02) * 100) / 100);
      const safeCorrection = clampToSafe(boundsFor(mover), safe);
      setCandidate(mover, safeCorrection.dx, safeCorrection.dy, safe);
      if (globalScore(states, safe) < baseline) {
        mover.reason = 'scale';
        continue;
      }
      Object.assign(mover, original);
    }

    if (mover.actor.canFade) {
      mover.opacity = 0;
      mover.reason = 'focus-fade';
      continue;
    }

    const alternate = mover === conflict.first ? conflict.second : conflict.first;
    if (!alternate.actor.fixed) {
      mover = alternate;
      obstacle = mover === conflict.first ? conflict.second : conflict.first;
      const alternateOriginal = {...mover};
      let alternateBest = {...alternateOriginal};
      let alternateBestScore = baseline;
      for (const candidate of candidateOffsets(
        boundsFor(mover),
        boundsFor(obstacle),
        Math.max(mover.actor.gap, obstacle.actor.gap),
      )) {
        Object.assign(mover, alternateOriginal);
        if (!setCandidate(mover, candidate.dx, candidate.dy, safe)) continue;
        const score = globalScore(states, safe);
        if (score + 1 < alternateBestScore) {
          alternateBest = {...mover};
          alternateBestScore = score;
        }
      }
      Object.assign(mover, alternateBest);
      if (alternateBestScore + 1 < baseline) {
        if (mover.reason === 'none') mover.reason = 'nudge';
        continue;
      }
      Object.assign(mover, alternateOriginal);
    }
    break;
  }

  forceResolve(states, safe);

  const unresolved: ChoreographySolution['unresolved'] = [];
  for (let index = 0; index < states.length; index += 1) {
    const first = states[index];
    if (first.opacity <= 0.2) continue;
    const overflow = overflowAmount(boundsFor(first), safe);
    if (overflow > EPSILON) unresolved.push({first: first.id, amount: overflow});
    for (let otherIndex = index + 1; otherIndex < states.length; otherIndex += 1) {
      const second = states[otherIndex];
      if (second.opacity <= 0.2 || pairIgnored(first.actor, second.actor)) continue;
      const amount = conflictAmount(
        boundsFor(first),
        boundsFor(second),
        Math.max(first.actor.gap, second.actor.gap),
      );
      if (amount > EPSILON) unresolved.push({first: first.id, second: second.id, amount});
    }
  }

  return {
    corrections: states.map(({actor: _actor, ...correction}) => correction),
    unresolved,
  };
}
