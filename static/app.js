"use strict";

const netlistEl = document.getElementById("netlist");
const solveBtn = document.getElementById("solve-btn");
const exampleBtn = document.getElementById("example-btn");
const clearBtn = document.getElementById("clear-btn");
const errorEl = document.getElementById("error");
const resultsEl = document.getElementById("results");
const nodeTbody = document.querySelector("#node-table tbody");
const elemTbody = document.querySelector("#elem-table tbody");

const EXAMPLE = [
  "# 分压器 + 电流源示例",
  "V1 1 0 10",
  "R1 1 2 1000",
  "R2 2 0 2000",
  "I1 0 3 0.005",
  "R3 3 0 1000",
].join("\n");

const TYPE_NAMES = { R: "电阻", V: "电压源", I: "电流源" };
const TYPE_UNITS = { R: "Ω", V: "V", I: "A" };

function addRow(tbody, cells) {
  const tr = document.createElement("tr");
  for (const text of cells) {
    const td = document.createElement("td");
    td.textContent = text;
    tr.appendChild(td);
  }
  tbody.appendChild(tr);
}

function showError(message) {
  errorEl.textContent = message;
  errorEl.hidden = false;
  resultsEl.hidden = true;
}

function showResults(data) {
  errorEl.hidden = true;
  nodeTbody.textContent = "";
  elemTbody.textContent = "";

  addRow(nodeTbody, ["0（地）", "0"]);
  for (const n of data.nodes) {
    addRow(nodeTbody, [String(n.node), n.voltage]);
  }
  for (const e of data.elements) {
    addRow(elemTbody, [
      e.name,
      TYPE_NAMES[e.type] || e.type,
      String(e.n1),
      String(e.n2),
      `${e.value} ${TYPE_UNITS[e.type] || ""}`,
      e.current,
    ]);
  }
  resultsEl.hidden = false;
}

async function solve() {
  solveBtn.disabled = true;
  try {
    const resp = await fetch("/api/solve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ netlist: netlistEl.value }),
    });
    const data = await resp.json();
    if (data.ok) {
      showResults(data);
    } else {
      // 出错时不清空输入框，用户可直接修改后重新提交
      showError(data.error || "未知错误");
    }
  } catch (err) {
    showError("无法连接服务器：" + err.message);
  } finally {
    solveBtn.disabled = false;
  }
}

solveBtn.addEventListener("click", solve);
exampleBtn.addEventListener("click", () => { netlistEl.value = EXAMPLE; });
clearBtn.addEventListener("click", () => {
  netlistEl.value = "";
  errorEl.hidden = true;
  resultsEl.hidden = true;
});
netlistEl.addEventListener("keydown", (ev) => {
  if ((ev.ctrlKey || ev.metaKey) && ev.key === "Enter") solve();
});
