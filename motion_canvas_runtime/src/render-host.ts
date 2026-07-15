import {PlaybackState, Stage} from '@motion-canvas/core/lib/app';
import {PlaybackManager} from '@motion-canvas/core/lib/app/PlaybackManager';
import {PlaybackStatus} from '@motion-canvas/core/lib/app/PlaybackStatus';
import {SharedWebGLContext} from '@motion-canvas/core/lib/app/SharedWebGLContext';
import {ReadOnlyTimeEvents} from '@motion-canvas/core/lib/scenes/timeEvents';
import {Vector2} from '@motion-canvas/core';
import project from './project';

const FPS = 30; const SIZE = new Vector2(1920, 1080); const playback = new PlaybackManager();
const status = new PlaybackStatus(playback); const logger = project.logger!; const sharedWebGLContext = new SharedWebGLContext(logger);
const scenes = project.scenes.map(description => new description.klass({...description, meta: description.meta.clone(), logger, playback: status, size: SIZE, resolutionScale: 1, timeEventsClass: ReadOnlyTimeEvents, sharedWebGLContext, experimentalFeatures: project.experimentalFeatures}));
playback.setup(scenes); playback.fps = FPS; playback.state = PlaybackState.Rendering;
const stage = new Stage(); stage.configure({size: SIZE, resolutionScale: 1, background: '#07111f'}); stage.finalBuffer.id = 'robot-canvas'; document.body.append(stage.finalBuffer);
let initialized = false;
async function initialize() {if (initialized) return; await playback.recalculate(); await playback.reset(); initialized = true;}
async function seek(timeSeconds: number) {await initialize(); const frame = Math.max(0, Math.min(playback.duration, Math.round(timeSeconds * FPS))); await playback.reset(); await playback.seek(frame); await stage.render(playback.currentScene, playback.previousScene); return {frame, durationFrames: playback.duration};}
declare global {interface Window {MotionCanvasRobot: {readonly fps: number; readonly duration: () => number; readonly seek: typeof seek}; __motionCanvasRobotReady: boolean;}}
window.MotionCanvasRobot = {fps: FPS, duration: () => playback.duration / FPS, seek}; await initialize(); await seek(0); window.__motionCanvasRobotReady = true;
