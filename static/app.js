'use strict';

const KIND_LABELS = { R: '电阻', V: '电压源', I: '电流源' };

const EXAMPLE_NETLIST = [
  '# 示例：含电压源与电流源的直流电路',
  'V1 1 0 12',
  'R1 1 2 6',
  'R2 2 0 6',
  'R3 2 3 12',
  'I1 0 3 0.5',
].join('\n');

const netlistEl = document.getElementById('netlist');
const solveBtn = document.getElementById('solve-btn');
const exampleBtn = document.getElementById('example-btn');
const clearBtn = document.getElementById('clear-btn');
const errorEl = document.getElementById('error');
const resultsEl = document.getElementById('results');
const voltageTbody = document.querySelector('#voltage-table tbody');
const currentTbody = document.querySelector('#current-table tbody');

// 数值格式化：去掉无意义的尾零，极大/极小值用科学计数法
function fmt(x) {
  if (typeof x !== 'number' || !Number.isFinite(x)) return String(x);
  if (Math.abs(x) < 1e-12) return '0';
  const a = Math.abs(x);
  if (a >= 1e6 || a < 1e-4) return x.toExponential(4);
  return String(Number(x.toPrecision(6)));
}

function showError(message) {
  errorEl.textContent = message;
  errorEl.hidden = false;
  resultsEl.hidden = true;
}

function clearError() {
  errorEl.hidden = true;
  errorEl.textContent = '';
}

function addRow(tbody, cells) {
  const tr = document.createElement('tr');
  for (const { text, isNum } of cells) {
    const td = document.createElement('td');
    td.textContent = text;
    if (isNum) td.className = 'num';
    tr.appendChild(td);
  }
  tbody.appendChild(tr);
}

function renderResults(data) {
  voltageTbody.textContent = '';
  currentTbody.textContent = '';

  addRow(voltageTbody, [
    { text: '0（地）' },
    { text: '0', isNum: true },
  ]);
  for (const item of data.node_voltages) {
    addRow(voltageTbody, [
      { text: String(item.node) },
      { text: fmt(item.voltage), isNum: true },
    ]);
  }

  for (const item of data.currents) {
    addRow(currentTbody, [
      { text: item.name },
      { text: KIND_LABELS[item.kind] || item.kind },
      { text: `${item.from} → ${item.to}` },
      { text: fmt(item.current), isNum: true },
    ]);
  }

  resultsEl.hidden = false;
}

async function solve() {
  clearError();
  solveBtn.disabled = true;
  try {
    const resp = await fetch('/solve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ netlist: netlistEl.value }),
    });
    let data;
    try {
      data = await resp.json();
    } catch {
      showError(`服务器返回异常（HTTP ${resp.status}）`);
      return;
    }
    // 出错时仅提示原因，输入内容保留在文本框中
    if (!data.ok) {
      showError(data.error || '求解失败');
      return;
    }
    renderResults(data);
  } catch {
    showError('无法连接服务器，请检查服务是否正常运行');
  } finally {
    solveBtn.disabled = false;
  }
}

solveBtn.addEventListener('click', solve);
exampleBtn.addEventListener('click', () => {
  netlistEl.value = EXAMPLE_NETLIST;
  clearError();
});
clearBtn.addEventListener('click', () => {
  netlistEl.value = '';
  clearError();
  resultsEl.hidden = true;
  netlistEl.focus();
});
netlistEl.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') solve();
});
