"""Flask 入口：提供页面与 /solve 求解接口。"""

from flask import Flask, jsonify, render_template, request

from solver import (NetlistError, NoUniqueSolutionError, parse_netlist,
                    solve_circuit)

app = Flask(__name__)

# 防止异常输入撑爆内存，网表文本本身很小
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024


def solve_netlist(text: str) -> dict:
    """解析并求解网表文本，返回可 JSON 序列化的结果字典。"""
    elements, nodes = parse_netlist(text)
    voltages, currents = solve_circuit(elements, nodes)
    return {'ok': True, 'node_voltages': voltages, 'currents': currents}


@app.get('/')
def index():
    return render_template('index.html')


@app.post('/solve')
def solve():
    payload = request.get_json(silent=True) or {}
    text = payload.get('netlist', '')
    if not isinstance(text, str):
        return jsonify(ok=False, error='请求格式错误：netlist 必须是字符串'), 400
    try:
        result = solve_netlist(text)
    except (NetlistError, NoUniqueSolutionError) as exc:
        return jsonify(ok=False, error=str(exc))
    return jsonify(**result)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
