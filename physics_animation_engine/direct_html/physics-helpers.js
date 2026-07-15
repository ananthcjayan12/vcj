(function physicsHelpers(global) {
  "use strict";
  function vectorComponents(magnitude, angleDegrees) {
    const radians = angleDegrees * Math.PI / 180;
    return { x: magnitude * Math.cos(radians), y: magnitude * Math.sin(radians) };
  }
  function resultant(x, y) {
    return { magnitude: Math.hypot(x, y), angleDegrees: Math.atan2(y, x) * 180 / Math.PI };
  }
  function assertPhysicsValue(key, value, tolerance = 1e-6) {
    const values = global.lessonPhysics && global.lessonPhysics.values ? global.lessonPhysics.values : {};
    const expected = values[key];
    if (expected === undefined) throw new Error(`Unknown physics key ${key}`);
    if (Math.abs(Number(expected) - Number(value)) > tolerance) throw new Error(`Physics value mismatch for ${key}`);
    return value;
  }
  global.DirectHTMLPhysics = { vectorComponents, resultant, assertPhysicsValue };
})(window);
