import {Layout, Node, Rect, Txt} from '@motion-canvas/2d';
import {createSignal, PossibleColor, SignalValue, SimpleSignal} from '@motion-canvas/core';

export const SHORT_SAFE_WIDTH = 940;
export const SHORT_CONTENT_HEIGHT = 1510;
export const SHORT_WIDTH = 1080;
export const SHORT_HEIGHT = 1920;

type TextLike = SignalValue<string> | SimpleSignal<string, void> | string;
type NumberLike = SignalValue<number> | SimpleSignal<number, void> | number;

function asText(value: TextLike | undefined, fallback = ''): any {
  return value ?? fallback;
}

export function ShortHook(props: {
  text?: TextLike;
  title?: TextLike;
  children?: any;
  color?: PossibleColor;
  fontSize?: number;
  y?: number;
  x?: number;
  opacity?: NumberLike;
  width?: number;
}) {
  const label = props.text ?? props.title;
  if (props.children != null) {
    return (
      <Layout y={props.y} x={props.x} opacity={props.opacity as any} width={props.width ?? SHORT_SAFE_WIDTH} layout direction={'column'} alignItems={'center'}>
        {props.children}
      </Layout>
    );
  }
  return (
    <Txt
      text={asText(label)}
      y={props.y}
      x={props.x}
      opacity={props.opacity as any}
      width={props.width ?? SHORT_SAFE_WIDTH}
      fontSize={props.fontSize ?? 72}
      fontWeight={800}
      fill={props.color ?? '#ffffff'}
      textAlign={'center'}
      textWrap
    />
  );
}

export function ShortTitle(props: {
  text?: TextLike;
  title?: TextLike;
  children?: any;
  fontSize?: number;
  y?: number;
  x?: number;
  opacity?: NumberLike;
  width?: number;
}) {
  const label = props.text ?? props.title;
  if (props.children != null) {
    return <Layout y={props.y} x={props.x} opacity={props.opacity as any}>{props.children}</Layout>;
  }
  return (
    <Txt
      text={asText(label)}
      y={props.y}
      x={props.x}
      opacity={props.opacity as any}
      width={props.width ?? SHORT_SAFE_WIDTH}
      fontSize={props.fontSize ?? 60}
      fontWeight={700}
      fill={'#ffffff'}
      textAlign={'center'}
      textWrap
    />
  );
}

export function ShortSubtitle(props: {
  text?: TextLike;
  subtitle?: TextLike;
  children?: any;
  fontSize?: number;
  y?: number;
  x?: number;
  opacity?: NumberLike;
  width?: number;
}) {
  const label = props.text ?? props.subtitle;
  if (props.children != null) {
    return <Layout y={props.y} x={props.x} opacity={props.opacity as any}>{props.children}</Layout>;
  }
  return (
    <Txt
      text={asText(label)}
      y={props.y}
      x={props.x}
      opacity={props.opacity as any}
      width={props.width ?? SHORT_SAFE_WIDTH}
      fontSize={props.fontSize ?? 42}
      fill={'#c9d7eb'}
      textAlign={'center'}
      textWrap
    />
  );
}

export function PortraitTextCard(props: {
  text?: TextLike;
  title?: TextLike;
  body?: TextLike;
  children?: any;
  fontSize?: number;
  y?: number;
  x?: number;
  opacity?: NumberLike;
  width?: number;
}) {
  if (props.children != null) {
    return (
      <Rect y={props.y} x={props.x} opacity={props.opacity as any} width={props.width ?? 940} padding={48} radius={36} fill={'#10243d'} layout direction={'column'} gap={18}>
        {props.children}
      </Rect>
    );
  }
  const heading = props.title;
  const body = props.text ?? props.body ?? '';
  return (
    <Rect y={props.y} x={props.x} opacity={props.opacity as any} width={props.width ?? 940} padding={48} radius={36} fill={'#10243d'} layout direction={'column'} gap={18}>
      {heading != null ? <Txt text={asText(heading)} width={844} fontSize={36} fontWeight={800} fill={'#67e8f9'} textWrap /> : null}
      <Txt text={asText(body)} width={844} fontSize={props.fontSize ?? 44} fill={'#ffffff'} textWrap />
    </Rect>
  );
}

export function PortraitEquationCard(props: {
  equation?: TextLike;
  title?: TextLike;
  caption?: TextLike;
  text?: TextLike;
  children?: any;
  fontSize?: number;
  y?: number;
  x?: number;
  opacity?: NumberLike;
  width?: number;
}) {
  if (props.children != null) {
    return (
      <Rect y={props.y} x={props.x} opacity={props.opacity as any} width={props.width ?? 940} padding={40} radius={36} fill={'#10243d'} layout direction={'column'} gap={14} alignItems={'center'}>
        {props.children}
      </Rect>
    );
  }
  const equation = props.equation ?? props.text ?? '';
  return (
    <Rect y={props.y} x={props.x} opacity={props.opacity as any} width={props.width ?? 900} padding={40} radius={36} fill={'#10243d'} layout direction={'column'} gap={14} alignItems={'center'}>
      {props.title != null ? <Txt text={asText(props.title)} width={820} fontSize={34} fontWeight={800} fill={'#9fb4d0'} textAlign={'center'} textWrap /> : null}
      <Txt text={asText(equation)} width={820} fontSize={props.fontSize ?? 56} fontWeight={800} fill={'#67e8f9'} textAlign={'center'} textWrap />
      {props.caption != null ? <Txt text={asText(props.caption)} width={820} fontSize={34} fill={'#d7e4f5'} textAlign={'center'} textWrap /> : null}
    </Rect>
  );
}

export function PortraitStatReadout(props: {
  label?: TextLike;
  value?: TextLike;
  children?: any;
  y?: number;
  x?: number;
  opacity?: NumberLike;
}) {
  if (props.children != null) {
    return <Layout y={props.y} x={props.x} opacity={props.opacity as any} direction={'column'} alignItems={'center'}>{props.children}</Layout>;
  }
  return (
    <Layout y={props.y} x={props.x} opacity={props.opacity as any} direction={'column'} alignItems={'center'} gap={8}>
      <Txt text={asText(props.value)} fontSize={84} fill={'#67e8f9'} />
      <Txt text={asText(props.label)} fontSize={40} fill={'#ffffff'} />
    </Layout>
  );
}

export function CaptionSafeArea(props: {
  text?: TextLike;
  children?: any;
  y?: number;
  x?: number;
  opacity?: NumberLike;
  width?: number;
}) {
  if (props.children != null) {
    return (
      <Layout y={props.y ?? 810} x={props.x} opacity={props.opacity as any} width={props.width ?? 960} layout direction={'column'} alignItems={'center'}>
        {props.children}
      </Layout>
    );
  }
  return (
    <Rect y={props.y ?? 745} x={props.x} opacity={props.opacity as any} width={props.width ?? 940} minHeight={120} padding={24} radius={28} fill={'#07111fcc'}>
      <Txt text={asText(props.text)} width={880} fontSize={52} fill={'#ffffff'} textAlign={'center'} textWrap />
    </Rect>
  );
}

export function DiagramStage(props: {
  children?: any;
  y?: number;
  x?: number;
  width?: number;
  height?: number;
  opacity?: NumberLike;
}) {
  return (
    <Layout
      y={props.y}
      x={props.x}
      opacity={props.opacity as any}
      width={props.width ?? SHORT_SAFE_WIDTH}
      height={props.height ?? 1100}
      layout={false}
    >
      {props.children}
    </Layout>
  );
}

export function VerticalComparison(props: {children?: any; y?: number; x?: number; gap?: number; opacity?: NumberLike}) {
  return (
    <Layout y={props.y} x={props.x} opacity={props.opacity as any} direction={'column'} gap={props.gap ?? 28} alignItems={'center'}>
      {props.children}
    </Layout>
  );
}

export function VerticalCardStack(props: {children?: any; y?: number; x?: number; gap?: number; opacity?: NumberLike}) {
  return (
    <Layout y={props.y} x={props.x} opacity={props.opacity as any} direction={'column'} gap={props.gap ?? 24} alignItems={'center'}>
      {props.children}
    </Layout>
  );
}

export function ExamTrapBadge(props: {text?: TextLike; children?: any; y?: number; x?: number; opacity?: NumberLike}) {
  if (props.children != null) {
    return <Layout y={props.y} x={props.x} opacity={props.opacity as any}>{props.children}</Layout>;
  }
  return (
    <Rect y={props.y} x={props.x} opacity={props.opacity as any} padding={[16, 28]} radius={999} fill={'#3b1d2a'} stroke={'#ff6b6b'} lineWidth={3}>
      <Txt text={asText(props.text, 'EXAM TRAP')} fontSize={34} fontWeight={800} fill={'#ffb4b4'} />
    </Rect>
  );
}

export function PredictionPrompt(props: {text?: TextLike; title?: TextLike; children?: any; y?: number; x?: number; opacity?: NumberLike}) {
  return <PortraitTextCard y={props.y} x={props.x} opacity={props.opacity} title={props.title ?? 'PREDICT'} text={props.text} children={props.children} />;
}

export function AnswerReveal(props: {text?: TextLike; title?: TextLike; children?: any; y?: number; x?: number; opacity?: NumberLike}) {
  return <PortraitTextCard y={props.y} x={props.x} opacity={props.opacity} title={props.title ?? 'ANSWER'} text={props.text} children={props.children} />;
}

export function ProgressBar(props: {
  progress?: NumberLike;
  width?: number;
  height?: number;
  y?: number;
  x?: number;
  accent?: PossibleColor;
  track?: PossibleColor;
  opacity?: NumberLike;
  children?: any;
}) {
  if (props.children != null) {
    return <Layout y={props.y} x={props.x} opacity={props.opacity as any}>{props.children}</Layout>;
  }
  const width = props.width ?? 960;
  const height = props.height ?? 14;
  const progress = props.progress ?? 0;
  return (
    <Layout y={props.y} x={props.x} opacity={props.opacity as any} width={width} height={height} layout={false}>
      <Rect width={width} height={height} radius={999} fill={props.track ?? '#1a2b3f'} />
      <Rect
        offset={[-1, 0]}
        x={-width / 2}
        width={() => width * Math.max(0, Math.min(1, typeof progress === 'function' ? Number((progress as any)()) : Number(progress)))}
        height={height}
        radius={999}
        fill={props.accent ?? '#46d9ff'}
      />
    </Layout>
  );
}

// Keep Node import referenced for TSX tooling that expects scene graph types nearby.
void Node;
void createSignal;
