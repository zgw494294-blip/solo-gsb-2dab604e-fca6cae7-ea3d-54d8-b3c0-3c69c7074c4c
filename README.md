# 直流电路网表求解器

一个直流电路（DC）网表求解网页应用：Python + Flask + NumPy 后端，原生 JavaScript 前端。
用户在页面中逐行输入网表，提交后由**改进节点分析（MNA）**求解，显示各节点电压及各元件
按「起点 → 终点」方向的电流。

## 快速启动

### 方式一：Docker Compose（单条命令）

```bash
docker compose up --build
```

### 方式二：Docker（单条命令）

```bash
docker build -t dc-circuit-solver . && docker run --rm -p 5000:5000 dc-circuit-solver
```

### 方式三：本地 Python

```bash
pip install -r requirements.txt
python app.py
```

启动后在浏览器访问：**http://localhost:5000**（端口 **5000**）

## 网表格式

每行一个元件，字段以空白分隔：

```
名称 起点 终点 数值
```

| 名称首字母 | 元件 | 单位 | 说明 |
| --- | --- | --- | --- |
| `R` | 电阻 | Ω（欧姆） | 阻值必须为正数 |
| `V` | 理想电压源 | V（伏特） | 约定 起点电位 − 终点电位 ＝ 数值 |
| `I` | 理想电流源 | A（安培） | 正方向为 起点 → 终点 |

规则与限制：

- 节点 `0` 为接地节点，其余节点编号为任意非负整数；
- 最多 **12 个非接地节点**、**30 个元件**；
- 元件名称不得重复（不区分大小写），以字母开头，可含字母、数字、下划线；
- 同一元件的起点与终点不能相同；
- 电压源、电流源数值可为任意有限实数（含 0 与负数），电阻必须为正；
- 空行与 `#` 开头的注释行会被忽略。

示例：

```
V1 1 0 12
R1 1 2 6
R2 2 0 6
R3 2 3 12
I1 0 3 0.5
```

## 输出与错误处理

- **节点电压**：各非接地节点对地电压（节点 0 固定为 0 V）；
- **元件电流**：每个元件按「起点 → 终点」方向的电流（负值表示实际方向相反）；
- 输入格式或数值非法（字段数不对、名称重复、阻值非正、节点非法等）时，给出具体行号与原因；
- 电路无唯一解时说明原因，包括：浮动节点（未经电阻/电压源接地）、电压源构成回路
 （KVL 矛盾或电流不定）、电流源割集等；
- 出错时输入内容保留在文本框中，可直接修改后重新提交。

## 接口

`POST /solve`，请求体 `{"netlist": "<网表文本>"}`：

- 成功：`{"ok": true, "node_voltages": [{"node": 1, "voltage": ...}], "currents": [{"name": "R1", "kind": "R", "from": 1, "to": 2, "current": ...}]}`
- 失败：`{"ok": false, "error": "<原因>"}`

## 项目结构

```
├── app.py               # Flask 入口与 /solve 接口
├── solver.py            # 网表解析、校验与 MNA 求解（NumPy）
├── templates/index.html # 页面
├── static/app.js        # 前端逻辑（原生 JavaScript）
├── static/style.css     # 样式
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── test_solver.py       # 求解器单元测试（python3 test_solver.py）
```
