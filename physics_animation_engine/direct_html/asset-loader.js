(function directHTMLAssets(global) {
  "use strict";
  function localAsset(name) {
    const assets = global.lessonAssets && Array.isArray(global.lessonAssets.assets) ? global.lessonAssets.assets : [];
    const entry = assets.find((item) => item.id === name);
    if (!entry) throw new Error(`Unknown local asset ${name}`);
    if (/^(?:https?:)?\/\//i.test(entry.path)) throw new Error(`Remote asset rejected: ${entry.path}`);
    return entry.path;
  }
  global.DirectHTMLAssets = { localAsset };
})(window);
