import {makeProject} from '@motion-canvas/core';
import {scenes} from './generated/scenes';

export default makeProject({scenes, audio: '/voiceover.mp3'});
