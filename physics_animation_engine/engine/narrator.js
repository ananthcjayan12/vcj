class Narrator {
  constructor() {
    this.enabled = false;
    this.subtitle = document.getElementById('subtitle-text');
    this.lastIndex = -1;
  }

  present(slide, index) {
    if (index === this.lastIndex) return;
    this.lastIndex = index;
    const text = slide.narration || slide.params.caption || slide.params.subtitle || `${slide.scene.replace('Scene_', '')} preview`;
    if (this.subtitle) this.subtitle.textContent = text;
    if (!this.enabled || !slide.narration || !('speechSynthesis' in window)) return;
    speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(slide.narration);
    utterance.rate = 0.96;
    utterance.pitch = 1;
    speechSynthesis.speak(utterance);
  }

  toggle() {
    this.enabled = !this.enabled;
    if (!this.enabled && 'speechSynthesis' in window) speechSynthesis.cancel();
    return this.enabled;
  }

  reset() {
    this.lastIndex = -1;
    if ('speechSynthesis' in window) speechSynthesis.cancel();
  }
}

export const narrator = new Narrator();
