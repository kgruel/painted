/**
 * PaintedSurface.jsx — the painted brand hero island.
 *
 * ┌─ LANING ─────────────────────────────────────────────────────────────────┐
 * │ This is a COSMETIC, brand/landing recreation of painted's terminal look.   │
 * │ It is hand-built React + CSS that *imitates* painted's rendered output for  │
 * │ marketing/illustration. It is NOT painted and does NOT render real painted  │
 * │ output. The numbers, services, logs and palettes are decorative sample      │
 * │ data. Anywhere the real product output is needed, render it with painted    │
 * │ itself (the library's cells→HTML path) — never with this file.              │
 * └────────────────────────────────────────────────────────────────────────────┘
 *
 * A self-contained interactive "system-monitor Surface": title bar, view rail,
 * main view, footer. Keyboard- and click-driven. Built as ONE React island with
 * a clean boundary — no Babel-standalone, no window globals, no load-order
 * coupling. Compile it with your own JSX toolchain (Astro/Vite/etc.).
 *
 * DEPENDENCIES (explicit):
 *   - react >= 18 (peer; uses hooks only — useState/useEffect/useRef).
 *     The default React import works under the classic JSX runtime. If your
 *     build uses the automatic runtime you can drop the React import.
 *   - A monospace webface. Tokens default to the JetBrains Mono stack (see
 *     PAINTED_THEME.'--font-mono'); load the actual font in the host (see
 *     fonts/README.md). Without it, falls back to the system mono — still legible.
 *   - NO stylesheet is required: the component injects its own design tokens as
 *     inline CSS custom properties (PAINTED_THEME) on its root. To inherit tokens
 *     from a global colors_and_type.css instead, pass `theme={null}`.
 *
 * ENTRY COMPONENT:  export default function PaintedSurface(props)
 *
 * PROPS (all optional):
 *   initialView    number|string   Starting view: index 0–4 or one of
 *                                   'Status'|'Charts'|'Tree'|'Carnival'|'Logs'. Default 0.
 *   initialPalette 'default'|'nord'|'mono'  Starting palette. Default 'default'.
 *   keyboardNav    boolean         Bind ↑↓/j k, 1–5, ←→ keys. SCOPED to the
 *                                   component root (it is focusable) — never to
 *                                   window — so it won't hijack host page keys.
 *                                   Default true.
 *   autoFocus      boolean         Focus the root on mount (enables keys without
 *                                   a click). Default false — polite for a hero.
 *   data           object          Override sample data: { services, regions,
 *                                   fileTree, logs }. Any omitted key uses the default.
 *   theme          object|null     CSS custom-property map applied to the root.
 *                                   Default PAINTED_THEME (self-contained). Pass
 *                                   null to inherit from an external stylesheet,
 *                                   or a partial object to override specific tokens.
 *   className      string          Extra class on the root.
 *   style          object          Inline style merged onto the root (e.g. height).
 *
 * Named export: PAINTED_THEME — the token map (mirrors colors_and_type.css).
 */

import React from 'react';

const { useState, useEffect, useRef } = React;

/* ── Design tokens (mirror of colors_and_type.css; ANSI-derived theme) ─────── */
export const PAINTED_THEME = {
  '--ink': '#0c0e16',
  '--panel': '#151823',
  '--overlay': '#1e2230',
  '--line': '#2b3142',
  '--line-bold': '#3b4258',
  '--fg': '#f4f2ea',
  '--fg-2': '#c3c7d1',
  '--fg-dim': '#79808f',
  '--red': '#ff5b6a',
  '--green': '#4fdc82',
  '--yellow': '#f5cf52',
  '--blue': '#5aa7ff',
  '--magenta': '#ff74c8',
  '--cyan': '#44e0e0',
  '--orange': '#ff9d4d',
  '--font-mono': "'JetBrains Mono', ui-monospace, 'SF Mono', 'Cascadia Code', 'Fira Code', Menlo, Consolas, monospace",
};

/* palette role / hue name → CSS var reference */
const PT = {
  fg: 'var(--fg)', fg2: 'var(--fg-2)', dim: 'var(--fg-dim)', muted: 'var(--fg-dim)',
  success: 'var(--green)', warning: 'var(--yellow)', error: 'var(--red)', accent: 'var(--cyan)',
  cyan: 'var(--cyan)', green: 'var(--green)', yellow: 'var(--yellow)', red: 'var(--red)',
  blue: 'var(--blue)', magenta: 'var(--magenta)', orange: 'var(--orange)', white: 'var(--fg)',
  ink: 'var(--ink)', panel: 'var(--panel)', overlay: 'var(--overlay)',
  line: 'var(--line)', lineBold: 'var(--line-bold)',
};

/* ── Primitives — Cell → Span/Line → Block, composed by functions ─────────── */
function S({ fg, bold, dim, italic, underline, reverse, children, style }) {
  const st = { ...(style || {}) };
  if (reverse) { st.color = 'var(--ink)'; st.background = fg ? PT[fg] : PT.accent; st.padding = '0 1px'; }
  else if (fg) { st.color = PT[fg] || fg; }
  if (bold) st.fontWeight = 700;
  if (dim) st.opacity = 0.6;
  if (italic) st.fontStyle = 'italic';
  if (underline) st.textDecoration = 'underline';
  return <span style={st}>{children}</span>;
}

function Row({ gap = 1, align = 'center', wrap, children, style }) {
  return <div style={{ display: 'flex', gap: `${gap * 4}px`, alignItems: align, flexWrap: wrap ? 'wrap' : 'nowrap', ...style }}>{children}</div>;
}
function Col({ gap = 1, children, style }) {
  return <div style={{ display: 'flex', flexDirection: 'column', gap: `${gap * 4}px`, minHeight: 0, ...style }}>{children}</div>;
}

function Panel({ title, accent = 'accent', focused, right, children, style, bodyStyle, flex }) {
  return (
    <div style={{ border: `1px solid ${focused ? PT.lineBold : PT.line}`, background: PT.panel, display: 'flex', flexDirection: 'column', flex, minHeight: 0, minWidth: 0, ...style }}>
      {title !== undefined && (
        <div style={{ borderBottom: `1px solid ${focused ? PT.lineBold : PT.line}`, padding: '6px 12px', display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 700, color: PT[accent], letterSpacing: '.02em', flexShrink: 0 }}>
          <span aria-hidden style={{ color: PT[accent] }}>▌</span>
          <span style={{ flex: 1 }}>{title}</span>
          {right && <span style={{ color: PT.dim, fontWeight: 400, fontSize: 12 }}>{right}</span>}
        </div>
      )}
      <div style={{ padding: '12px 14px', flex: 1, minHeight: 0, minWidth: 0, ...bodyStyle }}>{children}</div>
    </div>
  );
}

function KeyHint({ k, label }) {
  return <span style={{ whiteSpace: 'nowrap' }}><S fg="accent" bold>{k}</S>{label && <S fg="dim"> {label}</S>}</span>;
}

/* ── Widgets ──────────────────────────────────────────────────────────────── */
function ProgressBar({ value, width = 30, color = 'accent', showPct = true }) {
  const filled = Math.round(value * width);
  return (
    <span style={{ whiteSpace: 'pre' }}>
      <S fg={color} bold>{'█'.repeat(filled)}</S>
      <S fg="muted">{'░'.repeat(Math.max(0, width - filled))}</S>
      {showPct && <S> {String(Math.round(value * 100)).padStart(3)}%</S>}
    </span>
  );
}

const SPARK = ['▁', '▂', '▃', '▄', '▅', '▆', '▇', '█'];
function Sparkline({ values, color = 'muted', lo, hi }) {
  const min = lo ?? Math.min(...values);
  const max = hi ?? Math.max(...values);
  const span = (max - min) || 1;
  const text = values.map(v => SPARK[Math.min(7, Math.max(0, Math.floor((v - min) / span * 7.999)))]).join('');
  return <S fg={color} style={{ whiteSpace: 'pre' }}>{text}</S>;
}

const SPIN_FRAMES = { dots: ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'], line: ['-', '\\', '|', '/'], braille: ['⣾', '⣽', '⣻', '⢿', '⡿', '⣟', '⣯', '⣷'] };
function Spinner({ color = 'warning', tick = 90, frames = 'dots' }) {
  const set = Array.isArray(frames) ? frames : (SPIN_FRAMES[frames] || SPIN_FRAMES.dots);
  const [i, setI] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setI(x => (x + 1) % set.length), tick);
    return () => clearInterval(id);
  }, [tick, frames]);
  return <S fg={color} style={{ whiteSpace: 'pre' }}>{set[i % set.length]}</S>;
}

function Dot({ color = 'success', glyph = '●', children }) {
  return <span style={{ whiteSpace: 'nowrap' }}><S fg={color}>{glyph}</S> {children}</span>;
}

/* ── Data views — chart_lens (bars) · tree_lens · list_view ───────────────── */
function BarChart({ data, width = 24 }) {
  const vals = data.map(d => d.value);
  const lo = Math.min(...vals), hi = Math.max(...vals), span = (hi - lo) || 1;
  const labw = Math.max(...data.map(d => d.label.length));
  return (
    <div style={{ whiteSpace: 'pre', lineHeight: 1.7 }}>
      {data.map((d, i) => {
        const f = Math.round((d.value - lo) / span * width);
        return (
          <div key={i}>
            <S>{d.label.padEnd(labw)} </S>
            <S fg={d.color || 'accent'}>{'█'.repeat(f)}</S>
            <S fg="muted">{'░'.repeat(width - f)}</S>
            <S fg="dim"> {String(d.value).padStart(5)}</S>
          </div>
        );
      })}
    </div>
  );
}

function flatten(nodes, expanded, prefix = '', path = '') {
  const out = [];
  nodes.forEach((n, i) => {
    const p = path + '/' + n.name;
    const last = i === nodes.length - 1;
    out.push({ node: n, prefix, last, path: p, open: !!expanded[p] });
    if (n.children && expanded[p]) out.push(...flatten(n.children, expanded, prefix + (last ? '   ' : '│  '), p));
  });
  return out;
}
function Tree({ root, color = 'accent' }) {
  const [expanded, setExpanded] = useState({ '/src': true, '/src/painted': true });
  const [sel, setSel] = useState('/src');
  const rows = flatten(root, expanded);
  return (
    <div style={{ lineHeight: 1.55, whiteSpace: 'pre' }}>
      {rows.map((r, i) => {
        const isSel = r.path === sel;
        const dir = !!r.node.children;
        return (
          <div key={i}
            onClick={() => { setSel(r.path); if (dir) setExpanded(e => ({ ...e, [r.path]: !e[r.path] })); }}
            style={{ cursor: 'pointer', background: isSel ? PT.accent : 'transparent', color: isSel ? PT.ink : undefined }}>
            <span style={{ opacity: isSel ? 1 : 0.5 }}>{r.prefix}{r.prefix && (r.last ? '└── ' : '├── ')}</span>
            {dir ? <S fg={isSel ? undefined : color}>{r.open ? '▼ ' : '▶ '}</S> : <span>  </span>}
            <S bold={dir && !isSel}>{r.node.name}{dir ? '/' : ''}</S>
            <S fg={isSel ? undefined : 'dim'} dim={!isSel}>  {r.node.size}</S>
          </div>
        );
      })}
    </div>
  );
}

function ListView({ items, selected, onSelect, accent = 'accent' }) {
  return (
    <div style={{ lineHeight: 1.75 }}>
      {items.map((it, i) => {
        const isSel = i === selected;
        return (
          <div key={i} onClick={() => onSelect && onSelect(i)} style={{ cursor: 'pointer', display: 'flex', gap: 6, whiteSpace: 'pre' }}>
            {isSel ? <S fg={accent} bold>▸ </S> : <span>  </span>}
            <S fg={isSel ? accent : undefined} bold={isSel}>{it}</S>
          </div>
        );
      })}
    </div>
  );
}

/* ── Record rendering — record_line stream with a gutter rail ─────────────── */
const KIND_COLOR = (kind) => ({
  error: 'error', alert: 'error', critical: 'error', warning: 'warning', warn: 'warning',
  change: 'success', deploy: 'success', success: 'success', completed: 'success',
  decision: 'accent', thread: 'accent', task: 'accent', exchange: 'accent', tick: 'accent',
}[kind] || null);

const _SUMMARY_KEYS = ['topic', 'message', 'name', 'title', 'summary', 'description', 'text'];
function _summary(kind, payload) {
  for (const key of _SUMMARY_KEYS) if (payload[key]) return String(payload[key]);
  return Object.entries(payload).filter(([, v]) => v).map(([k, v]) => `${k}=${v}`).join(' ');
}
const _hhmm = (ts) => ts.toTimeString().slice(0, 5);
const _iso = (ts) => ts.toISOString().slice(0, 19) + 'Z';

function recordRows(ts, kind, payload, zoom) {
  const kc = KIND_COLOR(kind);
  const summary = _summary(kind, payload);
  if (zoom <= 0) return [[{ text: summary }]];
  const meta = (tsStr) => [{ text: tsStr + ' ', fg: 'muted' }, { text: '[', fg: 'muted' }, { text: kind, fg: kc || undefined, bold: !!kc }, { text: '] ', fg: 'muted' }];
  if (zoom <= 1) return [[...meta(_hhmm(ts)), { text: summary }]];
  if (zoom <= 2) {
    const rows = [[...meta(_hhmm(ts)), { text: summary }]];
    for (const [k, v] of Object.entries(payload)) {
      if (v === null || v === '' || v === undefined) continue;
      const sv = String(v);
      if (['description', 'message', 'body', 'response', 'output'].includes(k) || sv.length > 40) rows.push([{ text: `  ${k}: ${sv}`, fg: 'muted' }]);
    }
    return rows;
  }
  const rows = [[...meta(_iso(ts)), { text: summary }]];
  for (const [k, v] of Object.entries(payload)) {
    if (v === null || v === '' || v === undefined) continue;
    rows.push([{ text: `  ${k}: ${v}`, fg: 'muted' }]);
  }
  return rows;
}

const GUTTERS = {
  level: (kind, p) => {
    const l = p.level || '';
    if (l === 'ERROR') return ['█', 'error'];
    if (l === 'WARN') return ['▐', 'warning'];
    if (l === 'DEBUG') return ['│', 'muted'];
    return ['│', 'accent'];
  },
};
const _GUTTER_STEP = { '█': '▐', '▐': '│', '│': '│', '·': '·' };

function Seg({ s }) { return <S fg={s.fg} bold={s.bold}>{s.text}</S>; }

function RecordStream({ records, zoom = 1, gutter, lineHeight = 1.7 }) {
  const gFn = gutter ? GUTTERS[gutter] : null;
  const out = [];
  records.forEach((rec, ri) => {
    const { ts, kind, payload } = rec;
    const rows = recordRows(ts, kind, payload, zoom);
    const [gch, gcolor] = gFn ? gFn(kind, payload) : [null, null];
    rows.forEach((segs, li) => {
      out.push(
        <div key={`${ri}-${li}`} style={{ display: 'flex', whiteSpace: 'pre' }}>
          {gch && <span style={{ color: PT[gcolor] }}>{(li === 0 ? gch : _GUTTER_STEP[gch] || gch) + ' '}</span>}
          {segs.map((s, i) => <Seg key={i} s={s} />)}
        </div>
      );
    });
  });
  return <div style={{ lineHeight }}>{out}</div>;
}

/* ── Default sample data (decorative — NOT real painted output) ───────────── */
const VIEWS = ['Status', 'Charts', 'Tree', 'Carnival', 'Logs'];

const DEFAULT_SERVICES = [
  { name: 'api-gateway', state: 'ok', glyph: '●', color: 'success', cpu: 0.34, spark: [12, 18, 25, 38, 30, 42, 51, 47, 44, 52, 61, 58] },
  { name: 'auth-svc', state: 'ok', glyph: '●', color: 'success', cpu: 0.61, spark: [40, 42, 38, 45, 55, 60, 52, 48, 58, 66, 61, 63] },
  { name: 'cache', state: 'degraded', glyph: '⚡', color: 'warning', cpu: 0.88, spark: [70, 72, 80, 88, 92, 85, 90, 95, 93, 88, 91, 94] },
  { name: 'worker-pool', state: 'down', glyph: '✗', color: 'error', cpu: 0.16, spark: [60, 40, 20, 10, 8, 6, 12, 9, 7, 5, 8, 16] },
];

const DEFAULT_REGIONS = [
  { label: 'us-east', value: 820, color: 'accent' },
  { label: 'us-west', value: 540, color: 'green' },
  { label: 'eu-west', value: 670, color: 'magenta' },
  { label: 'ap-south', value: 310, color: 'yellow' },
  { label: 'sa-east', value: 190, color: 'red' },
];

const DEFAULT_FILE_TREE = [
  { name: 'src', size: '2.4M', children: [
    { name: 'painted', size: '1.8M', children: [
      { name: 'core', size: '840K' }, { name: 'views', size: '610K' }, { name: 'tui', size: '390K' },
    ] },
    { name: '__init__.py', size: '6K' },
  ] },
  { name: 'tests', size: '980K', children: [{ name: 'unit', size: '420K' }, { name: 'property', size: '560K' }] },
  { name: 'demos', size: '1.2M' },
];

const DEFAULT_LOGS = [
  { h: [14, 23, 1], kind: 'info', payload: { level: 'INFO', message: 'run_cli: detected TTY → mode=INTERACTIVE' } },
  { h: [14, 23, 1], kind: 'debug', payload: { level: 'DEBUG', message: 'fidelity: depth=2 (-v), chars=∞ lines=∞' } },
  { h: [14, 23, 2], kind: 'info', payload: { level: 'INFO', message: 'Surface.run: alt-screen acquired, diff-flush on' } },
  { h: [14, 23, 4], kind: 'warning', payload: { level: 'WARN', message: 'cache: latency 140ms exceeds 100ms budget' } },
  { h: [14, 23, 5], kind: 'info', payload: { level: 'INFO', message: 'palette: ambient set → NORD (scoped)' } },
  { h: [14, 23, 6], kind: 'error', payload: { level: 'ERROR', message: 'worker-pool: connection refused (econnrefused)' } },
  { h: [14, 23, 7], kind: 'info', payload: { level: 'INFO', message: 'render: 1 frame painted, 38 cells changed' } },
  { h: [14, 23, 8], kind: 'debug', payload: { level: 'DEBUG', message: 'wcwidth: measured 4 wide glyphs in row 12' } },
].map(r => ({ ts: new Date(2026, 5, 1, ...r.h), kind: r.kind, payload: r.payload }));

const PALETTES = {
  default: {},
  nord: { '--green': '#87af87', '--yellow': '#d7af5f', '--red': '#d78787', '--cyan': '#87afd7', '--blue': '#5f87af', '--magenta': '#af87af', '--fg-dim': '#6b7280' },
  mono: { '--green': 'var(--fg)', '--yellow': 'var(--fg)', '--red': 'var(--fg)', '--cyan': 'var(--fg)', '--blue': 'var(--fg)', '--magenta': 'var(--fg)' },
};
const PAL_NAMES = ['default', 'nord', 'mono'];

/* ── Views ────────────────────────────────────────────────────────────────── */
function StatusView({ services }) {
  return (
    <Col gap={3} style={{ height: '100%' }}>
      <Row gap={2} style={{ flexWrap: 'wrap' }}>
        <Dot color="success">Connected</Dot>
        <Dot color="error" glyph="✗">1 down</Dot>
        <Dot color="warning" glyph="⚡">1 degraded</Dot>
        <span style={{ whiteSpace: 'nowrap' }}><Spinner /> <S fg="muted">polling…</S></span>
      </Row>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        {services.map(s => (
          <Panel key={s.name} title={s.name} accent={s.color} right={s.state}>
            <Col gap={2}>
              <Row gap={2}><S fg="muted" style={{ width: 46, display: 'inline-block' }}>cpu</S><ProgressBar value={s.cpu} width={20} color={s.color} /></Row>
              <Row gap={2}><S fg="muted" style={{ width: 46, display: 'inline-block' }}>load</S><Sparkline values={s.spark} color={s.color} /></Row>
            </Col>
          </Panel>
        ))}
      </div>
    </Col>
  );
}

function ChartsView({ services, regions }) {
  return (
    <Col gap={4} style={{ height: '100%' }}>
      <div>
        <S fg="muted">requests / region · </S><S fg="accent" bold>chart_lens</S><S fg="muted"> zoom=3</S>
        <div style={{ marginTop: 10 }}><BarChart data={regions} width={28} /></div>
      </div>
      <div>
        <S fg="muted">throughput sparklines · last 12 ticks</S>
        <Col gap={1} style={{ marginTop: 10 }}>
          {services.map(s => (
            <Row key={s.name} gap={2}>
              <S style={{ width: 110, display: 'inline-block' }}>{s.name}</S>
              <Sparkline values={s.spark} color={s.color} />
              <S fg="dim"> {Math.max(...s.spark)}</S>
            </Row>
          ))}
        </Col>
      </div>
    </Col>
  );
}

function TreeView({ fileTree }) {
  return (
    <Col gap={2}>
      <S fg="muted">disk usage · <S fg="accent" bold>tree_lens</S> · click a ▶ to drill in</S>
      <div style={{ marginTop: 4 }}><Tree root={fileTree} /></div>
    </Col>
  );
}

function CarnivalView({ palIndex, setPalIndex }) {
  const name = PAL_NAMES[palIndex];
  const vars = PALETTES[name];
  return (
    <Col gap={3} style={{ height: '100%' }}>
      <Row gap={2} style={{ flexWrap: 'wrap' }}>
        <S fg="muted">palette </S>
        {PAL_NAMES.map((p, i) => (
          <span key={p} onClick={() => setPalIndex(i)} style={{ cursor: 'pointer', whiteSpace: 'nowrap' }}>
            {i === palIndex ? <S fg="accent" bold>▸ {p}</S> : <S fg="dim">  {p}</S>}
          </span>
        ))}
        <S fg="muted" style={{ whiteSpace: 'nowrap' }}>  ←/→ to cycle</S>
      </Row>
      <div style={{ ...vars, border: `1px solid var(--line)`, background: 'var(--panel)', padding: 16 }}>
        <Col gap={3}>
          <Row gap={2} wrap>
            <Dot color="success">success</Dot><Dot color="warning" glyph="⚡">warning</Dot>
            <Dot color="error" glyph="✗">error</Dot><span style={{ whiteSpace: 'nowrap' }}><Spinner /> <S fg="muted">working</S></span>
          </Row>
          <Row gap={2}><S fg="muted" style={{ width: 64, display: 'inline-block' }}>progress</S><ProgressBar value={0.72} width={26} color="success" /></Row>
          <Row gap={3}>
            <S reverse fg="accent" bold> Save </S>
            <S> Cancel </S>
            <S fg="error"> Delete </S>
          </Row>
          <Row gap={2} wrap>
            <S reverse fg="success"> success </S><S reverse fg="warning"> warning </S>
            <S reverse fg="error"> error </S><S reverse fg="accent"> accent </S>
          </Row>
        </Col>
      </div>
      {name === 'mono' && <S fg="muted" italic>MONO collapses color → meaning carries on bold / reverse / dim.</S>}
    </Col>
  );
}

function LogsView({ logs }) {
  return (
    <Col gap={0}>
      <S fg="muted">record_line stream · <S fg="accent" bold>gutter_fn</S> rail encodes level · zoom=SUMMARY</S>
      <div style={{ marginTop: 10 }}>
        <RecordStream records={logs} zoom={1} gutter="level" lineHeight={1.85} />
      </div>
    </Col>
  );
}

/* ── Entry component ──────────────────────────────────────────────────────── */
function resolveView(v) {
  if (typeof v === 'string') { const i = VIEWS.indexOf(v); return i >= 0 ? i : 0; }
  return Math.max(0, Math.min(VIEWS.length - 1, v | 0));
}

export default function PaintedSurface({
  initialView = 0,
  initialPalette = 'default',
  keyboardNav = true,
  autoFocus = false,
  data = {},
  theme = PAINTED_THEME,
  className,
  style,
}) {
  const [view, setView] = useState(() => resolveView(initialView));
  const [palIndex, setPalIndex] = useState(() => Math.max(0, PAL_NAMES.indexOf(initialPalette)));
  const rootRef = useRef(null);

  const services = data.services || DEFAULT_SERVICES;
  const regions = data.regions || DEFAULT_REGIONS;
  const fileTree = data.fileTree || DEFAULT_FILE_TREE;
  const logs = data.logs || DEFAULT_LOGS;

  useEffect(() => { if (autoFocus && rootRef.current) rootRef.current.focus(); }, [autoFocus]);

  function onKeyDown(e) {
    if (!keyboardNav) return;
    if (e.key === 'ArrowDown' || e.key === 'j') { setView(v => (v + 1) % VIEWS.length); e.preventDefault(); }
    else if (e.key === 'ArrowUp' || e.key === 'k') { setView(v => (v - 1 + VIEWS.length) % VIEWS.length); e.preventDefault(); }
    else if (e.key >= '1' && e.key <= String(VIEWS.length)) { setView(+e.key - 1); }
    else if (e.key === 'ArrowRight') { setPalIndex(p => (p + 1) % PAL_NAMES.length); e.preventDefault(); }
    else if (e.key === 'ArrowLeft') { setPalIndex(p => (p - 1 + PAL_NAMES.length) % PAL_NAMES.length); e.preventDefault(); }
  }

  const main = [
    <StatusView services={services} />,
    <ChartsView services={services} regions={regions} />,
    <TreeView fileTree={fileTree} />,
    <CarnivalView palIndex={palIndex} setPalIndex={setPalIndex} />,
    <LogsView logs={logs} />,
  ][view];

  const rootStyle = {
    ...(theme || {}),
    background: PT.ink, color: PT.fg, fontFamily: 'var(--font-mono)',
    fontVariantLigatures: 'none', WebkitFontSmoothing: 'antialiased',
    fontSize: 15, lineHeight: 1.45,
    height: '100%', minHeight: 520, width: '100%',
    display: 'flex', flexDirection: 'column', padding: 16, gap: 10,
    boxSizing: 'border-box', outline: 'none',
    ...(style || {}),
  };

  return (
    <div
      ref={rootRef}
      className={className}
      style={rootStyle}
      tabIndex={keyboardNav ? 0 : undefined}
      onKeyDown={onKeyDown}
      role="application"
      aria-label="painted system-monitor (cosmetic demo)"
    >
      {/* title bar */}
      <Row gap={3} style={{ flexShrink: 0, paddingBottom: 4, borderBottom: `1px solid var(--line)` }}>
        <S fg="accent" bold style={{ fontSize: 18, whiteSpace: 'nowrap' }}>painted</S>
        <S fg="muted" style={{ whiteSpace: 'nowrap' }}>system-monitor</S>
        <span style={{ flex: 1 }} />
        <KeyHint k="↑↓" label="nav" /><KeyHint k="1-5" label="jump" /><KeyHint k="←→" label="palette" /><KeyHint k="q" label="quit" />
      </Row>
      {/* body */}
      <div style={{ flex: 1, minHeight: 0, display: 'grid', gridTemplateColumns: '210px 1fr', gap: 12 }}>
        <Panel title="views" focused>
          <ListView items={VIEWS.map((v, i) => `${i + 1}. ${v}`)} selected={view} onSelect={setView} />
        </Panel>
        <Panel title={VIEWS[view].toLowerCase()} accent="cyan" right={`${view + 1}/${VIEWS.length}`} bodyStyle={{ overflow: 'auto' }}>
          {main}
        </Panel>
      </div>
      {/* footer */}
      <Row gap={3} style={{ flexShrink: 0, paddingTop: 4, borderTop: `1px solid var(--line)`, fontSize: 13 }}>
        <span style={{ whiteSpace: 'nowrap' }}><S fg="dim">mode </S><S reverse fg="accent" bold> -i </S><S fg="dim"> --static --live --json</S></span>
        <span style={{ flex: 1 }} />
        <S fg="dim" style={{ whiteSpace: 'nowrap' }}>{`▸ ${VIEWS[view]}  ·  palette: ${PAL_NAMES[palIndex]}`}</S>
      </Row>
    </div>
  );
}
