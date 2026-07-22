import {Latex, Layout, Rect, Txt} from '@motion-canvas/2d';
import {KineticLayout, KineticRect} from './choreography';
export {KineticActor} from './choreography';

export const Presentation = {
  font: 'Inter, Arial, sans-serif',
  title: 52,
  heading: 38,
  body: 31,
  label: 28,
  safeWidth: 1720,
  safeHeight: 880,
  colors: {panel: '#0e1d31', text: '#eaf3ff', muted: '#91a8c5', cyan: '#46d9ff', amber: '#ffc857'},
} as const;

export interface TextItem {title: string; body?: string; accent?: string}
export interface TableColumn {id: string; title: string; width?: number}
export interface TableRow {label: string; values: string[]}

type PresentationVariant = 'default' | 'compact';

const variantValue = <T,>(variant: PresentationVariant | undefined, normal: T, compact: T) =>
  variant === 'compact' ? compact : normal;

const bounded = (value: string, maximum: number, field: string) => {
  if (value.length > maximum) throw new Error(`${field} exceeds ${maximum} characters`);
  return value;
};
const display = (value: any, maximum: number, field: string) => typeof value === 'string' ? bounded(value, maximum, field) : value;
const isLatexEquation = (value: unknown) =>
  typeof value === 'string' && /\\[A-Za-z]+|[_^]\{?|\\[()[\]]/.test(value);

export function SceneTitle(props: any) {
  const {text, title, subtitle, children, ...placement} = props;
  const primary = text ?? title ?? children ?? '';
  return <KineticLayout kinetic={{role: 'title', priority: 1000, canShift: false, canScale: false, canFade: false}} layout direction={'column'} gap={12} width={1500} {...placement}>
    <Txt text={display(primary, 64, 'Scene title')} width={1500} fontFamily={Presentation.font} fontSize={Presentation.title} fontWeight={700} textAlign={'center'} fill={Presentation.colors.text} />
    {subtitle ? <Txt text={display(subtitle, 72, 'Scene subtitle')} width={1500} fontFamily={Presentation.font} fontSize={Presentation.label} textAlign={'center'} fill={Presentation.colors.muted} textWrap /> : null}
  </KineticLayout>;
}

export function TextCard(props: any) {
  const {item, title, body, children, accent, variant = 'default', width, height, ...placement} = props;
  const cardWidth = width ?? variantValue(variant, 720, 500);
  const cardHeight = height ?? variantValue(variant, 260, 140);
  const padding = variantValue(variant, 32, 20);
  const gap = variantValue(variant, 22, 10);
  const titleSize = variantValue(variant, Presentation.heading, 30);
  const bodySize = variantValue(variant, Presentation.body, 24);
  const bodyLineHeight = variantValue(variant, 42, 30);
  const resolved = item ?? {title: title ?? '', body: body ?? children ?? '', accent};
  const cardTitle = display(resolved.title, 42, 'Card title');
  const cardBody = resolved.body ? display(resolved.body, 110, 'Card body') : '';
  return <KineticRect kinetic={{role: 'supporting', priority: 640, maxShift: 260, minScale: 0.94, canFade: true}} layout direction={'column'} gap={gap} padding={padding} width={cardWidth} height={cardHeight} radius={18} fill={Presentation.colors.panel} {...placement}>
    <Txt text={cardTitle} width={cardWidth - padding * 2} fontFamily={Presentation.font} fontSize={titleSize} fontWeight={700} fill={resolved.accent ?? Presentation.colors.cyan} textWrap />
    {cardBody ? <Txt text={cardBody} width={cardWidth - padding * 2} fontFamily={Presentation.font} fontSize={bodySize} lineHeight={bodyLineHeight} fill={Presentation.colors.text} textWrap /> : null}
  </KineticRect>;
}

export function TwoColumnComparison({left, right}: {left: TextItem; right: TextItem}) {
  return <KineticLayout kinetic={{role: 'comparison', priority: 850, maxShift: 90, minScale: 0.96, canFade: false}} layout direction={'row'} gap={48} width={Presentation.safeWidth} height={620}>
    <TextCard item={left} width={836} height={620} />
    <TextCard item={right} width={836} height={620} />
  </KineticLayout>;
}

export function ComparisonTable(props: any) {
  const {title, columns: rawColumns, rows: rawRows, ...placement} = props;
  const arrayRows = (rawRows ?? []).every((row: any) => Array.isArray(row));
  const columns: TableColumn[] = (rawColumns ?? []).map((column: any, index: number) => typeof column === 'string' ? {id: `column_${index}`, title: column} : column);
  const rows: TableRow[] = arrayRows
    ? (rawRows ?? []).map((row: string[], index: number) => ({label: String(index + 1), values: row}))
    : rawRows ?? [];
  if (columns.length < 2 || columns.length > 3) throw new Error('ComparisonTable requires 2-3 columns');
  if (rows.length < 1 || rows.length > 4) throw new Error('ComparisonTable supports 1-4 visible rows');
  const labelWidth = arrayRows ? 0 : 340;
  const valueWidth = (Presentation.safeWidth - labelWidth) / columns.length;
  return <KineticLayout kinetic={{role: 'comparison', priority: 850, maxShift: 90, minScale: 0.96, canFade: false}} layout direction={'column'} width={Presentation.safeWidth} gap={3} {...placement}>
    {title ? <Txt text={display(title, 54, 'Table title')} width={Presentation.safeWidth} height={70} fontFamily={Presentation.font} fontSize={Presentation.heading} fontWeight={700} textAlign={'center'} fill={Presentation.colors.text} /> : null}
    <Layout layout direction={'row'} gap={3} height={96}>
      {!arrayRows ? <Rect width={labelWidth} height={96} fill={Presentation.colors.panel} /> : null}
      {columns.map(column => <Rect key={column.id} width={valueWidth} height={96} padding={22} fill={Presentation.colors.panel}>
        <Txt text={bounded(column.title, 28, 'Table heading')} width={valueWidth - 44} fontFamily={Presentation.font} fontSize={Presentation.heading} fontWeight={700} textAlign={'center'} fill={Presentation.colors.cyan} textWrap />
      </Rect>)}
    </Layout>
    {rows.map((row, rowIndex) => <Layout key={`row-${rowIndex}`} layout direction={'row'} gap={3} height={132}>
      {!arrayRows ? <Rect width={labelWidth} height={132} padding={24} fill={Presentation.colors.panel}>
        <Txt text={bounded(row.label, 32, 'Row label')} width={labelWidth - 48} fontFamily={Presentation.font} fontSize={Presentation.body} fontWeight={650} fill={Presentation.colors.amber} textWrap />
      </Rect> : null}
      {columns.map((column, columnIndex) => <Rect key={`${rowIndex}-${column.id}`} width={valueWidth} height={132} padding={24} fill={Presentation.colors.panel}>
        <Txt text={bounded(row.values[columnIndex] ?? '', 48, 'Table cell')} width={valueWidth - 48} fontFamily={Presentation.font} fontSize={Presentation.body} lineHeight={39} textAlign={'center'} fill={Presentation.colors.text} textWrap />
      </Rect>)}
    </Layout>)}
  </KineticLayout>;
}

export function EquationCard(props: any) {
  const {equation, caption, description, title, variant = 'default', width, height, ...placement} = props;
  const cardWidth = width ?? variantValue(variant, 900, 500);
  const cardHeight = height ?? variantValue(variant, 220, 140);
  const padding = variantValue(variant, 32, 20);
  const gap = variantValue(variant, 22, 10);
  const equationSize = variantValue(variant, 46, 34);
  const noteSize = variantValue(variant, Presentation.label, 23);
  const note = caption ?? description ?? title;
  const equationValue = display(equation, 120, 'Equation');
  return <KineticRect kinetic={{role: 'equation', priority: 720, maxShift: 240, minScale: 0.94, canFade: true}} layout direction={'column'} gap={gap} padding={padding} width={cardWidth} height={cardHeight} radius={18} fill={Presentation.colors.panel} {...placement}>
    {isLatexEquation(equationValue)
      ? <Latex tex={equationValue} fontSize={equationSize} fill={Presentation.colors.amber} />
      : <Txt text={equationValue} width={cardWidth - padding * 2} fontFamily={Presentation.font} fontSize={equationSize} fontWeight={700} textAlign={'center'} fill={Presentation.colors.amber} />}
    {note ? <Txt text={display(note, 72, 'Equation caption')} width={cardWidth - padding * 2} fontFamily={Presentation.font} fontSize={noteSize} textAlign={'center'} fill={Presentation.colors.muted} textWrap /> : null}
  </KineticRect>;
}

export function StatReadout(props: any) {
  const {value, unit = '', label, children, variant = 'default', width, height, ...placement} = props;
  const cardWidth = width ?? variantValue(variant, 440, 360);
  const cardHeight = height ?? variantValue(variant, 210, 140);
  const padding = variantValue(variant, 28, 20);
  const valueSize = variantValue(variant, 46, 34);
  const labelSize = variantValue(variant, Presentation.label, 23);
  const resolvedValue = value ?? children ?? '';
  const combined = typeof resolvedValue === 'string' ? `${bounded(resolvedValue, 32, 'Value')}${unit ? ` ${bounded(unit, 12, 'Unit')}` : ''}` : resolvedValue;
  return <KineticRect kinetic={{role: 'readout', priority: 760, maxShift: 220, minScale: 0.94, canFade: true}} layout direction={'column'} gap={variantValue(variant, 14, 8)} padding={padding} width={cardWidth} height={cardHeight} radius={18} fill={Presentation.colors.panel} {...placement}>
    <Txt text={combined} width={cardWidth - padding * 2} fontFamily={Presentation.font} fontSize={valueSize} fontWeight={700} textAlign={'center'} fill={Presentation.colors.cyan} />
    <Txt text={display(label, 42, 'Readout label')} width={cardWidth - padding * 2} fontFamily={Presentation.font} fontSize={labelSize} textAlign={'center'} fill={Presentation.colors.muted} textWrap />
  </KineticRect>;
}
