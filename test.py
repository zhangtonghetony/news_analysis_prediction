# import urllib
# params = urllib.parse.urlencode({'key':'734c11f5b3fb43fbabbfa3979c13440c','num':'10'})
# print(params)

# for i in range(0,50,25):
#     print(i)


# result=list(zip([1,2,3],[4,5,6]))
# for a,b in result:
#     print(a,b,end=' ')

# for a,b in zip([1,2,3],[4,5,6]):
#     print(a,b,end=' ')

import requests
import json
from config import config

def inspect_embedding_data():
    # 组装基础 URL
    graph_url = config['graph_url']
    graph_port = config['graph_port']
    graph_name = config['graph_name']
    base_url = f"http://{graph_url}:{graph_port}/graphs/{graph_name}"
    
    # 1. 捞取前 1 个节点
    v_url = f"{base_url}/graph/vertices?limit=1"
    
    try:
        response = requests.get(v_url)
        if response.status_code != 200:
            print(f"❌ 无法连接图数据库，HTTP 状态码: {response.status_code}")
            return
            
        vertices = response.json().get("vertices", [])
        if not vertices:
            print("⚠️ 数据库里目前是个空库，没有点可供测试，请先确保跑过清洗脚本入库！")
            return
            
        # 2. 抓出第一个顶点的属性
        test_vertex = vertices[0]
        props = test_vertex.get("properties", {})
        
        # 兼容一下你昨晚可能命名的两个字段名
        emb_data = props.get("embeddings") or props.get("embedding")
        
        print("\n================ 🔬 属性探测报告 🔬 ================\n")
        print(f"节点 ID: {test_vertex.get('id')}")
        print(f"节点 Label: {test_vertex.get('label')}")
        print(f"节点 Name: {props.get('name', '未知')}")
        print("-" * 50)
        
        if emb_data is None:
            print("❌ 警告：该节点的属性中没有找到 'embeddings' 或 'embedding' 字段！")
            print(f"当前节点的所有可用属性为: {list(props.keys())}")
            return
            
        # 3. 核心大招：打印其在 Python 里的真实类型
        data_type = type(emb_data)
        print(f"📊 数据库吐出来的原始数据类型为: {data_type}")
        
        # 4. 根据类型进行差异化展示和长度测试
        if isinstance(emb_data, str):
            print("🟢 结论：它是个【字符串 (String)】。")
            print(f"原始字符串前100个字符: {emb_data[:100]}...")
            
            # 尝试人肉反序列化，看看能不能还原
            try:
                # 检查它是符合 JSON 规范的 "[-0.04, ...]" 还是纯用逗号拼接的 "-0.04,..."
                if not emb_data.startswith('['):
                    # 如果没有方括号，我们人肉给它补上或者用 split
                    parsed_list = [float(x) for x in emb_data.split(',') if x.strip()]
                else:
                    parsed_list = json.loads(emb_data)
                    
                print(f"🎉 反序列化测试成功！将其转换为 List 后，向量的真实长度为: {len(parsed_list)} 维")
            except Exception as parse_err:
                print(f"💥 尝试反序列化为列表时失败，错误原因: {parse_err}")
                
        elif isinstance(emb_data, list):
            print("🔵 结论：它是个原生的【列表 (List)】。")
            print(f"向量的维度长度为: {len(emb_data)} 维")
            print(f"前 3 个元素为: {emb_data[:3]}")
            
        else:
            print(f"🟡 奇怪的未知类型: {data_type}，具体内容为: {emb_data}")

    except Exception as e:
        print(f"❌ 脚本执行过程中发生异常: {e}")

if __name__ == "__main__":
    inspect_embedding_data()
