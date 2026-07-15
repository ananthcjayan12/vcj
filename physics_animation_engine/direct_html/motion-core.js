(function directHTMLRuntime(global) {
  "use strict";

  const chapters = new Map();
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  const targets = (value) => global.gsap.utils.toArray(value);

  function show(element, options = {}) {
    const { duration = 0.45, ease = "power2.out", ...vars } = options;
    return { targets: element, vars: { autoAlpha: 1, duration, ease, ...vars } };
  }

  function hide(element, options = {}) {
    const { duration = 0.35, ease = "power2.in", ...vars } = options;
    return { targets: element, vars: { autoAlpha: 0, duration, ease, ...vars } };
  }

  function drawPath(element, options = {}) {
    const nodes = targets(element);
    nodes.forEach((node) => {
      const length = typeof node.getTotalLength === "function" ? node.getTotalLength() : 1000;
      global.gsap.set(node, { strokeDasharray: length, strokeDashoffset: length });
    });
    return { targets: nodes, vars: { strokeDashoffset: 0, duration: 0.9, ease: "power2.inOut", ...options } };
  }

  function move(element, options = {}) {
    return { targets: element, vars: { duration: 0.7, ease: "power2.inOut", ...options } };
  }

  function scale(element, options = {}) {
    const nextScale = options.scale === undefined ? 1 : options.scale;
    return { targets: element, vars: { scale: nextScale, duration: 0.5, ease: "power2.out", ...options } };
  }

  function morphPath(from, to, options = {}) {
    const source = typeof from === "string" ? from : from.getAttribute("d");
    const destination = typeof to === "string" ? to : to.getAttribute("d");
    const sourceNumbers = source.match(/-?\d*\.?\d+/g) || [];
    const destinationNumbers = destination.match(/-?\d*\.?\d+/g) || [];
    if (sourceNumbers.length !== destinationNumbers.length) {
      throw new Error("DirectHTML morphPath requires compatible path command/number structures");
    }
    const proxy = { progress: 0 };
    const template = source.split(/-?\d*\.?\d+/g);
    const start = sourceNumbers.map(Number);
    const end = destinationNumbers.map(Number);
    return {
      targets: proxy,
      vars: {
        progress: 1,
        duration: 0.9,
        ease: "power2.inOut",
        ...options,
        onUpdate: () => {
          let path = template[0];
          start.forEach((value, index) => {
            path += String(value + (end[index] - value) * proxy.progress) + template[index + 1];
          });
          if (typeof from !== "string") from.setAttribute("d", path);
        },
      },
    };
  }

  function fitCamera(elements, padding = 100) {
    const nodes = targets(elements).filter((node) => typeof node.getBBox === "function");
    if (!nodes.length) return { x: 0, y: 0, scale: 1 };
    const boxes = nodes.map((node) => node.getBBox());
    const minX = Math.min(...boxes.map((box) => box.x));
    const minY = Math.min(...boxes.map((box) => box.y));
    const maxX = Math.max(...boxes.map((box) => box.x + box.width));
    const maxY = Math.max(...boxes.map((box) => box.y + box.height));
    const width = Math.max(1, maxX - minX);
    const height = Math.max(1, maxY - minY);
    const zoom = Math.min((1920 - 2 * padding) / width, (1080 - 2 * padding) / height, 1.2);
    return {
      scale: zoom,
      x: 960 - (minX + width / 2) * zoom,
      y: 540 - (minY + height / 2) * zoom,
    };
  }

  function focusCamera(elements, options = {}) {
    const camera = document.querySelector("#camera");
    const padding = options.padding === undefined ? 120 : options.padding;
    const duration = options.duration === undefined ? 1.25 : options.duration;
    return move(camera, { ...fitCamera(elements, padding), duration });
  }

  function clearChapter(chapterId) {
    const root = document.querySelector(`[data-chapter-id="${CSS.escape(chapterId)}"]`);
    if (root) global.gsap.set(root, { autoAlpha: 0 });
  }

  function measureSafeArea(chapterId, margin = 100) {
    const root = document.querySelector(`[data-chapter-id="${CSS.escape(chapterId)}"]`);
    if (!root) return [];
    return Array.from(root.querySelectorAll('[data-qa="important"]')).map((element) => {
      const rect = element.getBoundingClientRect();
      return {
        id: element.id || null,
        left: rect.left,
        top: rect.top,
        right: rect.right,
        bottom: rect.bottom,
        safe: rect.left >= margin && rect.top >= margin && rect.right <= 1920 - margin && rect.bottom <= 1080 - margin,
      };
    });
  }

  function registerChapter(definition) {
    if (!definition || !/^chapter_\d{2,3}$/.test(definition.id || "")) throw new Error("Invalid DirectHTML chapter id");
    if (chapters.has(definition.id)) throw new Error(`Duplicate DirectHTML chapter ${definition.id}`);
    if (!(Number(definition.end) > Number(definition.start))) throw new Error(`Invalid timing for ${definition.id}`);
    if (typeof definition.build !== "function") throw new Error(`Missing build function for ${definition.id}`);
    chapters.set(definition.id, definition);
  }

  function scaleViewport() {
    const viewport = document.querySelector("#viewport");
    if (!viewport) return;
    const ratio = Math.min(global.innerWidth / 1920, global.innerHeight / 1080);
    viewport.style.transform = `scale(${ratio})`;
    viewport.style.marginLeft = `${(global.innerWidth - 1920 * ratio) / 2}px`;
    viewport.style.marginTop = `${(global.innerHeight - 1080 * ratio) / 2}px`;
  }

  function boot(manifest) {
    if (!global.gsap) throw new Error("DirectHTML requires the local GSAP runtime");
    const ordered = [...chapters.values()].sort((a, b) => a.start - b.start);
    if (!ordered.length) throw new Error("DirectHTML has no registered chapters");
    const duration = Number(manifest.duration);
    const master = global.gsap.timeline({ paused: true });

    ordered.forEach((chapter, index) => {
      const root = document.querySelector(`[data-chapter-id="${CSS.escape(chapter.id)}"]`);
      if (!root) throw new Error(`Missing markup for ${chapter.id}`);
      // Nested timelines inherit the paused master clock. Marking a child as
      // paused prevents GSAP from rendering it when HyperFrames scrubs the
      // parent, so only the master itself is explicitly paused.
      const local = global.gsap.timeline();
      global.gsap.set(root, { autoAlpha: 0 });
      local.set(root, { autoAlpha: 1 }, 0);
      chapter.build({ tl: local, root, core: api, timing: global.lessonTiming || {}, physics: global.lessonPhysics || {} });
      local.set({}, {}, chapter.end - chapter.start);
      master.add(local, chapter.start);
      master.set(root, { autoAlpha: 0 }, chapter.end);
      if (index === ordered.length - 1) master.set({}, {}, duration);
    });

    global.__timelines = global.__timelines || {};
    global.__timelines.direct_html_master = master;
    global.__templateLabTimeline = master;
    global.__templateLabDuration = duration;
    global.lessonManifest = { ...manifest, chapters: ordered.map(({ build, ...chapter }) => chapter) };

    const audio = document.querySelector("#lesson-audio");
    const seek = (seconds) => {
      const next = clamp(Number(seconds) || 0, 0, duration);
      master.pause().time(next, false);
      if (audio && Math.abs(audio.currentTime - next) > 0.03) audio.currentTime = next;
      document.dispatchEvent(new CustomEvent("lesson-seek", { detail: { time: next } }));
      return next;
    };
    global.lessonPlayer = {
      duration,
      seek,
      play: async () => {
        master.play();
        if (audio) {
          audio.currentTime = master.time();
          await audio.play();
        }
      },
      pause: () => { master.pause(); if (audio) audio.pause(); },
      getCurrentTime: () => master.time(),
      getChapterAt: (seconds) => {
        const matching = ordered.find((chapter) => seconds >= chapter.start && seconds < chapter.end);
        const finalChapter = ordered.length ? ordered[ordered.length - 1] : null;
        return matching ? matching.id : (finalChapter ? finalChapter.id : null);
      },
    };

    if (audio) {
      audio.addEventListener("timeupdate", () => {
        if (!master.paused() && Math.abs(master.time() - audio.currentTime) > 0.05) master.time(audio.currentTime, false);
      });
      audio.addEventListener("ended", () => master.pause().time(duration, false));
    }
    if (global.__hf || new URLSearchParams(global.location.search).get("render") === "1") document.body.classList.add("direct-html-render");
    scaleViewport();
    global.addEventListener("resize", scaleViewport);
    seek(0);
    global.__directHTMLReady = true;
    document.dispatchEvent(new CustomEvent("direct-html-ready"));
    return master;
  }

  const api = {
    registerChapter,
    boot,
    show,
    hide,
    drawPath,
    move,
    scale,
    morphPath,
    focusCamera,
    fitCamera,
    clearChapter,
    measureSafeArea,
  };
  global.DirectHTML = api;
})(window);
