// tsdataprep demo site -- DuckDB-WASM + Plotly. No frameworks.
//
// Loads four Parquet samples (D1, H4, W1, MN1 from the clean_5y scope), registers
// them as DuckDB views in the browser, renders three Plotly figures via SQL, and
// powers a free-form SQL panel against the same in-memory DB.

import * as duckdb from 'https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.29.0/+esm';

const PARQUETS = {
  d1:  'data/xauusd_d1_clean_5y.parquet',
  h4:  'data/xauusd_h4_clean_5y.parquet',
  w1:  'data/xauusd_w1_clean_5y.parquet',
  mn1: 'data/xauusd_mn1_clean_5y.parquet',
};

const PLOT_LAYOUT_BASE = {
  paper_bgcolor: '#161922',
  plot_bgcolor:  '#161922',
  font: { color: '#e8eaed', family: 'inherit', size: 12 },
  margin: { l: 56, r: 24, t: 12, b: 48 },
  xaxis: { gridcolor: '#2a2f3d', zerolinecolor: '#2a2f3d' },
  yaxis: { gridcolor: '#2a2f3d', zerolinecolor: '#2a2f3d' },
  hoverlabel: { bgcolor: '#1f2330', font: { color: '#e8eaed' } },
};

const PLOT_CONFIG = { displaylogo: false, responsive: true };

const status = (msg) => {
  const el = document.getElementById('sql-status');
  if (el) el.textContent = msg;
};

let db = null;
let conn = null;

async function initDuckDB() {
  status('Initialising DuckDB-WASM (downloads ~3 MB on first use)...');
  const bundles = duckdb.getJsDelivrBundles();
  const bundle = await duckdb.selectBundle(bundles);
  const worker_url = URL.createObjectURL(
    new Blob([`importScripts("${bundle.mainWorker}");`], { type: 'text/javascript' })
  );
  const worker = new Worker(worker_url);
  const logger = new duckdb.ConsoleLogger();
  db = new duckdb.AsyncDuckDB(logger, worker);
  await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
  URL.revokeObjectURL(worker_url);
  conn = await db.connect();

  status('Loading Parquet samples...');
  // Cast ts to plain TIMESTAMP at view creation: DuckDB-WASM 1.29 ships without
  // the date_part(VARCHAR, TIMESTAMP WITH TIME ZONE) overload, so extract('hour' FROM ts)
  // would otherwise fail. The Parquet files store ts as TIMESTAMPTZ (UTC).
  for (const [name, path] of Object.entries(PARQUETS)) {
    const buf = await (await fetch(path)).arrayBuffer();
    await db.registerFileBuffer(`${name}.parquet`, new Uint8Array(buf));
    await conn.query(`
      CREATE VIEW ${name} AS
      SELECT ts::TIMESTAMP AS ts,
             open, high, low, close,
             tick_volume, real_volume,
             spread_points, spread_pips
      FROM '${name}.parquet'
    `);
  }
  status('DuckDB ready. 4 views registered: d1, h4, w1, mn1.');
}

async function ensureDB() {
  if (conn) return;
  await initDuckDB();
}

// ── Charts ────────────────────────────────────────────────────────────────────

async function renderPriceChart() {
  await ensureDB();
  const res = await conn.query('SELECT ts, close FROM d1 ORDER BY ts');
  const ts = [];
  const close = [];
  for (const row of res.toArray()) {
    ts.push(new Date(Number(row.ts)));
    close.push(Number(row.close));
  }
  Plotly.newPlot('chart-price', [{
    x: ts, y: close, type: 'scatter', mode: 'lines',
    line: { color: '#f5b041', width: 1.4 },
    name: 'XAUUSD close',
    hovertemplate: '%{x|%Y-%m-%d}<br>$%{y:.2f}<extra></extra>',
  }], {
    ...PLOT_LAYOUT_BASE,
    yaxis: { ...PLOT_LAYOUT_BASE.yaxis, title: 'USD / oz', tickprefix: '$' },
    xaxis: { ...PLOT_LAYOUT_BASE.xaxis, title: '' },
  }, PLOT_CONFIG);
}

async function renderSpreadByHour() {
  await ensureDB();
  const res = await conn.query(`
    SELECT extract('hour' FROM ts) AS hour,
           avg(spread_pips) AS avg_spread,
           quantile_cont(spread_pips, 0.5) AS median_spread,
           count(*) AS bars
    FROM h4
    GROUP BY hour
    ORDER BY hour
  `);
  const x = [], avg = [], median = [];
  for (const row of res.toArray()) {
    x.push(Number(row.hour));
    avg.push(Number(row.avg_spread));
    median.push(Number(row.median_spread));
  }
  Plotly.newPlot('chart-spread-hour', [
    { x, y: median, type: 'bar', name: 'median', marker: { color: '#59b4ff' } },
    { x, y: avg, type: 'scatter', mode: 'lines+markers', name: 'mean',
      line: { color: '#f5b041', width: 2 }, marker: { size: 6 } },
  ], {
    ...PLOT_LAYOUT_BASE,
    barmode: 'group',
    xaxis: { ...PLOT_LAYOUT_BASE.xaxis, title: 'Hour of day (UTC)', dtick: 1 },
    yaxis: { ...PLOT_LAYOUT_BASE.yaxis, title: 'spread_pips' },
    legend: { x: 0.02, y: 0.98, bgcolor: 'rgba(0,0,0,0)' },
  }, PLOT_CONFIG);
}

async function renderMonthlyOHLC() {
  await ensureDB();
  const res = await conn.query(`
    SELECT date_trunc('month', ts) AS month,
           first(open  ORDER BY ts) AS open,
           max(high)                AS high,
           min(low)                 AS low,
           last(close ORDER BY ts)  AS close
    FROM d1
    GROUP BY month
    ORDER BY month
  `);
  const x = [], o = [], h = [], l = [], c = [];
  for (const row of res.toArray()) {
    x.push(new Date(Number(row.month)));
    o.push(Number(row.open));
    h.push(Number(row.high));
    l.push(Number(row.low));
    c.push(Number(row.close));
  }
  Plotly.newPlot('chart-monthly', [{
    x, open: o, high: h, low: l, close: c,
    type: 'candlestick',
    increasing: { line: { color: '#39c08c' } },
    decreasing: { line: { color: '#e35c5c' } },
  }], {
    ...PLOT_LAYOUT_BASE,
    yaxis: { ...PLOT_LAYOUT_BASE.yaxis, title: 'USD / oz', tickprefix: '$' },
    xaxis: { ...PLOT_LAYOUT_BASE.xaxis, title: '', rangeslider: { visible: false } },
  }, PLOT_CONFIG);
}

// ── SQL panel ─────────────────────────────────────────────────────────────────

// Year 2000 .. year 2100 in milliseconds since epoch -- heuristic to render
// timestamp values returned by DuckDB-WASM as ISO strings. The JS bindings
// return TIMESTAMP columns as numbers (or bigints if they exceed safe int);
// neither type is intrinsically distinguishable from a normal integer, so we
// fall back to a value-range check. 1291 (the bar count) is below TS_MIN so
// stays a number; 1577923200000 (a 2020-01 epoch ms) gets formatted.
const TS_MIN = 946684800000;       // 2000-01-01 UTC
const TS_MAX = 4102444800000;      // 2100-01-01 UTC
const isLikelyEpochMs = (n) => n >= TS_MIN && n <= TS_MAX;

function fmtTs(numericMs) {
  return new Date(numericMs).toISOString().replace('T', ' ').replace('.000Z', '');
}

function fmt(value) {
  if (value === null || value === undefined) return '<span class="muted">null</span>';
  if (value instanceof Date) return value.toISOString().replace('T', ' ').replace('.000Z', '');
  if (typeof value === 'bigint') {
    const asNum = Number(value);
    if (Number.isSafeInteger(asNum) && isLikelyEpochMs(asNum)) return fmtTs(asNum);
    return value.toString();
  }
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return String(value);
    if (Number.isInteger(value) && isLikelyEpochMs(value)) return fmtTs(value);
    return Number.isInteger(value) ? value.toString() : value.toFixed(4);
  }
  return String(value);
}

function renderResultTable(result) {
  const rows = result.toArray();
  if (!rows.length) {
    return '<div class="muted small">Query returned no rows.</div>';
  }
  const fields = result.schema.fields.map((f) => f.name);
  const header = '<tr>' + fields.map((c) => `<th>${c}</th>`).join('') + '</tr>';
  const body = rows.slice(0, 500).map((row) => {
    return '<tr>' + fields.map((c) => `<td>${fmt(row[c])}</td>`).join('') + '</tr>';
  }).join('');
  const note = rows.length > 500
    ? `<div class="muted small">Showing first 500 of ${rows.length} rows.</div>`
    : `<div class="muted small">${rows.length} rows.</div>`;
  return `<table>${header}${body}</table>${note}`;
}

async function runQuery() {
  const input = document.getElementById('sql-input');
  const output = document.getElementById('sql-output');
  const sql = input.value.trim();
  if (!sql) return;
  try {
    await ensureDB();
    status('Running query...');
    const t0 = performance.now();
    const result = await conn.query(sql);
    const ms = (performance.now() - t0).toFixed(0);
    output.innerHTML = renderResultTable(result);
    status(`Query OK in ${ms} ms.`);
  } catch (err) {
    output.innerHTML = `<div class="err">${String(err && err.message || err)}</div>`;
    status('Query failed. See output below.');
  }
}

// ── Boot ──────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  // Wire SQL panel
  const preset = document.getElementById('sql-preset');
  const input = document.getElementById('sql-input');
  const runBtn = document.getElementById('sql-run');
  if (preset && input) {
    preset.addEventListener('change', () => {
      if (preset.value) input.value = preset.value;
    });
  }
  if (runBtn) runBtn.addEventListener('click', runQuery);
  if (input) {
    input.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') runQuery();
    });
  }

  // Render charts in sequence (DB init is shared) but isolate failures: a broken
  // query for one chart should not blank the others.
  const renderers = [
    ['chart-price',        renderPriceChart],
    ['chart-spread-hour',  renderSpreadByHour],
    ['chart-monthly',      renderMonthlyOHLC],
  ];
  for (const [id, fn] of renderers) {
    try {
      await fn();
    } catch (err) {
      console.error(`Chart ${id} failed:`, err);
      const el = document.getElementById(id);
      if (el) el.innerHTML = `<div class="muted small">Chart unavailable: ${String(err.message || err)}</div>`;
    }
  }
});
