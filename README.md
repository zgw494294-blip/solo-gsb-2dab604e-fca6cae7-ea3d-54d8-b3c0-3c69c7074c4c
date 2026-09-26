# 直流电路网表求解器

一个用 **Python + Flask + NumPy + 原生 JavaScript** 实现的直流电路稳态分析网页应用。
用户在文本框中逐行输入网表，提交后服务器用**改进节点分析（MNA）**求解，
页面显示各节点电压和各元件按“起点 → 终点”正方向的电流。

## 网表格式

每行一个元件，字段以空白分隔：

```
名称 起点 终点 数值
```

| 名称首字母 | 元件类型 | 单位 | 说明 |
|---|---|---|---|
| `R` / `r` | 电阻 | Ω | 阻值必须为正 |
| `V` / `v` | 理想电压源 | V | 起点电位 − 终点电位 = 数值 |
| `I` / `i` | 理想电流源 | A | 电流正方向为 起点 → 终点 |

规则：

- 节点为 0 及以上的整数，**节点 0 为地**；起点与终点不能相同。
- 名称不得重复（不区分大小写），其余字符限字母、数字、下划线。
- 最多 **12 个非接地节点**、**30 个元件**。
- 空行与 `#` 开头的行视为注释，被忽略。
- 格式或数值非法、电路无唯一解（如悬空节点、电压源回路矛盾等）时，
  页面会显示具体原因，且**输入内容保留**，可直接修改后重新提交。

示例：

```
# 分压器 + 电流源
V1 1 0 10
R1 1 2 1000
R2 2 0 2000
I1 0 3 0.005
R3 3 0 1000
```

## 启动（Docker，单条命令）

```bash
docker compose up --build
```

然后在浏览器访问：**http://localhost:8080**

（容器内服务监听 8000 端口，Compose 将其映射到宿主机的 8080 端口。）

也可以不用 Compose：

```bash
docker build -t dc-solver . && docker run --rm -p 8080:8000 dc-solver
```

## 本地开发（不用 Docker）

```bash
pip install -r requirements.txt
python app.py
```

然后访问 **http://localhost:8000**。

## 求解方法

采用改进节点分析（Modified Nodal Analysis）：

- 未知量为各非接地节点电压，以及每个理想电压源的支路电流（正方向：起点 → 终点）。
- 对每个非接地节点列 KCL 方程；对每个电压源补充约束方程
  `V(起点) − V(终点) = 数值`。
- 用 NumPy 求解线性方程组；系数矩阵奇异或残差过大时判定为无唯一解并说明原因。

## 项目结构

```
├── app.py               # Flask 后端：网表解析 + MNA 求解 + API
├── templates/index.html # 页面模板
├── static/app.js        # 原生 JS：提交网表、渲染结果
├── static/style.css     # 样式
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## API

`POST /api/solve`，请求体 `{"netlist": "..."}`。

成功返回：

```json
{
  "ok": true,
  "nodes": [{"node": 1, "voltage": "10"}, ...],
  "elements": [{"name": "R1", "type": "R", "n1": 1, "n2": 2,
                "value": "1000", "current": "0.00333333"}, ...]
}
```

失败返回 `{"ok": false, "error": "具体原因"}`。
