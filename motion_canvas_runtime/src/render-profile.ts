export interface RenderProfile {
  id: 'lesson_landscape' | 'short_portrait' | 'square_social';
  width: number;
  height: number;
  fps: number;
  background: string;
}

export const RENDER_PROFILES: Record<RenderProfile['id'], RenderProfile> = {
  lesson_landscape: {id: 'lesson_landscape', width: 1920, height: 1080, fps: 30, background: '#07111f'},
  short_portrait: {id: 'short_portrait', width: 1080, height: 1920, fps: 30, background: '#07111f'},
  square_social: {id: 'square_social', width: 1080, height: 1080, fps: 30, background: '#07111f'},
};

export function activeRenderProfile(): RenderProfile {
  const query = new URLSearchParams(window.location.search);
  const id = query.get('profile') as RenderProfile['id'] | null;
  const base = RENDER_PROFILES[id || 'lesson_landscape'] || RENDER_PROFILES.lesson_landscape;
  const number = (key: string, fallback: number) => {
    const value = Number(query.get(key));
    return Number.isFinite(value) && value > 0 ? value : fallback;
  };
  return {...base, width: number('width', base.width), height: number('height', base.height), fps: number('fps', base.fps)};
}
