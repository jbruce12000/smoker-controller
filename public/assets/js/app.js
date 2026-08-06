'use strict';

// ---------------------------------------------------------------- config
const UNITS = { c: '\u00b0C', f: '\u00b0F' };
const MIN = 85;
const MAX = 500;
const MAX_HISTORY = 3000;   // max samples kept for charts/table
const TABLE_ROWS = 30;      // rows shown in the history table
const SPAN_MIN = 2;         // chart-span slider minimum (minutes)
const SPAN_MAX = 300;       // chart-span slider maximum (minutes; covers entire data set)
const SPAN_DEFAULT = 600;   // default chart span (seconds) = 10 min
let timeSpanSecs = SPAN_DEFAULT; // 0 = entire data set

const els = {
  connection: document.getElementById('connection'),
  connectionText: document.getElementById('connection-text'),
  temp: document.getElementById('temp'),
  tempUnit: document.getElementById('temp-unit'),
  setpoint: document.getElementById('setpoint'),
  setpointUnit: document.getElementById('setpoint-unit'),
  errorNow: document.getElementById('error-now'),
  errorAvg: document.getElementById('error-avg'),
  heat: document.getElementById('heat'),
  runtime: document.getElementById('runtime'),
  flapperBox: document.getElementById('flapper-readout'),
  stateBadge: document.getElementById('state-badge'),
  slider: document.getElementById('setpoint-slider'),
  input: document.getElementById('setpoint-input'),
  start: document.getElementById('start'),
  stop: document.getElementById('stop'),
  hint: document.getElementById('hint'),
  timeSpan: document.getElementById('time-span'),
  timeSpanVal: document.getElementById('time-span-val'),
  csv: document.getElementById('csv'),
  tableBody: document.querySelector('#history-table tbody'),
};

// ---------------------------------------------------------------- state
let units = 'f';
let running = false;
const history = []; // {t, temp, target, err, heat, p, i, d}
let woodThreshold = 75;   // flapper % that counts as "wide open"
let woodCycles = 10;      // consecutive wide-open cycles before the wood alarm
let woodHighCount = 0;    // consecutive cycles the flapper has been wide open

function wsUrl(path) {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return proto + '//' + window.location.host + path;
}

// ---------------------------------------------------------------- charts
function deepClone(obj) {
  if (obj === null || typeof obj !== 'object') return obj;
  if (Array.isArray(obj)) return obj.map(deepClone);
  const out = {};
  for (const key of Object.keys(obj)) out[key] = deepClone(obj[key]);
  return out;
}

const COMMON = {
  responsive: true,
  maintainAspectRatio: false,
  animation: false,
  interaction: { mode: 'nearest', axis: 'x', intersect: false },
  scales: {
    x: {
      type: 'linear',
      bounds: 'data',
      ticks: {
        color: '#8b95a5',
        maxTicksLimit: 8,
        callback: v => new Date(v * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
      grid: { color: 'rgba(255,255,255,0.05)' },
    },
    y: { ticks: { color: '#8b95a5' }, grid: { color: 'rgba(255,255,255,0.05)' } },
  },
  plugins: {
    legend: { labels: { color: '#8b95a5', boxWidth: 12 } },
    tooltip: {
      callbacks: {
        title: items => new Date(items[0].parsed.x * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      },
    },
  },
};

function lineChart(canvasId, series, yOptions) {
  const datasets = series.map(s => ({
    label: s.label,
    data: [],
    borderColor: s.color,
    backgroundColor: s.bg,
    fill: s.fill || false,
    stepped: s.stepped || false,
    borderDash: s.dash,
    borderWidth: 2,
    pointRadius: 0,
    tension: 0.2,
  }));
  const options = deepClone(COMMON);
  if (yOptions && yOptions.ticksCallback) {
    options.scales.y.ticks.callback = yOptions.ticksCallback;
  }
  if (yOptions && yOptions.title) {
    options.scales.y.title = { display: true, text: yOptions.title, color: '#8b95a5' };
  }
  if (yOptions && yOptions.suggestedMin != null) {
    options.scales.y.suggestedMin = yOptions.suggestedMin;
    options.scales.y.suggestedMax = yOptions.suggestedMax;
  }
  if (yOptions && yOptions.legend === false) {
    options.plugins.legend.display = false;
  }
  const chart = new Chart(document.getElementById(canvasId), {
    type: 'line',
    data: { datasets },
    options: options,
  });
  return {
    chart: chart,
    set(yArrays) {
      const cutoff = timeSpanSecs && history.length ? history[history.length - 1].t - timeSpanSecs : 0;
      chart.data.datasets.forEach((ds, i) => {
        ds.data = [];
        for (let j = 0; j < history.length; j++) {
          if (timeSpanSecs && history[j].t < cutoff) continue;
          ds.data.push({ x: history[j].t, y: yArrays[i][j] });
        }
      });
      chart.update('none');
    },
  };
}

let chartsReady = false;
let chartTemps, chartHeat, chartError, chartP, chartI, chartD;
try {
  chartTemps = lineChart('chart-temps', [
    { label: 'Temperature', color: '#ef8354', bg: 'rgba(239,131,84,0.12)', fill: true },
    { label: 'Target', color: '#4f9cf9', stepped: true, dash: [6, 4] },
  ], { title: '\u00b0F' });
  chartHeat = lineChart('chart-heat', [{ label: 'Flapper', color: '#4caf7d' }],
    { ticksCallback: v => v + '%', legend: false });
  chartError = lineChart('chart-error', [{ label: 'Error', color: '#e4572e' }],
    { title: '\u00b0F', suggestedMin: -50, suggestedMax: 50, legend: false });
  chartP = lineChart('chart-p', [{ label: 'P', color: '#4f9cf9' }], { legend: false });
  chartI = lineChart('chart-i', [{ label: 'I', color: '#9c6df2' }], { legend: false });
  chartD = lineChart('chart-d', [{ label: 'D', color: '#f2c14e' }], { legend: false });
  chartsReady = true;
} catch (e) {
  console.error('Chart.js failed to initialize, charts disabled:', e);
}

function ys(key) {
  const n = history.length;
  const arr = new Array(n);
  for (let i = 0; i < n; i++) arr[i] = history[i][key];
  return arr;
}

function redrawCharts() {
  if (!chartsReady) return;
  chartTemps.set([ys('temp'), ys('target')]);
  chartHeat.set([ys('heat')]);
  chartError.set([ys('err')]);
  chartP.set([ys('p')]);
  chartI.set([ys('i')]);
  chartD.set([ys('d')]);
}

function setChartUnits() {
  if (!chartsReady) return;
  const u = UNITS[units] || UNITS.f;
  chartTemps.chart.options.scales.y.title.text = u;
  chartError.chart.options.scales.y.title.text = u;
  chartTemps.chart.update('none');
  chartError.chart.update('none');
}

// ---------------------------------------------------------------- UI
function formatRuntime(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const pad = n => String(n).padStart(2, '0');
  return pad(h) + ':' + pad(m) + ':' + pad(s);
}

function updateWoodAlert(s) {
  if (s.state !== 'RUNNING' || s.heat == null) {
    woodHighCount = 0;
    els.flapperBox.classList.remove('alert');
    return;
  }
  woodHighCount = s.heat > woodThreshold ? woodHighCount + 1 : 0;
  els.flapperBox.classList.toggle('alert', woodHighCount > woodCycles);
}

function updateUi(s) {
  const isRunning = s.state === 'RUNNING';
  if (s.temperature != null) els.temp.textContent = Math.round(s.temperature);
  if (s.setpoint != null) {
    els.setpoint.textContent = Math.round(s.setpoint);
    // keep the user's chosen target while idle; only sync while running
    if (isRunning && document.activeElement !== els.input && document.activeElement !== els.slider) {
      els.input.value = Math.round(s.setpoint);
      els.slider.value = Math.round(s.setpoint);
    }
  }
  if (s.heat != null) els.heat.textContent = Math.round(s.heat);
  if (s.runtime != null) els.runtime.textContent = formatRuntime(s.runtime);
  if (s.units) {
    units = s.units;
    els.tempUnit.textContent = UNITS[units];
    els.setpointUnit.textContent = UNITS[units];
    setChartUnits();
  }
  if (s.wood_alert_threshold != null) woodThreshold = s.wood_alert_threshold;
  if (s.wood_alert_cycles != null) woodCycles = s.wood_alert_cycles;
  updateWoodAlert(s);

  running = isRunning;
  els.stateBadge.textContent = running ? 'RUNNING' : 'IDLE';
  els.stateBadge.classList.toggle('running', running);
  els.start.hidden = running;
  els.stop.hidden = !running;
  els.hint.textContent = running
    ? 'Running at ' + Math.round(s.setpoint) + UNITS[units] + '. Adjust the target any time.'
    : 'Set a target temperature (' + MIN + '\u2013' + MAX + UNITS[units] + '), then press Start.';
}

// ---------------------------------------------------------------- history + diagnostics
function addState(s) {
  const p = s.pidstats || {};
  if (p.time == null || p.ispoint == null) return;   // skip incomplete/empty pidstats
  history.push({
    t: p.time,
    temp: p.ispoint,
    target: p.setpoint,
    err: p.ispoint - p.setpoint,
    heat: p.out != null ? p.out * 100 : s.heat,
    p: p.p,
    i: p.i,
    d: p.d,
  });
  if (history.length > MAX_HISTORY) history.splice(0, history.length - MAX_HISTORY);
}

function avgError(windowSecs) {
  const n = history.length;
  if (!n) return null;
  const cutoff = history[n - 1].t - windowSecs;
  let sum = 0, count = 0;
  for (let i = n - 1; i >= 0 && history[i].t >= cutoff; i--) {
    if (history[i].err == null) continue;
    sum += history[i].err;
    count++;
  }
  return count ? sum / count : null;
}

function updateErrorStats() {
  if (!history.length) return;
  const last = history[history.length - 1];
  els.errorNow.textContent = last.err != null ? fmt(last.err) : '--';
  const parts = [60, 300, 900].map(avgError).map(v => (v == null ? '--' : fmt(v)));
  els.errorAvg.textContent = parts.join(' / ');
}

function fmt(v) {
  const n = Number(v);
  return (n > 0 ? '+' : '') + n.toFixed(1);
}

function renderTable() {
  const rows = history.slice(-TABLE_ROWS).reverse();
  els.tableBody.innerHTML = rows.map(r => {
    const time = new Date(r.t * 1000).toLocaleTimeString();
    return '<tr>' +
      '<td>' + time + '</td>' +
      '<td>' + Math.round(r.target) + '</td>' +
      '<td>' + Math.round(r.temp) + '</td>' +
      '<td>' + (r.err != null ? fmt(r.err) : '--') + '</td>' +
      '<td>' + (r.p != null ? r.p.toFixed(1) : '--') + '</td>' +
      '<td>' + (r.i != null ? r.i.toFixed(1) : '--') + '</td>' +
      '<td>' + (r.d != null ? r.d.toFixed(1) : '--') + '</td>' +
      '<td>' + Math.round(r.heat) + '</td>' +
      '</tr>';
  }).join('');
}

function refresh() {
  redrawCharts();
  updateErrorStats();
  renderTable();
}

// ---------------------------------------------------------------- status socket
let statusSocket;

function connectStatus() {
  statusSocket = new WebSocket(wsUrl('/status'));

  statusSocket.onopen = () => setConnection(true);
  statusSocket.onclose = () => {
    setConnection(false);
    setTimeout(connectStatus, 3000);
  };

  statusSocket.onmessage = e => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'backlog') {
      if (msg.units) units = msg.units;
      (msg.log || []).forEach(addState);
      if (msg.state) {
        if (msg.state.state === 'RUNNING') addState(msg.state);
        updateUi(msg.state);
      }
      refresh();
      return;
    }
    if (msg.state === 'RUNNING') addState(msg);
    updateUi(msg);
    refresh();
  };
}

function setConnection(online) {
  els.connection.classList.toggle('online', online);
  els.connection.classList.toggle('offline', !online);
  els.connectionText.textContent = online ? 'connected' : 'offline';
}

// ---------------------------------------------------------------- control socket
let controlSocket;
let controlQueue = [];

function connectControl() {
  controlSocket = new WebSocket(wsUrl('/control'));
  controlSocket.onopen = () => flushControlQueue();
  controlSocket.onclose = () => setTimeout(connectControl, 3000);
}

function sendControl(msg) {
  if (controlSocket && controlSocket.readyState === WebSocket.OPEN) {
    controlSocket.send(JSON.stringify(msg));
  } else {
    controlQueue.push(msg);
  }
}

function flushControlQueue() {
  while (controlQueue.length && controlSocket && controlSocket.readyState === WebSocket.OPEN) {
    controlSocket.send(JSON.stringify(controlQueue.shift()));
  }
}

// ---------------------------------------------------------------- setpoint controls
function clamp(value) {
  return Math.min(MAX, Math.max(MIN, Math.round(value / 5) * 5));
}

function syncInputs(value) {
  els.slider.value = value;
  els.input.value = value;
}

function applySetpoint(value) {
  const v = clamp(value);
  syncInputs(v);
  els.setpoint.textContent = Math.round(v);
  sendControl({ cmd: 'SET_TEMP', setpoint: v });
  return v;
}

els.slider.addEventListener('input', () => { els.input.value = els.slider.value; });
els.slider.addEventListener('change', () => applySetpoint(parseFloat(els.slider.value)));
els.input.addEventListener('input', () => { els.slider.value = els.input.value; });
els.input.addEventListener('change', () => applySetpoint(parseFloat(els.input.value || MIN)));

// ---------------------------------------------------------------- chart span
function spanLabel(m) {
  return m >= SPAN_MAX ? 'All' : m + ' min';
}

function applyTimeSpan(minutes) {
  const m = Math.min(SPAN_MAX, Math.max(SPAN_MIN, Math.round(parseFloat(minutes) || SPAN_DEFAULT / 60)));
  els.timeSpan.value = m;
  els.timeSpanVal.textContent = spanLabel(m);
  timeSpanSecs = m >= SPAN_MAX ? 0 : m * 60;
  redrawCharts();
}

els.timeSpan.addEventListener('input', () => {
  els.timeSpanVal.textContent = spanLabel(parseInt(els.timeSpan.value, 10) || SPAN_MIN);
});
els.timeSpan.addEventListener('change', () => applyTimeSpan(els.timeSpan.value));

// ---------------------------------------------------------------- start / stop
els.start.addEventListener('click', () => {
  const setpoint = applySetpoint(parseFloat(els.input.value || MIN));
  sendControl({ cmd: 'RUN', setpoint: setpoint });
});

els.stop.addEventListener('click', () => {
  sendControl({ cmd: 'STOP' });
});

// ---------------------------------------------------------------- csv export
els.csv.addEventListener('click', () => {
  const header = 'time,target,temp,error,heat,p,i,d';
  const lines = history.map(r =>
    [new Date(r.t * 1000).toISOString(), r.target, r.temp,
     r.err, r.heat, r.p, r.i, r.d].join(','));
  const blob = new Blob([header + '\n' + lines.join('\n')], { type: 'text/csv' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'smoker-state.csv';
  a.click();
  URL.revokeObjectURL(a.href);
});

// ---------------------------------------------------------------- init
connectStatus();
connectControl();
