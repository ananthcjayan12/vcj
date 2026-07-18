export type RenderProfileName = 'lesson_landscape' | 'reel_portrait';

export interface RenderProfile {
  name: RenderProfileName;
  width: number;
  height: number;
  fps: number;
  background: string;
}

export const RENDER_PROFILES: Record<RenderProfileName, RenderProfile> = {
  lesson_landscape: {name: 'lesson_landscape', width: 1920, height: 1080, fps: 30, background: '#07111f'},
  reel_portrait: {name: 'reel_portrait', width: 1080, height: 1920, fps: 30, background: '#07111f'},
};

export function resolveRenderProfile(value?: Partial<RenderProfile> & {name?: string}): RenderProfile {
  const name: RenderProfileName = value?.name === 'reel_portrait' ? 'reel_portrait' : 'lesson_landscape';
  const base = RENDER_PROFILES[name];
  return {
    ...base,
    width: Number(value?.width || base.width),
    height: Number(value?.height || base.height),
    fps: Number(value?.fps || base.fps),
    background: String(value?.background || base.background),
  };
}
