"""直流电路网表求解器（改进节点分析 MNA）。

网表格式（每行一个元件）：
    名称 起点 终点 数值
- 名称以 R/r 开头：电阻，单位欧姆，数值必须为正
- 名称以 V/v 开头：理想电压源，单位伏特，起点电位 - 终点电位 = 数值
- 名称以 I/i 开头：理想电流源，单位安培，正方向为起点 -> 终点
- 节点 0 为地；空行与 # 开头的行被忽略
"""

import math
import re

import numpy as np
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
app.json.ensure_ascii = False

MAX_NODES = 12       # 非接地节点数上限
MAX_ELEMENTS = 30    # 元件数上限
MAX_LINES = 200      # 网表最大行数（含空行/注释）
MAX_NETLIST_CHARS = 20000

NAME_RE = re.compile(r"^[RVIrvi][A-Za-z0-9_]*$")
NODE_RE = re.compile(r"^\d{1,9}$")


class NetlistError(Exception):
    """网表格式/数值非法，或电路无唯一解。"""


class Element:
    __slots__ = ("name", "etype", "n1", "n2", "value")

    def __init__(self, name, etype, n1, n2, value):
        self.name = name
        self.etype = etype  # 'R' / 'V' / 'I'
        self.n1 = n1
        self.n2 = n2
        self.value = value


def parse_netlist(text):
    """解析网表文本，返回 (elements, sorted_non_ground_nodes)。失败抛出 NetlistError。"""
    lines = text.splitlines()
    if len(lines) > MAX_LINES:
        raise NetlistError(f"网表行数 {len(lines)} 超过上限 {MAX_LINES}")

    elements = []
    seen = set()
    for lineno, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 4:
            raise NetlistError(
                f"第 {lineno} 行：格式应为“名称 起点 终点 数值”共 4 个字段，"
                f"实际为 {len(parts)} 个"
            )
        name, s1, s2, sval = parts

        if not NAME_RE.match(name):
            raise NetlistError(
                f"第 {lineno} 行：名称“{name}”非法，须以 R/V/I 开头，"
                "其余字符只能是字母、数字或下划线"
            )
        key = name.lower()
        if key in seen:
            raise NetlistError(f"第 {lineno} 行：元件名称“{name}”与前面重复")
        seen.add(key)

        for label, s in (("起点", s1), ("终点", s2)):
            if not NODE_RE.match(s):
                raise NetlistError(
                    f"第 {lineno} 行：{label}“{s}”非法，节点须为 0 及以上的整数（0 为地）"
                )
        n1, n2 = int(s1), int(s2)
        if n1 == n2:
            raise NetlistError(f"第 {lineno} 行：{name} 的起点与终点不能相同")

        try:
            value = float(sval)
        except ValueError:
            raise NetlistError(f"第 {lineno} 行：数值“{sval}”不是合法数字")
        if not math.isfinite(value):
            raise NetlistError(f"第 {lineno} 行：{name} 的数值必须是有限值")

        etype = name[0].upper()
        if etype == "R" and value <= 0:
            raise NetlistError(f"第 {lineno} 行：电阻 {name} 的阻值必须为正数")

        elements.append(Element(name, etype, n1, n2, value))

    if not elements:
        raise NetlistError("网表为空：请至少输入一个元件")
    if len(elements) > MAX_ELEMENTS:
        raise NetlistError(f"元件数量 {len(elements)} 超过上限 {MAX_ELEMENTS}")

    nodes = sorted({n for e in elements for n in (e.n1, e.n2) if n != 0})
    if len(nodes) > MAX_NODES:
        raise NetlistError(f"非接地节点数 {len(nodes)} 超过上限 {MAX_NODES}")

    return elements, nodes


def solve(elements, nodes):
    """改进节点分析求解。返回 (节点电压 dict, 元件电流 list)。失败抛出 NetlistError。"""
    idx = {node: i for i, node in enumerate(nodes)}
    n = len(nodes)
    vsources = [e for e in elements if e.etype == "V"]
    m = len(vsources)
    size = n + m

    A = np.zeros((size, size))
    z = np.zeros(size)

    for e in elements:
        a = idx.get(e.n1)  # 节点 0（地）不在未知量中，get 返回 None
        b = idx.get(e.n2)
        if e.etype == "R":
            g = 1.0 / e.value
            if a is not None:
                A[a, a] += g
            if b is not None:
                A[b, b] += g
            if a is not None and b is not None:
                A[a, b] -= g
                A[b, a] -= g
        elif e.etype == "I":
            # 电流源正方向为 起点 -> 终点
            if a is not None:
                z[a] -= e.value
            if b is not None:
                z[b] += e.value

    # 电压源：起点电位 - 终点电位 = 数值；附加未知量为其电流（起点 -> 终点）
    for k, e in enumerate(vsources):
        a = idx.get(e.n1)
        b = idx.get(e.n2)
        row = n + k
        if a is not None:
            A[a, row] += 1.0
            A[row, a] += 1.0
        if b is not None:
            A[b, row] -= 1.0
            A[row, b] -= 1.0
        z[row] = e.value

    no_unique = (
        "电路无唯一解（方程组奇异）。常见原因：存在只接电流源的悬空节点、"
        "与地完全隔离的子电路、电压源构成回路（取值矛盾或冗余）、"
        "或电流源割集电流之和不满足基尔霍夫定律"
    )
    try:
        x = np.linalg.solve(A, z)
    except np.linalg.LinAlgError:
        raise NetlistError(no_unique)

    if not np.all(np.isfinite(x)):
        raise NetlistError(no_unique)
    # 残差校验，排除接近奇异导致的数值垃圾
    residual = np.linalg.norm(A @ x - z, ord=np.inf)
    scale = max(1.0, np.linalg.norm(z, ord=np.inf),
                np.linalg.norm(A, ord=np.inf) * np.linalg.norm(x, ord=np.inf))
    if residual > 1e-6 * scale:
        raise NetlistError(no_unique)

    voltages = {node: x[idx[node]] for node in nodes}

    def v(node):
        return 0.0 if node == 0 else voltages[node]

    currents = []
    vk = 0
    for e in elements:
        if e.etype == "R":
            cur = (v(e.n1) - v(e.n2)) / e.value
        elif e.etype == "V":
            cur = x[n + vk]
            vk += 1
        else:  # 电流源：电流即其数值
            cur = e.value
        currents.append((e, cur))

    return voltages, currents


def fmt(value):
    """格式化为最多 6 位有效数字，消除 -0 与极小的数值噪声。"""
    if abs(value) < 1e-12:
        value = 0.0
    return f"{value:.6g}"


def solve_netlist(text):
    """求解网表文本，返回可 JSON 序列化的结果 dict。"""
    elements, nodes = parse_netlist(text)
    voltages, currents = solve(elements, nodes)
    return {
        "ok": True,
        "nodes": [{"node": node, "voltage": fmt(voltages[node])} for node in nodes],
        "elements": [
            {
                "name": e.name,
                "type": e.etype,
                "n1": e.n1,
                "n2": e.n2,
                "value": fmt(e.value),
                "current": fmt(cur),
            }
            for e, cur in currents
        ],
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/solve", methods=["POST"])
def api_solve():
    data = request.get_json(silent=True)
    if not data or not isinstance(data.get("netlist"), str):
        return jsonify({"ok": False, "error": "请求格式错误：需要 JSON 字段 netlist"}), 400
    netlist = data["netlist"]
    if len(netlist) > MAX_NETLIST_CHARS:
        return jsonify({"ok": False,
                        "error": f"网表长度超过上限 {MAX_NETLIST_CHARS} 字符"}), 400
    try:
        return jsonify(solve_netlist(netlist))
    except NetlistError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
