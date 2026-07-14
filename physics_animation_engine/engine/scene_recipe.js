const SVG_NS = 'http://www.w3.org/2000/svg';

const NODE_TYPES = new Set([
  'text', 'label', 'callout', 'object', 'apparatus', 'measurement',
  'vector', 'line', 'ray', 'equation', 'bar', 'graph', 'particles',
  'region', 'answer_cover',
  // Canonical deterministic manifest vocabulary.
  'axis', 'clock', 'counter', 'digital_timer', 'divider', 'error_bar',
  'eye', 'liquid', 'measuring_cylinder', 'meniscus', 'pendulum',
  'quantity_card', 'ruler', 'scale_key', 'sight_line', 'stopwatch',
  'timeline'
]);
const APPARATUS_KINDS = new Set([
  'ruler', 'measuring_cylinder', 'stopwatch', 'pendulum',
  'protractor', 'paper_stack', 'robot_grid'
]);
const OBJECT_KINDS = new Set(['block', 'ball', 'car', 'eye', 'gear']);
const ACTION_OPS = new Set([
  'reveal', 'hide', 'move', 'rotate', 'scale', 'draw', 'highlight',
  'count', 'fill', 'reveal_answer', 'persist',
  // Canonical deterministic manifest vocabulary.
  'classify', 'compare', 'measure', 'oscillate', 'trace', 'update'
]);
const LAYOUTS = new Set([
  'canvas', 'experiment', 'comparison', 'cause_effect', 'simulation_graph',
  'worked_example', 'prediction_reveal', 'system_flow', 'evidence_zoom',
  'classification', 'experiment_bench', 'instrument_demo', 'scale_drawing',
  'timeline'
]);
const WORKBENCHES = new Set([
  'measurement', 'mechanics', 'materials', 'energy', 'thermal', 'waves',
  'fields', 'circuits', 'electromagnetic', 'atomic', 'space', 'general',
  'Measurement and apparatus', 'Mechanics, forces and vectors',
  'Materials and fluids', 'Energy and system flow', 'Matter and thermal physics',
  'Waves, optics and signals', 'Fields, charge and magnetism',
  'Circuits and electrical systems', 'Electromagnetic devices',
  'Atomic and nuclear physics', 'Space, scale and timelines'
]);
const COLORS = new Set(['ink', 'muted', 'teal', 'yellow', 'orange', 'red', 'paper', 'pitch']);
const EASES = new Set([
  'power1.in', 'power1.out', 'power1.inOut',
  'power2.in', 'power2.out', 'power2.inOut',
  'power3.in', 'power3.out', 'power3.inOut',
  'power4.in', 'power4.out', 'power4.inOut',
  'back.out(1.2)', 'back.out(1.4)', 'back.out(1.6)',
  'sine.in', 'sine.out', 'sine.inOut', 'circ.in', 'circ.out', 'circ.inOut'
]);
const TO_KEYS = new Set(['x', 'y', 'rotation', 'scale', 'opacity', 'value', 'percent', 'color']);
const DEFAULT_DURATION = 8;
const DEFAULT_FADE = 0.45;

function fail(path, message) {
  throw new Error(`Invalid scene recipe at ${path}: ${message}`);
}

function record(value, path) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) fail(path, 'expected an object');
  return value;
}

function textValue(value, path, { required = false, max = 500 } = {}) {
  if (value == null && !required) return '';
  if (typeof value !== 'string') fail(path, 'expected a string');
  const result = value.trim();
  if (required && !result) fail(path, 'must not be empty');
  if (result.length > max) fail(path, `must be at most ${max} characters`);
  return result;
}

function finite(value, path, { min = -Infinity, max = Infinity, fallback } = {}) {
  if (value == null && fallback !== undefined) return fallback;
  if (typeof value !== 'number' || !Number.isFinite(value)) fail(path, 'expected a finite number');
  if (value < min || value > max) fail(path, `must be between ${min} and ${max}`);
  return value;
}

function integer(value, path, options = {}) {
  const result = finite(value, path, options);
  if (!Number.isInteger(result)) fail(path, 'expected an integer');
  return result;
}

function booleanValue(value, path, fallback = false) {
  if (value == null) return fallback;
  if (typeof value !== 'boolean') fail(path, 'expected a boolean');
  return value;
}

function enumValue(value, allowed, path, fallback) {
  const result = value == null ? fallback : value;
  if (typeof result !== 'string' || !allowed.has(result)) {
    fail(path, `expected one of: ${[...allowed].join(', ')}`);
  }
  return result;
}

function colorValue(value, path, fallback = 'ink') {
  return enumValue(value, COLORS, path, fallback);
}

function normalized(value, path, fallback) {
  return finite(value, path, { min: 0, max: 1, fallback });
}

function validatePoints(value, path) {
  if (!Array.isArray(value) || value.length < 2 || value.length > 80) {
    fail(path, 'expected an array containing 2 to 80 points');
  }
  return value.map((point, index) => {
    const item = record(point, `${path}[${index}]`);
    return {
      x: normalized(item.x, `${path}[${index}].x`),
      y: normalized(item.y, `${path}[${index}].y`),
      label: textValue(item.label, `${path}[${index}].label`, { max: 80 })
    };
  });
}

function validateNode(raw, index) {
  const path = `recipe.nodes[${index}]`;
  const node = record(raw, path);
  const type = enumValue(node.type, NODE_TYPES, `${path}.type`);
  const result = {
    id: textValue(node.id, `${path}.id`, { required: true, max: 80 }),
    type,
    x: normalized(node.x, `${path}.x`),
    y: normalized(node.y, `${path}.y`),
    width: normalized(node.width, `${path}.width`),
    height: normalized(node.height, `${path}.height`),
    text: textValue(node.text, `${path}.text`),
    label: textValue(node.label, `${path}.label`, { max: 120 }),
    color: colorValue(node.color, `${path}.color`),
    hidden: booleanValue(node.hidden, `${path}.hidden`),
    answer: booleanValue(node.answer, `${path}.answer`),
    value: node.value == null
      ? null
      : (typeof node.value === 'string'
          ? textValue(node.value, `${path}.value`, { required: true, max: 120 })
          : finite(node.value, `${path}.value`, { min: -1e9, max: 1e9 })),
    unit: textValue(node.unit, `${path}.unit`, { max: 24 }),
    percent: node.percent == null ? null : finite(node.percent, `${path}.percent`, { min: 0, max: 100 }),
    count: node.count == null ? (type === 'particles' ? 24 : 1) : integer(node.count, `${path}.count`, { min: 1, max: 120 }),
    direction: node.direction == null
      ? ''
      : (typeof node.direction === 'string'
          ? textValue(node.direction, `${path}.direction`, { required: true, max: 80 })
          : finite(node.direction, `${path}.direction`, { min: -3600, max: 3600 })),
    min: node.minimum == null
      ? (node.min == null ? 0 : finite(node.min, `${path}.min`, { min: -1e9, max: 1e9 }))
      : finite(node.minimum, `${path}.minimum`, { min: -1e9, max: 1e9 }),
    max: node.maximum == null
      ? (node.max == null ? 100 : finite(node.max, `${path}.max`, { min: -1e9, max: 1e9 }))
      : finite(node.maximum, `${path}.maximum`, { min: -1e9, max: 1e9 }),
    decimals: node.decimals == null ? 0 : integer(node.decimals, `${path}.decimals`, { min: 0, max: 6 }),
    role: textValue(node.role, `${path}.role`, { max: 80 }),
    orientation: textValue(node.orientation, `${path}.orientation`, { max: 80 }),
    state: textValue(node.state, `${path}.state`, { max: 80 }),
    reading: node.reading == null ? null : finite(node.reading, `${path}.reading`, { min: -1e9, max: 1e9 }),
    scaleValue: node.scale == null ? null : finite(node.scale, `${path}.scale`, { min: -1e9, max: 1e9 }),
    magnitude: node.magnitude == null ? null : finite(node.magnitude, `${path}.magnitude`, { min: -1e9, max: 1e9 }),
    points: node.points == null ? [] : validatePoints(node.points, `${path}.points`),
    items: node.items == null ? [] : (() => {
      if (!Array.isArray(node.items) || !node.items.length || node.items.length > 24) fail(`${path}.items`, 'expected 1 to 24 strings');
      return node.items.map((item, itemIndex) => textValue(item, `${path}.items[${itemIndex}]`, { required: true, max: 80 }));
    })()
  };

  if (result.width <= 0 || result.height <= 0) fail(path, 'width and height must be greater than 0');
  if (result.x + result.width > 1.000001 || result.y + result.height > 1.000001) {
    fail(path, 'geometry must remain inside the normalized 0..1 canvas');
  }
  if (type === 'apparatus') result.kind = enumValue(node.kind, APPARATUS_KINDS, `${path}.kind`);
  if (type === 'object') {
    if (node.kind != null) result.kind = enumValue(node.kind, OBJECT_KINDS, `${path}.kind`);
    else {
      const hint = `${result.id} ${result.label} ${result.role}`.toLowerCase();
      result.kind = hint.includes('gear') ? 'gear' : (hint.includes('sheet') || hint.includes('paper') ? 'paper_stack' : 'block');
    }
  }
  if (type === 'eye') result.kind = 'eye';
  if (['ruler', 'measuring_cylinder', 'stopwatch', 'pendulum'].includes(type)) result.kind = type;
  if (type === 'graph') {
    if (!result.points.length) fail(`${path}.points`, 'is required for graph nodes');
    result.xLabel = textValue(node.xLabel, `${path}.xLabel`, { max: 40 });
    result.yLabel = textValue(node.yLabel, `${path}.yLabel`, { max: 40 });
  }
  if (type === 'line' || type === 'ray' || type === 'vector') {
    result.x2 = normalized(node.x2, `${path}.x2`, 1);
    result.y2 = normalized(node.y2, `${path}.y2`, type === 'line' ? 1 : 0.5);
    if (typeof result.direction === 'string') {
      const endpoint = {
        left: [0, .5], right: [1, .5], up: [.5, 0], down: [.5, 1],
        northeast: [1, 0], northwest: [0, 0], southeast: [1, 1], southwest: [0, 1]
      }[result.direction.toLowerCase()];
      if (endpoint) [result.x2, result.y2] = endpoint;
    }
  }
  if (type === 'measurement' && result.value == null) fail(`${path}.value`, 'is required for measurement nodes');
  if (['counter', 'digital_timer', 'quantity_card', 'clock'].includes(type) && result.value == null) {
    result.value = result.reading == null ? 0 : result.reading;
  }
  if (node.decimals == null && typeof result.value === 'string' && /^-?\d+\.\d+$/.test(result.value)) {
    result.decimals = result.value.split('.')[1].length;
  }
  if (['bar', 'error_bar'].includes(type)) {
    const rangedValue = typeof result.value === 'number' ? result.value : (result.reading ?? result.min);
    result.percent = result.percent == null
      ? Math.max(0, Math.min(100, (rangedValue - result.min) / (result.max - result.min) * 100))
      : result.percent;
  }
  if (type === 'answer_cover') result.answer = true;
  if (result.max <= result.min) fail(path, 'max must be greater than min');
  return result;
}

function validateTo(raw, path) {
  const source = record(raw, path);
  Object.keys(source).forEach(key => {
    if (!TO_KEYS.has(key)) fail(`${path}.${key}`, 'is not an allowed animation destination');
  });
  const result = {};
  if ('x' in source) result.x = normalized(source.x, `${path}.x`);
  if ('y' in source) result.y = normalized(source.y, `${path}.y`);
  if ('rotation' in source) result.rotation = finite(source.rotation, `${path}.rotation`, { min: -3600, max: 3600 });
  if ('scale' in source) result.scale = finite(source.scale, `${path}.scale`, { min: 0.01, max: 20 });
  if ('opacity' in source) result.opacity = finite(source.opacity, `${path}.opacity`, { min: 0, max: 1 });
  if ('value' in source) result.value = finite(source.value, `${path}.value`, { min: -1e9, max: 1e9 });
  if ('percent' in source) result.percent = finite(source.percent, `${path}.percent`, { min: 0, max: 100 });
  if ('color' in source) result.color = colorValue(source.color, `${path}.color`);
  return result;
}

function validateAction(raw, index, nodeIds, cueCount) {
  const path = `recipe.actions[${index}]`;
  const action = record(raw, path);
  if (action.type != null && action.op != null) fail(path, 'use either type or op, not both');
  const normalizedTime = action.type != null;
  const op = enumValue(action.type ?? action.op, ACTION_OPS, normalizedTime ? `${path}.type` : `${path}.op`);
  const target = textValue(action.target, `${path}.target`, { required: true, max: 80 });
  if (!nodeIds.has(target)) fail(`${path}.target`, `references unknown node "${target}"`);
  const hasAt = action.at != null;
  const hasCue = action.cueIndex != null;
  if (hasAt && hasCue) fail(path, 'use either at or cueIndex, not both');
  const result = {
    op,
    target,
    at: hasAt ? finite(action.at, `${path}.at`, { min: 0, max: normalizedTime ? 1 : 86400 }) : 0,
    cueIndex: hasCue ? integer(action.cueIndex, `${path}.cueIndex`, { min: 0, max: Math.max(0, cueCount - 1) }) : null,
    duration: finite(action.duration, `${path}.duration`, { min: 0.0001, max: normalizedTime ? 1 : 120, fallback: normalizedTime ? .08 : .55 }),
    ease: enumValue(action.ease, EASES, `${path}.ease`, 'power2.inOut'),
    to: action.to == null ? {} : validateTo(action.to, `${path}.to`),
    normalizedTime,
    value: action.value == null
      ? null
      : (typeof action.value === 'string'
          ? textValue(action.value, `${path}.value`, { required: true, max: 120 })
          : finite(action.value, `${path}.value`, { min: -1e9, max: 1e9 })),
    label: textValue(action.label, `${path}.label`, { max: 120 }),
    count: action.count == null ? null : integer(action.count, `${path}.count`, { min: 1, max: 10000 }),
    amplitude: action.amplitude == null ? .06 : normalized(action.amplitude, `${path}.amplitude`),
    direction: textValue(action.direction, `${path}.direction`, { max: 80 })
  };
  if (hasCue && cueCount === 0) fail(`${path}.cueIndex`, 'cannot be used without params.cuePoints');
  const needsTo = new Set(['rotate', 'scale', 'fill']);
  if (!normalizedTime) needsTo.add('move').add('count');
  if (needsTo.has(op) && !Object.keys(result.to).length) fail(`${path}.to`, `is required for ${op}`);
  if (op === 'move' && Object.keys(result.to).length && !('x' in result.to || 'y' in result.to)) fail(`${path}.to`, 'move requires x or y');
  if (op === 'rotate' && !('rotation' in result.to)) fail(`${path}.to.rotation`, 'is required for rotate');
  if (op === 'scale' && !('scale' in result.to)) fail(`${path}.to.scale`, 'is required for scale');
  if (op === 'count' && !normalizedTime && !('value' in result.to)) fail(`${path}.to.value`, 'is required for count');
  if (op === 'fill' && !('percent' in result.to)) fail(`${path}.to.percent`, 'is required for fill');
  if (normalizedTime && result.at + result.duration > 1.000001) fail(path, 'must finish within the normalized timeline');
  return result;
}

export function validateRecipe(rawRecipe, params = {}) {
  const recipe = record(rawRecipe, 'recipe');
  const cuePoints = params.cuePoints == null ? [] : params.cuePoints;
  if (!Array.isArray(cuePoints)) fail('params.cuePoints', 'expected an array');
  const normalizedCues = cuePoints.map((cue, index) => finite(cue, `params.cuePoints[${index}]`, { min: 0, max: 86400 }));
  if (!Array.isArray(recipe.nodes) || !recipe.nodes.length || recipe.nodes.length > 120) {
    fail('recipe.nodes', 'expected an array containing 1 to 120 nodes');
  }
  if (!Array.isArray(recipe.actions) || recipe.actions.length > 300) {
    fail('recipe.actions', 'expected an array containing at most 300 actions');
  }
  const nodes = recipe.nodes.map(validateNode);
  const ids = new Set();
  nodes.forEach((node, index) => {
    if (ids.has(node.id)) fail(`recipe.nodes[${index}].id`, `duplicate id "${node.id}"`);
    ids.add(node.id);
  });
  const actions = recipe.actions.map((action, index) => validateAction(action, index, ids, normalizedCues.length));
  return {
    recipe: {
      id: textValue(recipe.id, 'recipe.id', { required: true, max: 100 }),
      workbench: enumValue(recipe.workbench, WORKBENCHES, 'recipe.workbench'),
      layout: enumValue(recipe.layout, LAYOUTS, 'recipe.layout'),
      title: textValue(recipe.title, 'recipe.title', { max: 140 }),
      subtitle: textValue(recipe.subtitle, 'recipe.subtitle', { max: 240 }),
      nodes,
      actions
    },
    cuePoints: normalizedCues
  };
}

function html(tag, className, value = '') {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (value !== '') element.textContent = String(value);
  return element;
}

function svgElement(tag, attributes = {}) {
  const element = document.createElementNS(SVG_NS, tag);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, String(value)));
  return element;
}

function addSvgText(parent, value, x, y, className = '') {
  const node = svgElement('text', { x, y, class: className });
  node.textContent = String(value ?? '');
  parent.appendChild(node);
  return node;
}

function iconSvg(className = '') {
  return svgElement('svg', { class: `recipe-icon ${className}`.trim(), viewBox: '0 0 100 100', 'aria-hidden': 'true' });
}

function renderRuler(node = {}) {
  const svg = iconSvg('recipe-ruler');
  const vertical = node.orientation === 'vertical';
  svg.setAttribute('viewBox', vertical ? '0 0 100 500' : '0 0 500 100');
  if (vertical) {
    svg.appendChild(svgElement('rect', { x: 30, y: 4, width: 40, height: 492, rx: 3, class: 'recipe-paper-shape' }));
  } else {
    svg.appendChild(svgElement('rect', { x: 4, y: 30, width: 492, height: 40, rx: 3, class: 'recipe-paper-shape' }));
  }
  for (let index = 0; index <= 20; index += 1) {
    const position = 7 + index * 24.3;
    const attributes = vertical
      ? { x1: 30, y1: position, x2: index % 5 === 0 ? 48 : 40, y2: position }
      : { x1: position, y1: 30, x2: position, y2: index % 5 === 0 ? 48 : 40 };
    svg.appendChild(svgElement('line', { ...attributes, class: 'recipe-tick' }));
  }
  addSvgText(svg, '0', vertical ? 38 : 7, vertical ? 18 : 62, 'recipe-svg-small');
  addSvgText(svg, node.unit || 'cm', vertical ? 38 : 455, vertical ? 480 : 62, 'recipe-svg-small');
  return svg;
}

function renderCylinder() {
  const svg = iconSvg('recipe-cylinder');
  svg.appendChild(svgElement('path', { d: 'M28 8 L28 82 Q28 92 50 92 Q72 92 72 82 L72 8', class: 'recipe-outline' }));
  svg.appendChild(svgElement('ellipse', { cx: 50, cy: 8, rx: 22, ry: 5, class: 'recipe-outline' }));
  svg.appendChild(svgElement('path', { d: 'M30 58 Q50 64 70 58 L70 82 Q70 89 50 89 Q30 89 30 82 Z', class: 'recipe-liquid recipe-fill-target' }));
  for (let y = 18; y <= 72; y += 9) svg.appendChild(svgElement('line', { x1: 28, y1: y, x2: y % 18 === 0 ? 42 : 37, y2: y, class: 'recipe-tick' }));
  return svg;
}

function renderStopwatch() {
  const svg = iconSvg('recipe-stopwatch');
  svg.appendChild(svgElement('rect', { x: 44, y: 4, width: 12, height: 10, rx: 2, class: 'recipe-solid' }));
  svg.appendChild(svgElement('circle', { cx: 50, cy: 55, r: 37, class: 'recipe-paper-shape' }));
  svg.appendChild(svgElement('circle', { cx: 50, cy: 55, r: 4, class: 'recipe-accent' }));
  svg.appendChild(svgElement('line', { x1: 50, y1: 55, x2: 50, y2: 29, class: 'recipe-hand' }));
  svg.appendChild(svgElement('line', { x1: 50, y1: 55, x2: 67, y2: 63, class: 'recipe-hand secondary' }));
  return svg;
}

function renderClock() {
  const svg = iconSvg('recipe-clock');
  svg.appendChild(svgElement('circle', { cx: 50, cy: 50, r: 42, class: 'recipe-paper-shape' }));
  for (let index = 0; index < 12; index += 1) {
    const angle = index * Math.PI / 6;
    svg.appendChild(svgElement('line', {
      x1: 50 + Math.sin(angle) * 32,
      y1: 50 - Math.cos(angle) * 32,
      x2: 50 + Math.sin(angle) * 38,
      y2: 50 - Math.cos(angle) * 38,
      class: 'recipe-tick'
    }));
  }
  svg.appendChild(svgElement('line', { x1: 50, y1: 50, x2: 50, y2: 24, class: 'recipe-hand' }));
  svg.appendChild(svgElement('line', { x1: 50, y1: 50, x2: 69, y2: 61, class: 'recipe-hand secondary' }));
  svg.appendChild(svgElement('circle', { cx: 50, cy: 50, r: 4, class: 'recipe-solid' }));
  return svg;
}

function renderPendulum() {
  const svg = iconSvg('recipe-pendulum');
  svg.appendChild(svgElement('path', { d: 'M12 14 H88 M22 14 V88 M78 14 V88', class: 'recipe-support' }));
  svg.appendChild(svgElement('path', { d: 'M28 74 Q50 92 72 74', class: 'recipe-guide recipe-drawable' }));
  const arm = svgElement('g', { class: 'recipe-pendulum-arm' });
  arm.appendChild(svgElement('line', { x1: 50, y1: 14, x2: 50, y2: 70, class: 'recipe-string' }));
  arm.appendChild(svgElement('circle', { cx: 50, cy: 75, r: 9, class: 'recipe-accent' }));
  svg.appendChild(arm);
  return svg;
}

function renderProtractor() {
  const svg = iconSvg('recipe-protractor');
  svg.appendChild(svgElement('path', { d: 'M8 80 A42 42 0 0 1 92 80 Z', class: 'recipe-paper-shape' }));
  svg.appendChild(svgElement('path', { d: 'M28 80 A22 22 0 0 1 72 80', class: 'recipe-outline' }));
  for (let angle = 0; angle <= 180; angle += 15) {
    const radians = Math.PI - angle * Math.PI / 180;
    const x1 = 50 + Math.cos(radians) * 35;
    const y1 = 80 - Math.sin(radians) * 35;
    const x2 = 50 + Math.cos(radians) * 42;
    const y2 = 80 - Math.sin(radians) * 42;
    svg.appendChild(svgElement('line', { x1, y1, x2, y2, class: 'recipe-tick' }));
  }
  return svg;
}

function renderPaperStack() {
  const svg = iconSvg('recipe-paper-stack');
  for (let index = 4; index >= 0; index -= 1) {
    svg.appendChild(svgElement('rect', { x: 12 + index * 2, y: 18 + index * 10, width: 72, height: 48, rx: 2, class: index === 0 ? 'recipe-paper-shape' : 'recipe-sheet' }));
  }
  return svg;
}

function renderRobotGrid() {
  const svg = iconSvg('recipe-robot-grid');
  for (let step = 10; step <= 90; step += 20) {
    svg.appendChild(svgElement('line', { x1: step, y1: 5, x2: step, y2: 95, class: 'recipe-grid-line' }));
    svg.appendChild(svgElement('line', { x1: 5, y1: step, x2: 95, y2: step, class: 'recipe-grid-line' }));
  }
  const robot = svgElement('g', { class: 'recipe-robot' });
  robot.appendChild(svgElement('rect', { x: 35, y: 35, width: 30, height: 30, rx: 6, class: 'recipe-accent' }));
  robot.appendChild(svgElement('circle', { cx: 44, cy: 48, r: 3, class: 'recipe-eye-dot' }));
  robot.appendChild(svgElement('circle', { cx: 56, cy: 48, r: 3, class: 'recipe-eye-dot' }));
  robot.appendChild(svgElement('line', { x1: 42, y1: 57, x2: 58, y2: 57, class: 'recipe-mouth' }));
  svg.appendChild(robot);
  return svg;
}

function renderApparatus(kind, node = {}) {
  const renderer = {
    ruler: renderRuler,
    measuring_cylinder: renderCylinder,
    stopwatch: renderStopwatch,
    pendulum: renderPendulum,
    protractor: renderProtractor,
    paper_stack: renderPaperStack,
    robot_grid: renderRobotGrid
  }[kind];
  return renderer(node);
}

function renderObject(kind) {
  const svg = iconSvg(`recipe-object-${kind}`);
  if (kind === 'block') {
    svg.appendChild(svgElement('rect', { x: 13, y: 23, width: 74, height: 58, rx: 7, class: 'recipe-object-shape' }));
  } else if (kind === 'ball') {
    svg.appendChild(svgElement('circle', { cx: 50, cy: 50, r: 35, class: 'recipe-object-shape' }));
    svg.appendChild(svgElement('path', { d: 'M25 30 Q50 50 75 30 M25 70 Q50 50 75 70', class: 'recipe-detail' }));
  } else if (kind === 'car') {
    svg.appendChild(svgElement('path', { d: 'M12 62 L22 39 H65 L82 52 H91 V73 H10 V62 Z', class: 'recipe-object-shape' }));
    svg.appendChild(svgElement('circle', { cx: 28, cy: 75, r: 10, class: 'recipe-wheel' }));
    svg.appendChild(svgElement('circle', { cx: 73, cy: 75, r: 10, class: 'recipe-wheel' }));
  } else if (kind === 'eye') {
    svg.appendChild(svgElement('path', { d: 'M7 50 Q50 8 93 50 Q50 92 7 50 Z', class: 'recipe-paper-shape' }));
    svg.appendChild(svgElement('circle', { cx: 50, cy: 50, r: 17, class: 'recipe-iris' }));
    svg.appendChild(svgElement('circle', { cx: 50, cy: 50, r: 7, class: 'recipe-pupil' }));
  } else if (kind === 'gear') {
    const gear = svgElement('g', { class: 'recipe-gear' });
    for (let angle = 0; angle < 360; angle += 45) gear.appendChild(svgElement('rect', { x: 44, y: 5, width: 12, height: 22, rx: 2, transform: `rotate(${angle} 50 50)`, class: 'recipe-object-shape' }));
    gear.appendChild(svgElement('circle', { cx: 50, cy: 50, r: 29, class: 'recipe-object-shape' }));
    gear.appendChild(svgElement('circle', { cx: 50, cy: 50, r: 10, class: 'recipe-paper-hole' }));
    svg.appendChild(gear);
  }
  return svg;
}

let markerSequence = 0;

function directionEndpoints(direction) {
  const aliases = {
    east: 'right', west: 'left', north: 'up', south: 'down',
    'north-east': 'northeast', 'north-west': 'northwest',
    'south-east': 'southeast', 'south-west': 'southwest'
  };
  const named = typeof direction === 'string' ? (aliases[direction.toLowerCase()] || direction.toLowerCase()) : '';
  const endpoints = {
    right: [5, 50, 95, 50], left: [95, 50, 5, 50],
    up: [50, 95, 50, 5], down: [50, 5, 50, 95],
    northeast: [5, 95, 95, 5], northwest: [95, 95, 5, 5],
    southeast: [5, 5, 95, 95], southwest: [95, 5, 5, 95]
  };
  if (endpoints[named]) return endpoints[named];
  if (typeof direction === 'number') {
    const radians = direction * Math.PI / 180;
    return [
      50 - Math.cos(radians) * 45,
      50 + Math.sin(radians) * 45,
      50 + Math.cos(radians) * 45,
      50 - Math.sin(radians) * 45
    ];
  }
  return null;
}

function addArrowMarker(svg, node, markerSize) {
  markerSequence += 1;
  const markerId = `recipe-arrow-${String(node.id).replace(/[^a-zA-Z0-9_-]/g, '-')}-${markerSequence}`;
  const defs = svgElement('defs');
  const marker = svgElement('marker', {
    id: markerId, viewBox: '0 0 10 10', refX: 9, refY: 5,
    markerUnits: 'userSpaceOnUse', markerWidth: markerSize, markerHeight: markerSize, orient: 'auto-start-reverse'
  });
  marker.appendChild(svgElement('path', { d: 'M0 0 L10 5 L0 10 Z', class: 'recipe-arrow-marker' }));
  defs.appendChild(marker);
  svg.appendChild(defs);
  return markerId;
}

function renderVector(node) {
  const svg = iconSvg(`recipe-${node.type}`);
  const svgScale = Math.max(.01, Math.min(node.width * 1920, node.height * 1080) / 100);
  const strokeWidth = 5 / svgScale;
  const markerId = node.type === 'line' ? '' : addArrowMarker(svg, node, 16 / svgScale);
  const markerAttributes = markerId ? { 'marker-end': `url(#${markerId})` } : {};
  const className = `recipe-stroke recipe-drawable ${node.type === 'ray' ? 'is-ray' : ''}`;
  const strokeStyle = `stroke-width:${strokeWidth}`;
  if (node.points && node.points.length > 1) {
    const points = node.points.map(point => `${4 + point.x * 92},${4 + point.y * 92}`).join(' ');
    svg.appendChild(svgElement('polyline', { points, class: className, style: strokeStyle, ...markerAttributes }));
  } else {
    const directed = directionEndpoints(node.direction);
    const [x1, y1, x2, y2] = directed || [4, 50, node.x2 * 92 + 4, node.y2 * 92 + 4];
    svg.appendChild(svgElement('line', { x1, y1, x2, y2, class: className, style: strokeStyle, ...markerAttributes }));
  }
  return svg;
}

function renderGraph(node) {
  const svg = iconSvg('recipe-graph-svg');
  for (let value = 20; value <= 80; value += 20) {
    svg.appendChild(svgElement('line', { x1: value, y1: 8, x2: value, y2: 88, class: 'recipe-grid-line' }));
    svg.appendChild(svgElement('line', { x1: 12, y1: value, x2: 94, y2: value, class: 'recipe-grid-line' }));
  }
  svg.appendChild(svgElement('line', { x1: 12, y1: 88, x2: 94, y2: 88, class: 'recipe-axis' }));
  svg.appendChild(svgElement('line', { x1: 12, y1: 88, x2: 12, y2: 8, class: 'recipe-axis' }));
  const points = node.points.map(point => `${12 + point.x * 82},${88 - point.y * 80}`).join(' ');
  svg.appendChild(svgElement('polyline', { points, class: 'recipe-plot recipe-drawable' }));
  if (node.xLabel) addSvgText(svg, node.xLabel, 72, 98, 'recipe-svg-small');
  if (node.yLabel) addSvgText(svg, node.yLabel, 4, 12, 'recipe-svg-small');
  return svg;
}

function hashText(value) {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function seeded(seed) {
  let state = seed || 1;
  return () => {
    state = Math.imul(state ^ (state >>> 15), 1 | state);
    state ^= state + Math.imul(state ^ (state >>> 7), 61 | state);
    return ((state ^ (state >>> 14)) >>> 0) / 4294967296;
  };
}

function renderParticles(node) {
  const field = html('div', 'recipe-particle-field');
  const random = seeded(hashText(node.id));
  for (let index = 0; index < node.count; index += 1) {
    const particle = html('i', 'recipe-particle');
    particle.style.setProperty('--particle-x', `${5 + random() * 90}%`);
    particle.style.setProperty('--particle-y', `${5 + random() * 90}%`);
    particle.style.setProperty('--particle-size', `${10 + random() * 16}px`);
    field.appendChild(particle);
  }
  return field;
}

function renderAxis(node) {
  const svg = iconSvg('recipe-axis-svg');
  const horizontal = node.orientation !== 'vertical';
  if (horizontal) {
    svg.appendChild(svgElement('line', { x1: 5, y1: 55, x2: 95, y2: 55, class: 'recipe-axis recipe-drawable' }));
    svg.appendChild(svgElement('path', { d: 'M86 48 L95 55 L86 62', class: 'recipe-arrowhead' }));
  } else {
    svg.appendChild(svgElement('line', { x1: 50, y1: 95, x2: 50, y2: 5, class: 'recipe-axis recipe-drawable' }));
    svg.appendChild(svgElement('path', { d: 'M43 14 L50 5 L57 14', class: 'recipe-arrowhead' }));
  }
  if (node.label) addSvgText(svg, node.label, horizontal ? 72 : 57, horizontal ? 75 : 15, 'recipe-svg-label');
  return svg;
}

function renderMeniscus(node) {
  const svg = iconSvg('recipe-meniscus');
  svg.appendChild(svgElement('rect', { x: 18, y: 8, width: 64, height: 84, rx: 5, class: 'recipe-outline' }));
  const curve = node.state === 'convex' ? 'M20 52 Q50 36 80 52' : 'M20 45 Q50 61 80 45';
  svg.appendChild(svgElement('path', { d: curve, class: 'recipe-meniscus-line recipe-drawable' }));
  svg.appendChild(svgElement('path', { d: `${curve} L80 90 L20 90 Z`, class: 'recipe-liquid' }));
  return svg;
}

function renderTimelineNode(node) {
  const svg = iconSvg('recipe-timeline-svg');
  svg.appendChild(svgElement('line', { x1: 6, y1: 50, x2: 94, y2: 50, class: 'recipe-axis recipe-drawable' }));
  const points = node.points.length
    ? node.points
    : node.items.map((label, index) => ({ x: (index + 1) / (node.items.length + 1), y: .5, label }));
  points.forEach(point => {
    const x = 6 + point.x * 88;
    svg.appendChild(svgElement('circle', { cx: x, cy: 50, r: 3.5, class: 'recipe-accent' }));
    if (point.label) addSvgText(svg, point.label, x, point.y < .5 ? 38 : 68, 'recipe-svg-label centered');
  });
  return svg;
}

function displayValue(node) {
  if (node.value != null) return String(node.value);
  if (node.reading != null) return String(node.reading);
  if (node.magnitude != null) return String(node.magnitude);
  return '0';
}

function renderNode(node) {
  const element = html('div', `recipe-node recipe-node-${node.type}`);
  element.dataset.recipeNode = node.id;
  element.dataset.color = node.color;
  element.style.setProperty('--node-x', `${node.x * 100}%`);
  element.style.setProperty('--node-y', `${node.y * 100}%`);
  element.style.setProperty('--node-w', `${node.width * 100}%`);
  element.style.setProperty('--node-h', `${node.height * 100}%`);
  if (node.hidden || node.answer) element.classList.add('is-concealed');

  if (node.type === 'text') element.appendChild(html('p', 'recipe-copy', node.text));
  else if (node.type === 'label') element.appendChild(html('span', 'recipe-label', node.text || node.label));
  else if (node.type === 'callout') {
    element.append(html('span', 'recipe-callout-rule'), html('p', 'recipe-callout-copy', node.text));
  } else if (node.type === 'object' || node.type === 'eye') {
    element.appendChild(node.kind === 'paper_stack' ? renderPaperStack() : renderObject(node.kind));
    if (node.label) element.appendChild(html('span', 'recipe-object-label', node.label));
    if (node.type === 'object' && node.count > 1) element.appendChild(html('strong', 'recipe-value recipe-object-count', '1'));
  }
  else if (node.type === 'apparatus' || ['ruler', 'measuring_cylinder', 'stopwatch', 'pendulum'].includes(node.type)) {
    const drawing = renderApparatus(node.kind, node);
    const initialFill = node.reading == null ? 65 : Math.max(0, Math.min(100, (node.reading - node.min) / (node.max - node.min) * 100));
    drawing.style.setProperty('--recipe-fill', `${initialFill}%`);
    element.appendChild(drawing);
    if (node.type === 'stopwatch' && node.value != null) {
      element.append(html('strong', 'recipe-value recipe-stopwatch-value', displayValue(node)), html('small', 'recipe-unit recipe-stopwatch-unit', node.unit));
    }
  }
  else if (node.type === 'clock') {
    element.appendChild(renderClock());
    if (node.label) element.appendChild(html('span', 'recipe-object-label', node.label));
  } else if (node.type === 'quantity_card') {
    element.appendChild(html('strong', 'recipe-card-title', node.label));
    const list = html('ul', 'recipe-card-items');
    node.items.forEach(item => list.appendChild(html('li', '', item)));
    element.appendChild(list);
  } else if (['measurement', 'counter', 'digital_timer'].includes(node.type)) {
    element.append(html('span', 'recipe-measure-label', node.label), html('strong', 'recipe-value', displayValue(node)), html('small', 'recipe-unit', node.unit));
  } else if (node.type === 'vector' || node.type === 'line' || node.type === 'ray') {
    element.appendChild(renderVector(node));
    if (node.label || node.text) element.appendChild(html('span', 'recipe-stroke-label', node.label || node.text));
  } else if (node.type === 'sight_line') {
    element.appendChild(renderVector({ ...node, type: 'line', x2: 1, y2: .5 }));
    if (node.label) element.appendChild(html('span', 'recipe-stroke-label', node.label));
  } else if (node.type === 'axis') element.appendChild(renderAxis(node));
  else if (node.type === 'divider') element.appendChild(renderVector({ ...node, type: 'line', x2: node.orientation === 'vertical' ? .5 : 1, y2: node.orientation === 'vertical' ? 1 : .5 }));
  else if (node.type === 'meniscus') element.appendChild(renderMeniscus(node));
  else if (node.type === 'liquid') {
    const fill = html('i', 'recipe-liquid-block recipe-fill-target');
    const initialFill = node.reading == null ? 60 : Math.max(0, Math.min(100, (node.reading - node.min) / (node.max - node.min) * 100));
    fill.style.setProperty('--recipe-fill', `${initialFill}%`);
    element.appendChild(fill);
    if (node.label) element.appendChild(html('span', 'recipe-liquid-label', node.label));
  } else if (node.type === 'timeline') element.appendChild(renderTimelineNode(node));
  else if (node.type === 'scale_key') element.append(html('span', 'recipe-scale-key-label', node.label || 'Scale'));
  else if (node.type === 'equation') element.appendChild(html('p', 'recipe-equation', node.text || node.label || displayValue(node)));
  else if (node.type === 'bar' || node.type === 'error_bar') {
    const track = html('div', 'recipe-bar-track');
    const fill = html('i', 'recipe-bar-fill');
    fill.style.setProperty('--recipe-fill', `${node.percent}%`);
    track.appendChild(fill);
    const barValue = node.type === 'error_bar' ? `${displayValue(node)}${node.unit ? ` ${node.unit}` : ''}` : `${node.percent}%`;
    element.append(html('span', 'recipe-bar-label', node.label), track, html('strong', 'recipe-bar-value', barValue));
  } else if (node.type === 'graph') element.appendChild(renderGraph(node));
  else if (node.type === 'particles') element.appendChild(renderParticles(node));
  else if (node.type === 'region') {
    element.append(html('strong', 'recipe-region-label', node.label), html('p', 'recipe-region-copy', node.text));
  } else if (node.type === 'answer_cover') element.appendChild(html('span', 'recipe-cover-copy', node.text || 'Pause • predict • reveal'));
  return element;
}

function resolveAt(action, cues, actionWindow) {
  if (action.cueIndex != null) return cues[action.cueIndex];
  return action.normalizedTime ? action.at * actionWindow : action.at;
}

function drawSetup(target) {
  const drawables = [...target.querySelectorAll('.recipe-drawable')];
  target.querySelectorAll('.recipe-arrow-marker').forEach(marker => { marker.style.opacity = '0'; });
  drawables.forEach(path => {
    if (typeof path.getTotalLength !== 'function') return;
    const matrix = path.getScreenCTM?.();
    const screenScale = matrix ? Math.sqrt(Math.abs(matrix.a * matrix.d - matrix.b * matrix.c)) : 1;
    const length = path.getTotalLength() * screenScale;
    path.style.strokeDasharray = String(length);
    path.style.strokeDashoffset = String(length);
  });
  return drawables;
}

function colorToken(name) {
  return `var(--recipe-${name})`;
}

export class RecipeScene {
  setup(container, params = {}) {
    if (!(container instanceof Element)) throw new Error('RecipeScene.setup requires a DOM Element container');
    if (!params || typeof params !== 'object' || Array.isArray(params)) fail('params', 'expected an object');
    const validated = validateRecipe(params.recipe, params);
    this.recipe = validated.recipe;
    this.cuePoints = validated.cuePoints;
    this.params = params;
    this.nodes = new Map();

    this.root = html('section', 'scene-root mav-v3-scene recipe-scene');
    this.root.dataset.scene = 'RecipeScene';
    this.root.dataset.recipeId = this.recipe.id;
    this.root.dataset.workbench = this.recipe.workbench;
    this.root.dataset.layout = this.recipe.layout;
    this.root.append(html('div', 'paper-bg'), html('div', 'grain'), html('div', 'vignette'));

    const camera = html('div', 'camera recipe-camera');
    const content = html('div', 'v3-scene-content recipe-content');
    if (this.recipe.title || this.recipe.subtitle) {
      const header = html('header', 'recipe-header');
      if (this.recipe.title) header.appendChild(html('h2', 'recipe-title', this.recipe.title));
      if (this.recipe.subtitle) header.appendChild(html('p', 'recipe-subtitle', this.recipe.subtitle));
      content.appendChild(header);
    }
    this.recipe.nodes.forEach(node => {
      const element = renderNode(node);
      content.appendChild(element);
      this.nodes.set(node.id, element);
    });
    camera.appendChild(content);
    this.root.appendChild(camera);
    container.appendChild(this.root);
  }

  buildTimeline(params = this.params || {}) {
    if (!this.root || !this.recipe) throw new Error('RecipeScene.setup must be called before buildTimeline');
    if (typeof globalThis.gsap === 'undefined') throw new Error('RecipeScene requires global gsap');
    const seconds = finite(params.duration, 'params.duration', { min: 2, max: 86400, fallback: DEFAULT_DURATION });
    const finalHold = finite(params.finalHoldSeconds, 'params.finalHoldSeconds', { min: 0, max: seconds - .1, fallback: 1 });
    const fadeDuration = Math.min(DEFAULT_FADE, Math.max(.1, seconds - finalHold));
    const lastActionTime = seconds - finalHold - fadeDuration;
    const timeline = gsap.timeline({ paused: true, defaults: { overwrite: false } });
    timeline.set(this.root, { autoAlpha: 1 }, 0);
    const header = this.root.querySelector('.recipe-header');
    if (header) timeline.fromTo(header, { y: -24, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55, ease: 'power3.out' }, .05);

    this.recipe.actions.forEach((action, index) => {
      const actionWindow = Math.max(.1, lastActionTime);
      const at = resolveAt(action, this.cuePoints, actionWindow);
      const runtimeAction = {
        ...action,
        duration: action.normalizedTime ? action.duration * actionWindow : action.duration
      };
      if (at > lastActionTime) {
        fail(`recipe.actions[${index}]`, `starts at ${at}s, after the usable action window ending at ${lastActionTime.toFixed(2)}s`);
      }
      const target = this.nodes.get(action.target);
      const end = at + runtimeAction.duration;
      if (end > seconds - finalHold && !['hide', 'persist'].includes(action.op)) {
        fail(`recipe.actions[${index}]`, `ends at ${end}s, inside the ${finalHold}s final hold`);
      }
      this.addAction(timeline, target, runtimeAction, at);
    });

    const fadeAt = seconds - fadeDuration;
    timeline.to(this.root, { autoAlpha: 0, duration: fadeDuration, ease: 'power2.in' }, fadeAt);
    if (timeline.duration() < seconds) timeline.to({}, { duration: seconds - timeline.duration() });
    return timeline;
  }

  addAction(timeline, target, action, at) {
    const to = action.to;
    if (action.op === 'reveal' || action.op === 'reveal_answer') {
      target.classList.remove('is-concealed');
      timeline.fromTo(target, { autoAlpha: 0, scale: .94 }, { autoAlpha: 1, scale: 1, duration: action.duration, ease: action.ease }, at);
    } else if (action.op === 'hide') {
      timeline.to(target, { autoAlpha: 0, duration: action.duration, ease: action.ease }, at);
    } else if (action.op === 'move' || action.op === 'classify') {
      const destination = {};
      if ('x' in to) destination.left = `${to.x * 100}%`;
      if ('y' in to) destination.top = `${to.y * 100}%`;
      if (Object.keys(destination).length) {
        timeline.to(target, { ...destination, duration: action.duration, ease: action.ease }, at);
      } else {
        timeline.to(target, { '--recipe-highlight': 1, scale: 1.035, duration: action.duration, ease: action.ease }, at);
      }
      if (action.label) {
        const label = target.querySelector('.recipe-label, .recipe-measure-label, .recipe-region-label');
        if (label) timeline.call(() => { label.textContent = action.label; }, null, at + action.duration);
      }
    } else if (action.op === 'rotate') {
      timeline.to(target, { rotation: to.rotation, duration: action.duration, ease: action.ease }, at);
    } else if (action.op === 'scale') {
      timeline.to(target, { scale: to.scale, duration: action.duration, ease: action.ease }, at);
    } else if (action.op === 'draw' || action.op === 'trace') {
      const paths = drawSetup(target);
      if (paths.length) {
        timeline.to(paths, { strokeDashoffset: 0, duration: action.duration, stagger: .06, ease: action.ease }, at);
        const arrowMarkers = [...target.querySelectorAll('.recipe-arrow-marker')];
        if (arrowMarkers.length) timeline.set(arrowMarkers, { opacity: 1 }, at + action.duration);
      }
      else timeline.fromTo(target, { autoAlpha: .25 }, { autoAlpha: 1, duration: action.duration, ease: action.ease }, at);
    } else if (action.op === 'highlight' || action.op === 'compare') {
      timeline.to(target, { '--recipe-highlight': 1, scale: 1.035, duration: action.duration * .55, ease: action.ease }, at)
        .to(target, { scale: 1, duration: action.duration * .45, ease: 'power2.out' }, at + action.duration * .55);
    } else if (action.op === 'count') {
      const valueNode = target.querySelector('.recipe-value');
      const node = this.recipe.nodes.find(item => item.id === action.target);
      const nodeValue = Number(node.value ?? node.reading ?? 0);
      const initialValue = action.normalizedTime ? 0 : nodeValue;
      const destinationValue = Number(
        to.value ?? action.value ?? (action.normalizedTime && nodeValue !== 0 ? nodeValue : action.count)
      );
      if (!valueNode || !Number.isFinite(initialValue) || !Number.isFinite(destinationValue)) {
        const destinationText = action.value ?? action.count ?? to.value;
        timeline.call(() => {
          const fallback = valueNode || target.querySelector('.recipe-label, .recipe-copy');
          if (fallback && destinationText != null) fallback.textContent = String(destinationText);
        }, null, at + action.duration);
      } else {
        const state = { value: initialValue };
        timeline.to(state, {
          value: destinationValue,
          duration: action.duration,
          ease: action.ease,
          onUpdate: () => { valueNode.textContent = state.value.toFixed(node.decimals); }
        }, at);
      }
    } else if (action.op === 'fill') {
      const fill = target.querySelector('.recipe-bar-fill, .recipe-fill-target');
      if (!fill) throw new Error(`Recipe action fill target "${action.target}" has no fillable element`);
      const valueNode = target.querySelector('.recipe-bar-value');
      const state = { percent: Number.parseFloat(fill.style.getPropertyValue('--recipe-fill')) || 0 };
      timeline.to(state, {
        percent: to.percent,
        duration: action.duration,
        ease: action.ease,
        onUpdate: () => {
          fill.style.setProperty('--recipe-fill', `${state.percent}%`);
          if (valueNode) valueNode.textContent = `${Math.round(state.percent)}%`;
        }
      }, at);
    } else if (action.op === 'measure') {
      const valueNode = target.querySelector('.recipe-value');
      const fill = target.querySelector('.recipe-fill-target');
      const node = this.recipe.nodes.find(item => item.id === action.target);
      if (valueNode && action.value != null) {
        timeline.call(() => { valueNode.textContent = String(action.value); }, null, at + action.duration * .6);
      }
      if (fill && typeof action.value === 'number') {
        const percent = Math.max(0, Math.min(100, (action.value - node.min) / (node.max - node.min) * 100));
        timeline.to(fill, { '--recipe-fill': `${percent}%`, duration: action.duration, ease: action.ease }, at);
      } else {
        timeline.to(target, { '--recipe-highlight': 1, scale: 1.025, duration: action.duration, ease: action.ease }, at);
      }
    } else if (action.op === 'oscillate') {
      const movingPart = target.querySelector('.recipe-pendulum-arm') || target;
      const vertical = action.direction.toLowerCase().includes('vertical');
      const travel = action.amplitude * (vertical ? 1080 : 1920);
      const repetitions = Math.max(1, action.count || 3);
      timeline.to(movingPart, {
        [vertical ? 'y' : 'x']: travel,
        rotation: movingPart.classList?.contains('recipe-pendulum-arm') ? action.amplitude * 180 : 0,
        duration: action.duration / (repetitions * 2),
        repeat: repetitions * 2 - 1,
        yoyo: true,
        ease: 'power2.inOut'
      }, at);
    } else if (action.op === 'update') {
      const valueNode = target.querySelector('.recipe-value, .recipe-scale-key-value, .recipe-bar-value, .recipe-equation');
      const labelNode = target.querySelector('.recipe-label, .recipe-measure-label, .recipe-region-label');
      timeline.call(() => {
        if (valueNode && action.value != null) valueNode.textContent = String(action.value);
        if (labelNode && action.label) labelNode.textContent = action.label;
      }, null, at + action.duration);
      const fill = target.querySelector('.recipe-fill-target, .recipe-bar-fill');
      const node = this.recipe.nodes.find(item => item.id === action.target);
      if (fill && typeof action.value === 'number') {
        const percent = Math.max(0, Math.min(100, (action.value - node.min) / (node.max - node.min) * 100));
        timeline.to(fill, { '--recipe-fill': `${percent}%`, duration: action.duration, ease: action.ease }, at);
      } else timeline.to(target, { '--recipe-highlight': 1, duration: action.duration, ease: action.ease }, at);
    } else if (action.op === 'persist') {
      timeline.set(target, { autoAlpha: to.opacity == null ? 1 : to.opacity }, at);
    }
    if (to.color && !['count', 'fill'].includes(action.op)) {
      timeline.to(target, { '--recipe-node-color': colorToken(to.color), duration: action.duration, ease: action.ease }, at);
    }
  }

  teardown() {
    this.root?.remove();
    this.root = null;
    this.nodes?.clear();
  }
}
