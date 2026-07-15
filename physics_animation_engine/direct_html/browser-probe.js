(function browserProbe(global) {
  "use strict";
  const accentColors = new Map([
    ["rgb(53, 198, 244)", "cyan"],
    ["rgb(100, 139, 255)", "blue"],
    ["rgb(67, 214, 160)", "green"],
    ["rgb(245, 196, 81)", "yellow"],
    ["rgb(255, 138, 91)", "orange"],
    ["rgb(255, 101, 119)", "red"],
  ]);
  function visible(element) {
    const rect = element.getBoundingClientRect();
    if (rect.width <= 1 || rect.height <= 1) return false;
    let current = element;
    while (current && current instanceof Element) {
      const style = getComputedStyle(current);
      if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) <= 0.01) return false;
      if (current.hasAttribute("data-chapter-id")) break;
      current = current.parentElement;
    }
    return true;
  }
  function rgb(value) {
    const match = String(value || "").match(/rgba?\(\s*([\d.]+)[, ]+\s*([\d.]+)[, ]+\s*([\d.]+)(?:[, /]+\s*([\d.]+))?\s*\)/i);
    if (!match || (match[4] !== undefined && Number(match[4]) === 0)) return null;
    return [Number(match[1]), Number(match[2]), Number(match[3])];
  }
  function luminance(color) {
    const channels = color.map(function (channel) {
      const normalized = channel / 255;
      return normalized <= 0.04045 ? normalized / 12.92 : Math.pow((normalized + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
  }
  function contrastRatio(foreground, background) {
    if (!foreground || !background) return null;
    const first = luminance(foreground), second = luminance(background);
    return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
  }
  function effectiveBackground(element) {
    const bounds = element.getBoundingClientRect();
    const behind = document.elementsFromPoint(bounds.left + bounds.width / 2, bounds.top + bounds.height / 2);
    for (let index = 0; index < behind.length; index += 1) {
      const candidate = behind[index];
      if (candidate === element || candidate.contains(element)) continue;
      const style = getComputedStyle(candidate);
      const background = rgb(style.backgroundColor);
      if (background) return background;
      if (["rect", "circle", "ellipse", "path", "polygon"].includes(String(candidate.tagName).toLowerCase())) {
        const fill = rgb(style.fill);
        if (fill) return fill;
      }
    }
    let current = element.parentElement;
    while (current) {
      const color = rgb(getComputedStyle(current).backgroundColor);
      if (color) return color;
      current = current.parentElement;
    }
    const stage = document.getElementById("stage");
    return rgb(stage ? getComputedStyle(stage).backgroundColor : "") || [7, 19, 31];
  }
  function snapshot(time) {
    global.lessonPlayer.seek(time);
    const chapterId = global.lessonPlayer.getChapterAt(time);
    const chapter = document.querySelector(`[data-chapter-id="${CSS.escape(chapterId)}"]`);
    const objects = chapter ? Array.from(chapter.querySelectorAll("[data-visual-object]")).filter(visible) : [];
    const important = chapter ? Array.from(chapter.querySelectorAll('[data-qa="important"]')).filter(visible) : [];
    const accents = new Set();
    if (chapter) {
      Array.from(chapter.querySelectorAll("*")).filter(visible).forEach((element) => {
        const style = getComputedStyle(element);
        [style.color, style.fill, style.stroke].forEach((value) => {
          if (accentColors.has(value)) accents.add(accentColors.get(value));
        });
      });
    }
    return {
      time,
      chapter_id: chapterId,
      active_objects: objects.length,
      accent_colors: Array.from(accents).sort(),
      important: important.map((element) => {
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        const text = element.textContent ? element.textContent.trim() : "";
        const foreground = rgb(style.fill) || rgb(style.color);
        return { id: element.id || null, tag: element.tagName, left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom, font_size: parseFloat(style.fontSize) || null, opacity: Number(style.opacity), transform: style.transform, stroke_dashoffset: style.strokeDashoffset, text, contrast_ratio: contrastRatio(foreground, effectiveBackground(element)) };
      }),
    };
  }
  global.DirectHTMLProbe = { visible, snapshot };
})(window);
