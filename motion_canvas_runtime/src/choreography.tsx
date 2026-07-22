import {Circle, Grid, Layout, Line, Node, Rect, Txt} from '@motion-canvas/2d';
import {
  ActorBox,
  ActorCorrection,
  Bounds,
  SafeArea,
  solveChoreography,
} from './choreography-core';

export type KineticRole =
  | 'title'
  | 'primary'
  | 'diagram'
  | 'comparison'
  | 'equation'
  | 'readout'
  | 'supporting'
  | 'label'
  | 'decorative';

export interface KineticActorMetadata {
  id?: string;
  role?: KineticRole;
  priority?: number;
  gap?: number;
  canShift?: boolean;
  canScale?: boolean;
  canFade?: boolean;
  maxShift?: number;
  minScale?: number;
}

export interface KineticFrameReport {
  frame: number;
  scene: string;
  actors: number;
  labels: number;
  corrections: Array<ActorCorrection & {role: KineticRole; source: 'explicit' | 'diagram-fallback' | 'label'}>;
  unresolved: Array<{first: string; second?: string; amount: number}>;
  errors?: string[];
}

const actorMetadata = new WeakMap<Node, Required<KineticActorMetadata>>();

const ROLE_DEFAULTS: Record<KineticRole, Required<Omit<KineticActorMetadata, 'id' | 'role'>>> = {
  title: {priority: 1000, gap: 32, canShift: false, canScale: false, canFade: false, maxShift: 0, minScale: 1},
  primary: {priority: 900, gap: 32, canShift: true, canScale: true, canFade: false, maxShift: 110, minScale: 0.94},
  diagram: {priority: 880, gap: 32, canShift: true, canScale: true, canFade: false, maxShift: 120, minScale: 0.94},
  comparison: {priority: 850, gap: 32, canShift: true, canScale: true, canFade: false, maxShift: 90, minScale: 0.96},
  readout: {priority: 760, gap: 28, canShift: true, canScale: true, canFade: true, maxShift: 220, minScale: 0.94},
  equation: {priority: 720, gap: 28, canShift: true, canScale: true, canFade: true, maxShift: 240, minScale: 0.94},
  supporting: {priority: 640, gap: 28, canShift: true, canScale: true, canFade: true, maxShift: 260, minScale: 0.94},
  label: {priority: 320, gap: 10, canShift: true, canScale: false, canFade: true, maxShift: 180, minScale: 1},
  decorative: {priority: 100, gap: 12, canShift: true, canScale: true, canFade: true, maxShift: 280, minScale: 0.88},
};

function normalizedMetadata(node: Node, metadata: KineticActorMetadata): Required<KineticActorMetadata> {
  const role = metadata.role ?? 'supporting';
  const defaults = ROLE_DEFAULTS[role];
  return {
    id: metadata.id || node.key,
    role,
    priority: metadata.priority ?? defaults.priority,
    gap: metadata.gap ?? defaults.gap,
    canShift: metadata.canShift ?? defaults.canShift,
    canScale: metadata.canScale ?? defaults.canScale,
    canFade: metadata.canFade ?? defaults.canFade,
    maxShift: metadata.maxShift ?? defaults.maxShift,
    minScale: metadata.minScale ?? defaults.minScale,
  };
}

export function registerKineticActor<T extends Node>(node: T, metadata: KineticActorMetadata): T {
  actorMetadata.set(node, normalizedMetadata(node, metadata));
  return node;
}

export function kineticMetadata(node: Node): Required<KineticActorMetadata> | undefined {
  return actorMetadata.get(node);
}

export class KineticLayout extends Layout {
  public constructor({kinetic, ...props}: any) {
    super(props);
    registerKineticActor(this, kinetic ?? {});
  }
}

export class KineticRect extends Rect {
  public constructor({kinetic, ...props}: any) {
    super(props);
    registerKineticActor(this, kinetic ?? {});
  }
}

export interface KineticActorProps extends KineticActorMetadata {
  children?: any;
  x?: any;
  y?: any;
  position?: any;
  rotation?: any;
  scale?: any;
  opacity?: any;
  zIndex?: any;
}

export function KineticActor(props: KineticActorProps) {
  const {
    id, role = 'primary', priority, gap, canShift, canScale, canFade, maxShift, minScale,
    children, ...placement
  } = props;
  return <KineticLayout
    kinetic={{id, role, priority, gap, canShift, canScale, canFade, maxShift, minScale}}
    {...placement}
  >{children}</KineticLayout>;
}

interface RuntimeActor {
  id: string;
  node: Node;
  metadata: Required<KineticActorMetadata>;
  source: 'explicit' | 'diagram-fallback' | 'label';
  groupId?: string;
}

function boundsFor(node: Node): Bounds | null {
  const box = node.cacheBBox();
  const matrix = node.localToWorld();
  const points = box.corners.map(point => point.transformAsPoint(matrix));
  if (!points.length) return null;
  const xs = points.map(point => point.x);
  const ys = points.map(point => point.y);
  const left = Math.min(...xs);
  const right = Math.max(...xs);
  const top = Math.min(...ys);
  const bottom = Math.max(...ys);
  if (![left, right, top, bottom].every(Number.isFinite)) return null;
  if (right - left < 2 || bottom - top < 2) return null;
  return {left, right, top, bottom, width: right - left, height: bottom - top};
}

function isAncestor(first: Node, second: Node): boolean {
  let current = second.parent();
  while (current) {
    if (current === first) return true;
    current = current.parent();
  }
  return false;
}

function instantiatedDescendants(node: Node): Node[] {
  const result: Node[] = [];
  const queue = [...node.peekChildren()];
  while (queue.length) {
    const current = queue.shift()!;
    result.push(current);
    queue.push(...current.peekChildren());
  }
  return result;
}

function explicitDescendants(node: Node): Node[] {
  return instantiatedDescendants(node).filter(candidate => Boolean(kineticMetadata(candidate)));
}

function promotedRoot(node: Node, view: Node): Node {
  let root = node;
  while (root.parent() && root.parent() !== view) {
    const parent = root.parent()!;
    const siblings = parent.peekChildren();
    const isManagedStack = parent instanceof Layout && Boolean(parent.layout());
    if (siblings.length === 1 || isManagedStack) {
      root = parent;
      continue;
    }
    break;
  }
  return root;
}

function combineMetadata(nodes: Node[], root: Node): Required<KineticActorMetadata> {
  const values = nodes.map(node => kineticMetadata(node)).filter(Boolean) as Required<KineticActorMetadata>[];
  if (!values.length) return normalizedMetadata(root, {role: 'supporting'});
  const strongest = [...values].sort((first, second) => second.priority - first.priority)[0];
  return {
    ...strongest,
    id: values.length === 1 ? strongest.id : `cluster:${root.key}`,
    gap: Math.max(...values.map(value => value.gap)),
    canShift: values.every(value => value.canShift),
    canScale: values.every(value => value.canScale),
    canFade: values.every(value => value.canFade),
    maxShift: Math.max(...values.map(value => value.maxShift)),
    minScale: Math.max(...values.map(value => value.minScale)),
  };
}

function containsDiagramPrimitive(node: Node): boolean {
  return node instanceof Circle || node instanceof Grid || node instanceof Line || instantiatedDescendants(node).some(
    child => child instanceof Circle || child instanceof Grid || child instanceof Line,
  );
}

function collectMainActors(view: Node): RuntimeActor[] {
  const visible = instantiatedDescendants(view).filter(node => node.absoluteOpacity() > 0.02);
  const explicitByRoot = new Map<Node, Node[]>();
  for (const node of visible) {
    if (!kineticMetadata(node)) continue;
    const root = promotedRoot(node, view);
    const group = explicitByRoot.get(root) ?? [];
    group.push(node);
    explicitByRoot.set(root, group);
  }
  const actors: RuntimeActor[] = [];
  for (const [root, nodes] of explicitByRoot) {
    if (root.absoluteOpacity() <= 0.02 || !boundsFor(root)) continue;
    actors.push({id: combineMetadata(nodes, root).id, node: root, metadata: combineMetadata(nodes, root), source: 'explicit'});
  }

  for (const child of view.peekChildren()) {
    if (child.absoluteOpacity() <= 0.02) continue;
    if (actors.some(actor => actor.node === child || isAncestor(child, actor.node))) continue;
    if (explicitDescendants(child).length) continue;
    if (child instanceof Grid) continue;
    const bounds = boundsFor(child);
    if (!bounds || !containsDiagramPrimitive(child)) continue;
    const nearCanvas = bounds.width >= 1800 && bounds.height >= 1000;
    const plausibleDiagram = bounds.width >= 320 && bounds.width <= 1500 && bounds.height >= 180 && bounds.height <= 850;
    if (nearCanvas || !plausibleDiagram) continue;
    const metadata = normalizedMetadata(child, {
      id: `auto-diagram:${child.key}`,
      role: 'diagram',
      priority: 880,
      maxShift: 120,
      minScale: 0.94,
      canFade: false,
    });
    actors.push({id: metadata.id, node: child, metadata, source: 'diagram-fallback'});
  }
  return actors;
}

function actorBoxes(actors: RuntimeActor[], fixed = false): ActorBox[] {
  const result: ActorBox[] = [];
  for (const actor of actors) {
    const bounds = boundsFor(actor.node);
    if (!bounds) continue;
    result.push({
      id: actor.id,
      bounds,
      priority: actor.metadata.priority,
      gap: actor.metadata.gap,
      fixed: fixed || !actor.metadata.canShift,
      maxShift: actor.metadata.maxShift,
      minScale: actor.metadata.minScale,
      canScale: actor.metadata.canScale,
      canFade: actor.metadata.canFade,
      groupId: actor.groupId,
    });
  }
  return result;
}

function applyWorldOffset(node: Node, dx: number, dy: number) {
  if (Math.abs(dx) < 0.01 && Math.abs(dy) < 0.01) return;
  const matrix = node.worldToParent();
  const origin = new DOMPoint(0, 0).matrixTransform(matrix);
  const target = new DOMPoint(dx, dy).matrixTransform(matrix);
  const current = node.position();
  node.position([current.x + target.x - origin.x, current.y + target.y - origin.y]);
}

function applyCorrection(actor: RuntimeActor, correction: ActorCorrection) {
  applyWorldOffset(actor.node, correction.dx, correction.dy);
  if (correction.scale < 0.999) {
    const current = actor.node.scale();
    actor.node.scale([current.x * correction.scale, current.y * correction.scale]);
  }
  if (correction.opacity < 0.999) {
    actor.node.opacity(actor.node.opacity() * correction.opacity);
  }
}

function collectDiagramLabels(diagrams: RuntimeActor[]): RuntimeActor[] {
  const labels: RuntimeActor[] = [];
  for (const diagram of diagrams) {
    for (const node of instantiatedDescendants(diagram.node).filter(candidate => candidate instanceof Txt && candidate.absoluteOpacity() > 0.02)) {
      const label = node as Txt;
      if (kineticMetadata(label)) continue;
      const text = String(label.text() ?? '').trim();
      if (!text || text.split(/\s+/).length > 6) continue;
      const metadata = normalizedMetadata(label, {
        id: `auto-label:${label.key}`,
        role: 'label',
        priority: 320,
        gap: 10,
        maxShift: 180,
        canScale: false,
        canFade: true,
      });
      labels.push({
        id: metadata.id,
        node: label,
        metadata,
        source: 'label',
        groupId: diagram.id,
      });
    }
  }
  return labels;
}

function reportCorrections(
  actors: RuntimeActor[],
  corrections: ActorCorrection[],
): KineticFrameReport['corrections'] {
  const byId = new Map(actors.map(actor => [actor.id, actor]));
  return corrections
    .filter(correction => correction.reason !== 'none')
    .map(correction => {
      const actor = byId.get(correction.id)!;
      return {...correction, role: actor.metadata.role, source: actor.source};
    });
}

export function choreographScene(
  scene: any,
  frame: number,
  safe: SafeArea = {left: 100, right: 1820, top: 100, bottom: 980},
): KineticFrameReport {
  const view = scene.getView() as Node;
  const mainActors = collectMainActors(view);
  const mainSolution = solveChoreography(actorBoxes(mainActors), safe);
  const mainById = new Map(mainActors.map(actor => [actor.id, actor]));
  for (const correction of mainSolution.corrections) {
    const actor = mainById.get(correction.id);
    if (actor) applyCorrection(actor, correction);
  }

  const diagrams = mainActors.filter(actor => actor.metadata.role === 'diagram' || actor.metadata.role === 'primary');
  const labels = collectDiagramLabels(diagrams);
  const labelSolution = solveChoreography([
    ...actorBoxes(mainActors, true),
    ...actorBoxes(labels),
  ], safe);
  const labelsById = new Map(labels.map(actor => [actor.id, actor]));
  for (const correction of labelSolution.corrections) {
    const label = labelsById.get(correction.id);
    if (label) applyCorrection(label, correction);
  }

  return {
    frame,
    scene: String(scene.name || 'unknown'),
    actors: mainActors.length,
    labels: labels.length,
    corrections: [
      ...reportCorrections(mainActors, mainSolution.corrections),
      ...reportCorrections(labels, labelSolution.corrections),
    ],
    unresolved: [...mainSolution.unresolved, ...labelSolution.unresolved],
  };
}
