import requests
import urllib.parse
import json

# ==================== 1. 请在下方填写你的测试配置 ====================
GRAPH_HOST = "127.0.0.1"
GRAPH_PORT = "8080"
GRAPH_NAME = "hugegraph"
SEED_ID = "11:俄罗斯"  # 确保这个节点在你的数据库里存在
# ====================================================================

BASE_URL = f"http://{GRAPH_HOST}:{GRAPH_PORT}/graphs/{GRAPH_NAME}"

def test_rest_traversal(seed_id: str):
    print(f"🚀 开始测试 Python 端两步遍历逻辑...")
    print(f"种子节点: {seed_id}")
    
    # 编码 ID
    encoded_id = urllib.parse.quote(f'"{seed_id}"', safe="")
    
    # 1. 第一步：获取与种子节点相关的所有边
    # 接口: GET /graphs/{graph}/graph/edges?vertex_id=...
    edge_url = f"{BASE_URL}/graph/edges?vertex_id={encoded_id}&direction=BOTH"
    
    try:
        print(f"正在获取节点关联边: {edge_url}")
        resp = requests.get(edge_url, timeout=5)
        
        if resp.status_code != 200:
            print(f"❌ 获取边失败 (状态码: {resp.status_code}): {resp.text}")
            return
            
        edges = resp.json().get("edges", [])
        print(f"✅ 成功获取到 {len(edges)} 条关联边。")
        if edges:
            print(f"🔥 原始边数据样例 (第一条): {json.dumps(edges[0], ensure_ascii=False, indent=2)}")
        
        # 2. 第二步：遍历边
        for edge in edges:
            # 💡 调试重点：检查这个边对象里到底有没有 source_id 和 target_id
            # 有些版本里，它们是 edge.get('source_id')，有些可能是 edge.get('outV') 或其他
            s_id = edge.get("source_id")
            t_id = edge.get("target_id")
            
            # 如果这里是 None，说明字段名不对，我们得根据 print 出来的内容修改 key
            if not t_id or not s_id:
                print(f"❌ 关键字段缺失！当前边数据: {edge}")
                continue
        
        # 2. 第二步：遍历边，捞出邻居节点详情
        for edge in edges:
            target_id = edge.get("target_id") if edge.get("source_id") == seed_id else edge.get("source_id")
            
            # 接口: GET /graphs/{graph}/graph/vertices/{id}
            node_url = f"{BASE_URL}/graph/vertices/{urllib.parse.quote(f'\"{target_id}\"', safe='')}"
            node_resp = requests.get(node_url, timeout=5)
            
            if node_resp.status_code == 200:
                node_data = node_resp.json()
                print(f"🔗 发现邻居: {target_id} | 类型: {node_data.get('label')}")
            else:
                print(f"⚠️ 无法获取节点详情: {target_id}")
                
    except Exception as e:
        print(f"💥 测试发生异常: {e}")

if __name__ == "__main__":
    test_rest_traversal(SEED_ID)