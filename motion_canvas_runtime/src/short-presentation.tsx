import {Layout, Rect, Txt} from '@motion-canvas/2d';
import {PossibleColor} from '@motion-canvas/core';

export const SHORT_SAFE_WIDTH = 940;
export const SHORT_CONTENT_HEIGHT = 1510;

export function ShortHook(props: {text: string; color?: PossibleColor}) {
  return <Txt text={props.text} width={SHORT_SAFE_WIDTH} fontSize={72} fontWeight={800} fill={props.color ?? '#ffffff'} textAlign={'center'} textWrap />;
}
export function ShortTitle(props: {text: string}) { return <Txt text={props.text} width={SHORT_SAFE_WIDTH} fontSize={60} fontWeight={700} fill={'#ffffff'} textAlign={'center'} />; }
export function ShortSubtitle(props: {text: string}) { return <Txt text={props.text} width={SHORT_SAFE_WIDTH} fontSize={42} fill={'#c9d7eb'} textAlign={'center'} textWrap />; }
export function PortraitTextCard(props: {text: string}) { return <Rect width={940} padding={48} radius={36} fill={'#10243d'}><Txt text={props.text} width={844} fontSize={44} fill={'#ffffff'} textWrap /></Rect>; }
export function PortraitEquationCard(props: {equation: string}) { return <Rect width={940} padding={54} radius={36} fill={'#10243d'}><Txt text={props.equation} fontSize={64} fill={'#67e8f9'} /></Rect>; }
export function PortraitStatReadout(props: {label: string; value: string}) { return <Layout direction={'column'} alignItems={'center'}><Txt text={props.value} fontSize={84} fill={'#67e8f9'} /><Txt text={props.label} fontSize={40} fill={'#ffffff'} /></Layout>; }
export function CaptionSafeArea(props: {text: string}) { return <Rect y={745} width={940} minHeight={120} padding={24} radius={28} fill={'#07111fcc'}><Txt text={props.text} width={880} fontSize={52} fill={'#ffffff'} textAlign={'center'} textWrap /></Rect>; }
export const VerticalComparison = Layout;
export const VerticalCardStack = Layout;
export const DiagramStage = Layout;
export const ExamTrapBadge = Rect;
export const PredictionPrompt = PortraitTextCard;
export const AnswerReveal = PortraitTextCard;
export const ProgressBar = Rect;
