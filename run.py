from flask import Flask, render_template, request, Response, jsonify
from query_from_db import QueryDB
from insert2db import insert_news_to_db
import threading
import time
import json

app = Flask(__name__)

# 初始化查询引擎
query_engine = QueryDB()

# 标记数据收集任务是否正在运行
is_collecting = False

def scheduled_data_collection():
    """
    定时任务：每24小时自动执行一次数据收集
    """
    global is_collecting
    print("⏳ 定时数据收集服务已启动，正在进行首次 24 小时倒计时...")
    time.sleep(24 * 60 * 60)

    while True:
        try:
            print("⏰ 定时任务触发：开始数据收集...")
            is_collecting = True
            insert_news_to_db()
            print("✅ 定时数据收集完成")
            is_collecting = False
        except Exception as e:
            print(f"❌ 定时数据收集失败: {e}")
            is_collecting = False
        # 等待24小时
        time.sleep(24 * 60 * 60)

# 启动定时任务线程
threading.Thread(target=scheduled_data_collection, daemon=True).start()

@app.route('/')
def index():
    """
    基础函数：渲染主页面
    """
    return render_template('main.html')

@app.route('/query', methods=['POST'])
def query():
    """
    查询函数：调用查询引擎，返回流式输出和检索到的节点
    """
    data = request.get_json()
    user_input = data.get('query', '')
    
    if not user_input:
        return jsonify({'error': '查询内容不能为空'}), 400
        
    def generate():
        print("🔍 正在检索知识图谱...")
        # 修正核心: query_with_nodes 返回的第一个变量 unique_facts 就是规范化后的点和边列表
        # 第二个变量是包含了大模型 stream=True 的原始文本生成器对象
        unique_facts, answer_stream = query_engine.query_with_nodes(user_input)
        
        # 🚀 瞬间把清洗去重后的图谱节点（unique_facts）发送给前端去画列表/拓扑
        # 将 type 统一改为 'nodes' 方便前端直观匹配
        print("🚀 图谱拓扑提取成功，正在秒级泵出节点数据...")
        nodes_json = json.dumps({'type': 'nodes', 'data': unique_facts}, ensure_ascii=False)
        yield f"data: {nodes_json}\n\n"
        
        # 🧠 紧接着无缝消费大模型的流式正文
        print("🧠 正在启动大模型流式推理...")
        for chunk in answer_stream:
            answer_json = json.dumps({'type': 'answer', 'data': chunk}, ensure_ascii=False)
            yield f"data: {answer_json}\n\n"
            
        print("🏁 全链路真流式数据泵出完毕。")
            
    return Response(generate(), mimetype='text/event-stream')

@app.route('/collect_data', methods=['POST'])
def collect_data():
    """
    数据收集函数：手动触发数据收集
    """
    global is_collecting
    
    if is_collecting:
        return jsonify({'status': 'running', 'message': '数据收集任务正在进行中...'}), 200
    
    def do_collect():
        global is_collecting
        try:
            is_collecting = True
            insert_news_to_db()
            print("✅ 手动触发数据收集完成")
        except Exception as e:
            print(f"❌ 手动触发数据收集失败: {e}")
        finally:
            is_collecting = False
    
    # 在后台线程中执行数据收集
    threading.Thread(target=do_collect, daemon=True).start()
    
    return jsonify({'status': 'started', 'message': '数据收集任务已启动'}), 200

@app.route('/collect_status', methods=['GET'])
def collect_status():
    """
    查询数据收集任务状态
    """
    return jsonify({'is_collecting': is_collecting}), 200

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000)
