import { append, duration, el, finishTimeline, root } from '../engine/renderer.js';

function electronWord(count) {
  return `${count} electron${count === 1 ? '' : 's'}`;
}

export class Scene_AtomicModel {
  setup(container, params) {
    this.root = root(container, 'Scene_AtomicModel', 'scene-p2 scene-atomic-model');
    const electrons = params.electronConfig.reduce((sum, count) => sum + count, 0);
    const header = el('header', 'p2-scene-header');
    append(header,
      el('span', 'p2-kicker', { text: 'Bohr model' }),
      el('h2', '', { text: `${params.element}: structure of the atom` }),
      el('p', '', { text: `${params.protons} protons · ${params.neutrons} neutrons · ${electrons} electrons` })
    );

    this.board = el('section', 'p2-atom-board');
    this.atom = el('div', 'p2-atom');
    this.nucleus = el('div', 'p2-nucleus');
    const nucleonCount = params.protons + params.neutrons;
    for (let index = 0; index < nucleonCount; index++) {
      const nucleon = el('i', index < params.protons ? 'is-proton' : 'is-neutron');
      const angle = index * 137.508 * Math.PI / 180;
      const radius = 8 + Math.sqrt(index) * 8.4;
      nucleon.style.setProperty('--nucleon-x', `${Math.cos(angle) * radius}px`);
      nucleon.style.setProperty('--nucleon-y', `${Math.sin(angle) * radius}px`);
      this.nucleus.appendChild(nucleon);
    }
    append(this.nucleus, el('span', '', { text: `${params.protons}p⁺` }), el('small', '', { text: `${params.neutrons}n⁰` }));

    this.shells = params.electronConfig.map((count, shellIndex) => {
      const shell = el('div', `p2-electron-shell ${params.highlightShell === shellIndex + 1 ? 'is-highlighted' : ''}`);
      const size = 260 + shellIndex * 165;
      shell.style.setProperty('--shell-size', `${size}px`);
      shell.dataset.shell = String(shellIndex + 1);
      for (let index = 0; index < count; index++) {
        const electron = el('i', 'p2-electron');
        electron.style.setProperty('--electron-angle', `${index * 360 / count}deg`);
        electron.style.setProperty('--electron-radius', `${size / 2}px`);
        shell.appendChild(electron);
      }
      this.atom.appendChild(shell);
      return shell;
    });
    this.atom.appendChild(this.nucleus);
    this.board.appendChild(this.atom);

    this.legend = null;
    if (params.showLabels) {
      this.legend = el('aside', 'p2-atom-legend');
      const summary = el('div', 'p2-atom-summary');
      append(summary,
        el('small', '', { text: 'Atomic number' }), el('strong', '', { text: params.protons }),
        el('small', '', { text: 'Mass number' }), el('strong', '', { text: params.protons + params.neutrons })
      );
      const config = el('div', 'p2-shell-config');
      append(config, el('small', '', { text: 'Electron configuration' }));
      params.electronConfig.forEach((count, index) => {
        const row = el('span', params.highlightShell === index + 1 ? 'is-highlighted' : '');
        append(row,
          el('b', '', { text: `Shell ${index + 1}` }),
          el('i', '', { text: electronWord(count) })
        );
        config.appendChild(row);
      });
      const key = el('div', 'p2-nucleon-key');
      append(key,
        el('span', '', { html: '<i class="is-proton"></i> proton' }),
        el('span', '', { html: '<i class="is-neutron"></i> neutron' }),
        el('span', '', { html: '<i class="is-electron"></i> electron' })
      );
      append(this.legend, summary, config, key);
      this.board.appendChild(this.legend);
    }
    append(this.root, header, this.board);
  }

  buildTimeline(params) {
    const seconds = duration(params, 7.5);
    const tl = gsap.timeline({ paused: true });
    tl.set(this.root, { autoAlpha: 1 }, 0)
      .fromTo(this.root.querySelector('.p2-scene-header'), { y: -22, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .55 }, .08)
      .fromTo(this.board, { scale: .96, autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: .55 }, .28)
      .fromTo(this.nucleus.querySelectorAll(':scope > i'), { scale: 0, autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: .32, stagger: .025, ease: 'back.out(2)' }, .55)
      .fromTo(this.nucleus.querySelectorAll('span, small'), { y: 10, autoAlpha: 0 }, { y: 0, autoAlpha: 1, duration: .35, stagger: .08 }, 1.05)
      .fromTo(this.shells, { scale: .6, autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: .55, stagger: .22, ease: 'power3.out' }, 1.25)
      .fromTo(this.root.querySelectorAll('.p2-electron'), { scale: 0, autoAlpha: 0 }, { scale: 1, autoAlpha: 1, duration: .25, stagger: .035, ease: 'back.out(2.2)' }, 1.72);
    this.shells.forEach((shell, index) => {
      tl.to(shell, { rotate: (index % 2 ? -1 : 1) * (220 + index * 70), duration: Math.max(2, seconds - 2.25), ease: 'none' }, 2.05);
    });
    const highlighted = this.root.querySelector('.p2-electron-shell.is-highlighted');
    if (highlighted) tl.to(highlighted, { boxShadow: '0 0 44px rgba(255,210,63,.45)', duration: .7, repeat: 3, yoyo: true }, 2.15);
    if (this.legend) tl.fromTo(this.legend, { x: 35, autoAlpha: 0 }, { x: 0, autoAlpha: 1, duration: .55 }, 2.1);
    return finishTimeline(tl, this.root, seconds);
  }

  teardown() { this.root?.remove(); }

  static getParamSchema() {
    return {
      type: 'object', required: ['element', 'protons', 'neutrons', 'electronConfig'], additionalProperties: false,
      properties: {
        element: { type: 'string', maxLength: 30, default: 'Carbon' },
        protons: { type: 'integer', minimum: 1, maximum: 30, default: 6 },
        neutrons: { type: 'integer', minimum: 0, maximum: 40, default: 6 },
        electronConfig: { type: 'array', minItems: 1, maxItems: 4, default: [2, 4], items: { type: 'integer', minimum: 1, maximum: 12, default: 2 } },
        showLabels: { type: 'boolean', default: true },
        highlightShell: { type: 'integer', minimum: 0, maximum: 4, default: 0 }
      }
    };
  }
}
