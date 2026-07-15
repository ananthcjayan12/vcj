import {Layout, Rect, Txt} from '@motion-canvas/2d';

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

const bounded = (value: string, maximum: number, field: string) => {
  if (value.length > maximum) throw new Error(`${field} exceeds ${maximum} characters`);
  return value;
};
const display = (value: any, maximum: number, field: string) => typeof value === 'string' ? bounded(value, maximum, field) : value;

export function SceneTitle(props: any) {
  const {text, title, subtitle, children, ...placement} = props;
  const primary = text ?? title ?? children ?? '';
  return <Layout layout direction={'column'} gap={12} width={1500} {...placement}>
    <Txt text={display(primary, 64, 'Scene title')} width={1500} fontFamily={Presentation.font} fontSize={Presentation.title} fontWeight={700} textAlign={'center'} fill={Presentation.colors.text} />
    {subtitle ? <Txt text={display(subtitle, 72, 'Scene subtitle')} width={1500} fontFamily={Presentation.font} fontSize={Presentation.label} textAlign={'center'} fill={Presentation.colors.muted} textWrap /> : null}
  </Layout>;
}

export function TextCard(props: any) {
  const {item, title, body, children, accent, width = 720, height = 260, ...placement} = props;
  const resolved = item ?? {title: title ?? '', body: body ?? children ?? '', accent};
  const cardTitle = display(resolved.title, 42, 'Card title');
  const cardBody = resolved.body ? display(resolved.body, 110, 'Card body') : '';
  return <Rect layout direction={'column'} gap={22} padding={32} width={width} height={height} radius={18} fill={Presentation.colors.panel} {...placement}>
    <Txt text={cardTitle} width={width - 64} fontFamily={Presentation.font} fontSize={Presentation.heading} fontWeight={700} fill={resolved.accent ?? Presentation.colors.cyan} textWrap />
    {cardBody ? <Txt text={cardBody} width={width - 64} fontFamily={Presentation.font} fontSize={Presentation.body} lineHeight={42} fill={Presentation.colors.text} textWrap /> : null}
  </Rect>;
}

export function TwoColumnComparison({left, right}: {left: TextItem; right: TextItem}) {
  return <Layout layout direction={'row'} gap={48} width={Presentation.safeWidth} height={620}>
    <TextCard item={left} width={836} height={620} />
    <TextCard item={right} width={836} height={620} />
  </Layout>;
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
  return <Layout layout direction={'column'} width={Presentation.safeWidth} gap={3} {...placement}>
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
  </Layout>;
}

export function EquationCard(props: any) {
  const {equation, caption, description, title, ...placement} = props;
  const note = caption ?? description ?? title;
  return <Rect layout direction={'column'} gap={22} padding={32} width={900} height={220} radius={18} fill={Presentation.colors.panel} {...placement}>
    <Txt text={display(equation, 58, 'Equation')} width={836} fontFamily={Presentation.font} fontSize={46} fontWeight={700} textAlign={'center'} fill={Presentation.colors.amber} />
    {note ? <Txt text={display(note, 72, 'Equation caption')} width={836} fontFamily={Presentation.font} fontSize={Presentation.label} textAlign={'center'} fill={Presentation.colors.muted} textWrap /> : null}
  </Rect>;
}

export function StatReadout(props: any) {
  const {value, unit = '', label, children, ...placement} = props;
  const resolvedValue = value ?? children ?? '';
  const combined = typeof resolvedValue === 'string' ? `${bounded(resolvedValue, 32, 'Value')}${unit ? ` ${bounded(unit, 12, 'Unit')}` : ''}` : resolvedValue;
  return <Rect layout direction={'column'} gap={14} padding={28} width={440} height={210} radius={18} fill={Presentation.colors.panel} {...placement}>
    <Txt text={combined} width={384} fontFamily={Presentation.font} fontSize={46} fontWeight={700} textAlign={'center'} fill={Presentation.colors.cyan} />
    <Txt text={display(label, 42, 'Readout label')} width={384} fontFamily={Presentation.font} fontSize={Presentation.label} textAlign={'center'} fill={Presentation.colors.muted} textWrap />
  </Rect>;
}
