"""solver.py 的单元测试。

本环境未安装 NumPy，因此注入一个纯 Python 的最小 numpy 替身，
仅实现 solver.py 用到的接口（array / linalg.solve / linalg.LinAlgError）。
在装有真实 NumPy 的环境中运行时，替身同样能保证接口语义一致。
"""

import sys
import types


# ---------- 最小 numpy 替身 ----------
class _LinAlgError(Exception):
    pass


def _gauss_solve(A, b):
    """高斯消元（部分主元），奇异时抛出 _LinAlgError。"""
    n = len(A)
    M = [list(A[i]) + [b[i]] for i in range(n)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-15:
            raise _LinAlgError('Singular matrix')
        M[col], M[piv] = M[piv], M[col]
        for r in range(col + 1, n):
            factor = M[r][col] / M[col][col]
            for c in range(col, n + 1):
                M[r][c] -= factor * M[col][c]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (M[i][n] - sum(M[i][j] * x[j] for j in range(i + 1, n))) / M[i][i]
    return x


def _fake_array(obj, dtype=None):
    if obj and isinstance(obj[0], (list, tuple)):
        return [list(row) for row in obj]
    return list(obj)


fake_np = types.ModuleType('numpy')
fake_np.array = _fake_array
fake_np.linalg = types.SimpleNamespace(solve=_gauss_solve, LinAlgError=_LinAlgError)
sys.modules['numpy'] = fake_np

import solver  # noqa: E402
from solver import (NetlistError, NoUniqueSolutionError, parse_netlist,  # noqa: E402
                    solve_circuit)

# ---------- 测试工具 ----------
PASSED = 0
FAILED = 0


def check(cond, label):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f'  ok  {label}')
    else:
        FAILED += 1
        print(f'FAIL  {label}')


def close(a, b, tol=1e-9):
    return abs(a - b) <= tol


def solve_text(text):
    elements, nodes = parse_netlist(text)
    return solve_circuit(elements, nodes)


def currents_by_name(currents):
    return {c['name']: c['current'] for c in currents}


def expect_error(text, exc_type, keyword, label):
    try:
        solve_text(text)
    except exc_type as exc:
        check(keyword in str(exc), f'{label}（提示包含「{keyword}」）-> {exc}')
        return
    except Exception as exc:  # noqa: BLE001
        check(False, f'{label}（抛出了错误类型 {type(exc).__name__}: {exc}）')
        return
    check(False, f'{label}（未抛出 {exc_type.__name__}）')


# ---------- 正常求解 ----------
print('== 正常求解 ==')

# 分压电路：V(1)=10, V(2)=5；R1、R2 电流均为 1A；V1 电流(1->0)为 -1A
v, c = solve_text('V1 1 0 10\nR1 1 2 5\nR2 2 0 5')
volt = {item['node']: item['voltage'] for item in v}
cur = currents_by_name(c)
check(close(volt[1], 10) and close(volt[2], 5), '分压电路节点电压')
check(close(cur['R1'], 1) and close(cur['R2'], 1), '分压电路电阻电流')
check(close(cur['V1'], -1), '电压源电流方向（起点->终点为 -1A）')

# 电流源：2A 从地注入节点 1，经 4Ω 电阻到地，V(1)=8V
v, c = solve_text('I1 0 1 2\nR1 1 0 4')
volt = {item['node']: item['voltage'] for item in v}
cur = currents_by_name(c)
check(close(volt[1], 8), '电流源电路节点电压')
check(close(cur['R1'], 2) and close(cur['I1'], 2), '电流源电路元件电流')

# 混合电路（手算：V=[12, 7.5, 13.5]，i_V1=-0.75，i_R3=-0.5）
v, c = solve_text('V1 1 0 12\nR1 1 2 6\nR2 2 0 6\nR3 2 3 12\nI1 0 3 0.5')
volt = {item['node']: item['voltage'] for item in v}
cur = currents_by_name(c)
check(close(volt[1], 12) and close(volt[2], 7.5) and close(volt[3], 13.5),
      '混合电路节点电压')
check(close(cur['V1'], -0.75) and close(cur['R1'], 0.75)
      and close(cur['R2'], 1.25) and close(cur['R3'], -0.5)
      and close(cur['I1'], 0.5), '混合电路元件电流')

# 0V 电压源相当于短路/电流表：V(1)=0，I1 的 1A 全部经 V1 流回地
v, c = solve_text('V1 1 0 0\nR1 1 0 5\nI1 0 1 1')
volt = {item['node']: item['voltage'] for item in v}
cur = currents_by_name(c)
check(close(volt[1], 0) and close(cur['V1'], 1) and close(cur['R1'], 0),
      '0V 电压源作电流表')

# 注释、空行、大小写、负值
v, c = solve_text('# 注释行\n\nr1 1 0 8\nv1 1 0 -4\ni2 0 1 -0.5\n')
volt = {item['node']: item['voltage'] for item in v}
cur = currents_by_name(c)
check(close(volt[1], -4), '小写名称与负电压源')
check(close(cur['r1'], -0.5) and close(cur['i2'], -0.5) and close(cur['v1'], 0),
      '负电流源方向')

# 电流输出顺序与输入一致
_, c = solve_text('R2 1 0 4\nR1 1 0 4\nV9 1 0 8')
check([x['name'] for x in c] == ['R2', 'R1', 'V9'], '电流结果顺序与输入一致')

# ---------- 格式 / 数值非法 ----------
print('== 格式与数值校验 ==')
expect_error('', NetlistError, '网表为空', '空网表')
expect_error('# 只有注释\n', NetlistError, '网表为空', '仅注释')
expect_error('R1 1 0', NetlistError, '4 个字段', '字段不足')
expect_error('R1 1 0 5 extra', NetlistError, '4 个字段', '字段过多')
expect_error('X1 1 0 5', NetlistError, 'R（电阻）、V（电压源）或 I（电流源）', '非法首字母')
expect_error('1R 1 0 5', NetlistError, '名称', '数字开头的名称')
expect_error('R1 x 0 5', NetlistError, '节点编号', '非法节点')
expect_error('R1 -1 0 5', NetlistError, '非负整数', '负节点编号')
expect_error('R1 1 1 5', NetlistError, '起点与终点相同', '起点终点相同')
expect_error('R1 1 0 abc', NetlistError, '浮点数', '非法数值')
expect_error('R1 1 0 1e999', NetlistError, '有限值', '无穷大数值')
expect_error('R1 1 0 nan', NetlistError, '有限值', 'NaN 数值')
expect_error('R1 1 0 0', NetlistError, '正数', '零电阻')
expect_error('R1 1 0 -5', NetlistError, '正数', '负电阻')
expect_error('R1 1 0 5\nR1 1 0 6', NetlistError, '重复', '名称重复')
expect_error('R1 1 0 5\nr1 0 1 6', NetlistError, '重复', '名称重复（大小写）')
expect_error('\n'.join(f'R{i} 1 0 {i+1}' for i in range(1, 32)),
             NetlistError, '30', '元件数超过 30')
expect_error('\n'.join(f'R{i} {i} 0 1' for i in range(1, 14)),
             NetlistError, '12', '非接地节点超过 12')

# ---------- 无唯一解 ----------
print('== 无唯一解 ==')
expect_error('R1 1 2 5\nV1 3 0 1', NoUniqueSolutionError, '悬浮', '浮动节点')
expect_error('I1 1 0 1', NoUniqueSolutionError, '悬浮', '电流源割集（悬浮）')
expect_error('R1 1 0 5\nI1 1 2 1\nI2 2 1 1', NoUniqueSolutionError, '悬浮',
             '部分节点悬浮')
expect_error('V1 1 0 5\nV2 1 0 3', NoUniqueSolutionError, '回路', '电压源并联矛盾')
expect_error('V1 1 2 5\nV2 2 3 3\nV3 1 3 8\nR1 1 0 10',
             NoUniqueSolutionError, '回路', '电压源回路')

print(f'\n通过 {PASSED} 项，失败 {FAILED} 项')
sys.exit(1 if FAILED else 0)
