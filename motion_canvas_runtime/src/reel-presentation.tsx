import {Circle, Layout, Line, Rect, Txt} from '@motion-canvas/2d';

export const ReelPresentation = {
  font: 'Inter, Arial, sans-serif',
  colors: {
    background: '#07111f', panel: '#10233b', text: '#f7fbff', muted: '#9bb1ca',
    cyan: '#35e2ff', electric: '#6c63ff', amber: '#ffd166', coral: '#ff5d73', green: '#4ee6a8',
  },
  safe: {left: -450, right: 330, top: -800, bottom: 520, captionTop: 540, captionBottom: 740},
} as const;

const bounded = (value: unknown, maximum: number, field: string) => {
  const text = String(value ?? '');
  if (text.length <= maximum) return text;
  return `${text.slice(0, Math.max(1, maximum - 1)).trimEnd()}…`;
};

export function ReelBackground({children}: any) {
  return <Rect width={1080} height={1920} fill={ReelPresentation.colors.background}>
    <Circle x={-380} y={-720} width={520} height={520} fill={'#173b5b55'} />
    <Circle x={310} y={420} width={680} height={680} fill={'#33276b44'} />
    {children}
  </Rect>;
}

export function ReelSafeStage({children, ...placement}: any) {
  return <Layout width={780} height={1320} y={-140} {...placement}>{children}</Layout>;
}

export function HookText({text, children, accent = ReelPresentation.colors.cyan, ...placement}: any) {
  return <Txt text={bounded(text ?? children, 52, 'Hook')} width={780} fontFamily={ReelPresentation.font}
    fontSize={76} lineHeight={88} fontWeight={800} textAlign={'center'} fill={accent} textWrap {...placement} />;
}

export function QuestionPrompt({text, children, ...placement}: any) {
  return <Rect width={780} minHeight={190} padding={34} radius={34} fill={'#10233bee'} stroke={'#35e2ff88'} lineWidth={3} {...placement}>
    <Txt text={bounded(text ?? children, 70, 'Question')} width={700} fontFamily={ReelPresentation.font}
      fontSize={58} lineHeight={68} fontWeight={750} textAlign={'center'} fill={ReelPresentation.colors.text} textWrap />
  </Rect>;
}

export function PredictionChoice({label, active = false, accent, ...placement}: any) {
  const color = accent ?? ReelPresentation.colors.amber;
  return <Rect width={350} height={150} padding={24} radius={28} fill={active ? `${color}2f` : '#10233bee'}
    stroke={active ? color : '#9bb1ca55'} lineWidth={active ? 4 : 2} {...placement}>
    <Txt text={bounded(label, 28, 'Prediction choice')} width={300} fontFamily={ReelPresentation.font}
      fontSize={46} fontWeight={750} textAlign={'center'} fill={active ? color : ReelPresentation.colors.text} textWrap />
  </Rect>;
}

export function ObjectLabel({text, children, accent = ReelPresentation.colors.cyan, ...placement}: any) {
  return <Rect padding={[14, 22]} radius={18} fill={'#07111fcc'} stroke={`${accent}88`} lineWidth={2} {...placement}>
    <Txt text={bounded(text ?? children, 30, 'Object label')} fontFamily={ReelPresentation.font}
      fontSize={46} fontWeight={700} fill={accent} />
  </Rect>;
}

export function EquationFlash({equation, caption, accent = ReelPresentation.colors.amber, ...placement}: any) {
  return <Rect layout direction={'column'} gap={16} width={780} minHeight={190} padding={30} radius={30}
    fill={'#10233bf2'} stroke={`${accent}88`} lineWidth={3} {...placement}>
    <Txt text={bounded(equation, 54, 'Equation')} width={720} fontFamily={ReelPresentation.font}
      fontSize={66} fontWeight={800} textAlign={'center'} fill={accent} />
    {caption ? <Txt text={bounded(caption, 48, 'Equation caption')} width={710} fontFamily={ReelPresentation.font}
      fontSize={44} textAlign={'center'} fill={ReelPresentation.colors.muted} textWrap /> : null}
  </Rect>;
}

export function NumberCounter({value, unit = '', label, accent = ReelPresentation.colors.cyan, ...placement}: any) {
  return <Layout layout direction={'column'} gap={8} {...placement}>
    <Txt text={`${bounded(value, 18, 'Counter value')}${unit ? ` ${bounded(unit, 8, 'Counter unit')}` : ''}`}
      fontFamily={ReelPresentation.font} fontSize={72} fontWeight={850} textAlign={'center'} fill={accent} />
    {label ? <Txt text={bounded(label, 28, 'Counter label')} width={420} fontFamily={ReelPresentation.font}
      fontSize={44} textAlign={'center'} fill={ReelPresentation.colors.muted} textWrap /> : null}
  </Layout>;
}

export function PayoffBanner({text, children, accent = ReelPresentation.colors.green, ...placement}: any) {
  return <Rect width={820} minHeight={190} padding={34} radius={36} fill={`${accent}20`} stroke={accent} lineWidth={4} {...placement}>
    <Txt text={bounded(text ?? children, 72, 'Payoff')} width={740} fontFamily={ReelPresentation.font}
      fontSize={60} lineHeight={70} fontWeight={800} textAlign={'center'} fill={ReelPresentation.colors.text} textWrap />
  </Rect>;
}

export function CaptionGuide({text = 'CAPTION SAFE AREA', ...placement}: any) {
  return <Rect y={640} width={800} height={190} radius={20} stroke={'#9bb1ca44'} lineWidth={2} lineDash={[16, 12]} {...placement}>
    <Txt text={bounded(text, 32, 'Caption guide')} fontFamily={ReelPresentation.font} fontSize={42} fill={'#9bb1ca66'} />
  </Rect>;
}

export function BrandMark({text = 'MAV PHYSICS', ...placement}: any) {
  return <Txt text={bounded(text, 20, 'Brand mark')} x={-345} y={-860} fontFamily={ReelPresentation.font}
    fontSize={34} fontWeight={800} fill={'#f7fbff88'} {...placement} />;
}

export function ProgressPulse({progress = 0, accent = ReelPresentation.colors.cyan, ...placement}: any) {
  const resolvedProgress = () => {
    const value = typeof progress === 'function' ? progress() : progress;
    return Math.max(0, Math.min(1, Number(value)));
  };
  return <Layout y={820} width={760} height={16} {...placement}>
    <Line points={[[-380, 0], [380, 0]]} lineWidth={10} stroke={'#9bb1ca33'} lineCap={'round'} />
    <Line points={() => [[-380, 0], [-380 + 760 * resolvedProgress(), 0]]}
      lineWidth={10} stroke={accent} lineCap={'round'} />
  </Layout>;
}
