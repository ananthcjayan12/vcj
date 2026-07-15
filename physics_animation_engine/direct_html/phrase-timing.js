(function phraseTiming(global) {
  "use strict";
  const normalize = (value) => String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

  function atPhrase(paragraphId, phrase) {
    const words = (global.lessonTiming && Array.isArray(global.lessonTiming.words) ? global.lessonTiming.words : []).filter((item) => item.paragraph_id === paragraphId);
    const wanted = normalize(phrase).split(" ").filter(Boolean);
    const spoken = words.map((item) => normalize(item.word));
    for (let index = 0; index <= spoken.length - wanted.length; index += 1) {
      if (wanted.every((word, offset) => spoken[index + offset] === word)) return Number(words[index].start);
    }
    throw new Error(`Phrase not found in ${paragraphId}: ${phrase}`);
  }

  function betweenPhrases(paragraphId, startPhrase, endPhrase) {
    const start = atPhrase(paragraphId, startPhrase);
    const end = atPhrase(paragraphId, endPhrase);
    if (end < start) throw new Error(`Phrase range is reversed in ${paragraphId}`);
    return { start, end, duration: end - start };
  }

  global.DirectHTMLTiming = { atPhrase, betweenPhrases };
})(window);
