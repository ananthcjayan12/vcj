import { registry } from '../modules/_registry.js';

const scenes = Object.fromEntries(
  Object.entries(registry).map(([name, SceneClass]) => [name, SceneClass.getParamSchema()])
);

process.stdout.write(`${JSON.stringify(scenes)}\n`);
