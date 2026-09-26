"""直流电路网表的解析、校验与改进节点分析（MNA）求解。

网表格式（每行一个元件，# 开头为注释）：
    名称 起点 终点 数值
    R 开头：电阻，单位欧姆，数值必须为正
    V 开头：理想电压源，单位伏特，规定 起点电位 - 终点电位 = 数值
    I 开头：理想电流源，单位安培，正方向为起点 -> 终点
节点 0 为接地节点。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

import numpy as np

GROUND = 0              # 接地节点编号
MAX_NODES = 12          # 非接地节点数上限
MAX_ELEMENTS = 30       # 元件数上限
MAX_NODE_ID = 1_000_000  # 节点编号上限（防止无意义输入）
MAX_NAME_LEN = 16       # 元件名称长度上限

_NAME_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_]*$')
VALID_KINDS = ('R', 'V', 'I')


class NetlistError(Exception):
    """网表格式或数值非法。"""


class NoUniqueSolutionError(Exception):
    """电路约束导致不存在唯一解。"""


@dataclass
class Element:
    name: str
    kind: str   # 'R' / 'V' / 'I'
    n1: int     # 起点
    n2: int     # 终点
    value: float


def _parse_node(token: str, lineno: int) -> int:
    try:
        node = int(token, 10)
    except ValueError:
        raise NetlistError(
            f'第 {lineno} 行：节点编号 "{token}" 非法，应为非负整数') from None
    if node < 0:
        raise NetlistError(f'第 {lineno} 行：节点编号 {node} 非法，应为非负整数')
    if node > MAX_NODE_ID:
        raise NetlistError(f'第 {lineno} 行：节点编号 {node} 过大（上限 {MAX_NODE_ID}）')
    return node


def parse_netlist(text: str) -> tuple[list[Element], list[int]]:
    """解析并校验网表，返回 (元件列表, 排序后的非接地节点列表)。"""
    elements: list[Element] = []
    seen: dict[str, int] = {}  # 小写名称 -> 首次出现的行号

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split()
        if len(parts) != 4:
            raise NetlistError(
                f'第 {lineno} 行：每行应为 4 个字段「名称 起点 终点 数值」，'
                f'实际为 {len(parts)} 个')
        name, tok_n1, tok_n2, tok_val = parts

        if len(name) > MAX_NAME_LEN or not _NAME_RE.match(name):
            raise NetlistError(
                f'第 {lineno} 行：名称 "{name}" 非法，应以字母开头，'
                f'仅含字母、数字、下划线，且不超过 {MAX_NAME_LEN} 个字符')
        kind = name[0].upper()
        if kind not in VALID_KINDS:
            raise NetlistError(
                f'第 {lineno} 行：名称 "{name}" 应以 R（电阻）、V（电压源）'
                f'或 I（电流源）开头')
        key = name.lower()
        if key in seen:
            raise NetlistError(
                f'第 {lineno} 行：名称 "{name}" 与第 {seen[key]} 行的元件重复')
        seen[key] = lineno

        n1 = _parse_node(tok_n1, lineno)
        n2 = _parse_node(tok_n2, lineno)
        if n1 == n2:
            raise NetlistError(
                f'第 {lineno} 行：{name} 的起点与终点相同（均为节点 {n1}），不允许')

        try:
            value = float(tok_val)
        except ValueError:
            raise NetlistError(
                f'第 {lineno} 行：数值 "{tok_val}" 不是合法的浮点数') from None
        if not math.isfinite(value):
            raise NetlistError(f'第 {lineno} 行：数值 "{tok_val}" 必须为有限值')
        if kind == 'R' and value <= 0:
            raise NetlistError(
                f'第 {lineno} 行：电阻 {name} 的阻值必须为正数（当前为 {value}）')

        elements.append(Element(name=name, kind=kind, n1=n1, n2=n2, value=value))

    if not elements:
        raise NetlistError('网表为空：请至少输入一个元件')
    if len(elements) > MAX_ELEMENTS:
        raise NetlistError(
            f'元件数量为 {len(elements)} 个，超过上限 {MAX_ELEMENTS} 个')

    nodes = sorted({n for e in elements for n in (e.n1, e.n2)} - {GROUND})
    if len(nodes) > MAX_NODES:
        raise NetlistError(
            f'非接地节点数量为 {len(nodes)} 个，超过上限 {MAX_NODES} 个')
    return elements, nodes


class _UnionFind:
    """并查集，用于电路拓扑检查。"""

    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def find(self, x: int) -> int:
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: int, b: int) -> None:
        self.parent[self.find(a)] = self.find(b)

    def connected(self, a: int, b: int) -> bool:
        return self.find(a) == self.find(b)


def _check_unique_solution(elements: list[Element], nodes: list[int]) -> None:
    """MNA 方程组有唯一解的拓扑充要条件：

    1. 每个节点都能经电阻/电压源到达地（否则电位悬浮，或存在电流源割集）；
    2. 电压源（含经地）不构成回路（否则 KVL 矛盾或回路电流不确定）。
    """
    uf = _UnionFind()
    for e in elements:
        if e.kind in ('R', 'V'):
            uf.union(e.n1, e.n2)
    floating = [nd for nd in nodes if not uf.connected(nd, GROUND)]
    if floating:
        raise NoUniqueSolutionError(
            '无唯一解：节点 {} 未通过电阻或电压源与地（节点 0）连通，'
            '电位悬浮无法确定（也可能存在仅由电流源构成的割集）'.format(
                '、'.join(map(str, floating))))

    uf_v = _UnionFind()
    for e in elements:
        if e.kind != 'V':
            continue
        if uf_v.connected(e.n1, e.n2):
            raise NoUniqueSolutionError(
                f'无唯一解：电压源 {e.name}（{e.n1}→{e.n2}）与其他电压源构成回路，'
                'KVL 相互矛盾或回路电流无法唯一确定')
        uf_v.union(e.n1, e.n2)


def solve_circuit(elements: list[Element],
                  nodes: list[int]) -> tuple[list[dict], list[dict]]:
    """用改进节点分析求解，返回 (节点电压列表, 元件电流列表)。

    元件电流的正方向均为 起点 -> 终点。
    """
    index = {nd: i for i, nd in enumerate(nodes)}
    n = len(nodes)
    vsources = [e for e in elements if e.kind == 'V']
    m = len(vsources)
    size = n + m
    A = [[0.0] * size for _ in range(size)]
    z = [0.0] * size

    # 电阻与电流源盖章
    for e in elements:
        a = index.get(e.n1)  # 接地节点不在 index 中，视为 None
        b = index.get(e.n2)
        if e.kind == 'R':
            g = 1.0 / e.value
            if a is not None:
                A[a][a] += g
            if b is not None:
                A[b][b] += g
            if a is not None and b is not None:
                A[a][b] -= g
                A[b][a] -= g
        elif e.kind == 'I':
            # 电流由起点流向终点：起点流出、终点注入
            if a is not None:
                z[a] -= e.value
            if b is not None:
                z[b] += e.value

    # 电压源盖章：附加未知量为其 起点->终点 的电流
    for k, e in enumerate(vsources):
        row = n + k
        a = index.get(e.n1)
        b = index.get(e.n2)
        if a is not None:
            A[a][row] += 1.0
            A[row][a] += 1.0
        if b is not None:
            A[b][row] -= 1.0
            A[row][b] -= 1.0
        z[row] = e.value  # V(起点) - V(终点) = 数值

    _check_unique_solution(elements, nodes)

    a_mat = np.array(A, dtype=float)
    b_vec = np.array(z, dtype=float)
    try:
        x = np.linalg.solve(a_mat, b_vec)
    except np.linalg.LinAlgError as exc:
        raise NoUniqueSolutionError(
            '无唯一解：电路方程组奇异（可能存在仅由电流源构成的割集等约束冲突）'
        ) from exc
    x = [float(v) for v in x]

    # 残差校验，防止病态矩阵给出不可靠结果
    residual = max(
        (abs(sum(A[i][j] * x[j] for j in range(size)) - z[i])
         for i in range(size)),
        default=0.0)
    scale = max(1.0, max((abs(v) for v in z), default=0.0))
    if any(not math.isfinite(v) for v in x) or residual > 1e-6 * scale:
        raise NoUniqueSolutionError('数值求解失败：电路可能无唯一解或严重病态')

    voltages = [{'node': nd, 'voltage': x[index[nd]]} for nd in nodes]

    currents = []
    k = 0
    for e in elements:
        v1 = x[index[e.n1]] if e.n1 in index else 0.0
        v2 = x[index[e.n2]] if e.n2 in index else 0.0
        if e.kind == 'R':
            cur = (v1 - v2) / e.value
        elif e.kind == 'I':
            cur = e.value
        else:  # 'V'：MNA 附加未知量即 起点->终点 电流
            cur = x[n + k]
            k += 1
        currents.append({
            'name': e.name,
            'kind': e.kind,
            'from': e.n1,
            'to': e.n2,
            'current': cur,
        })
    return voltages, currents
