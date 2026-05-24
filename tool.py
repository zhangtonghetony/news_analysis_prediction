import requests

# 你的配置
base_url = "http://127.0.0.1:8080/graphs/hugegraph/schema/edgelabels"

# 我们直接向底层 schema 发送一个“更新边规则”的 PUT 请求
# 让原本存在的 subsidiary_of 强行追加 org -> org 关系
url = f"{base_url}/subsidiary_of?action=append"

data = {
    "name": "subsidiary_of",
    "source_label": "org",  # 新的起点类型
    "target_label": "org"   # 新的终点类型
}

try:
    response = requests.put(url, json=data)
    if response.status_code == 200:
        print("🎉 奇迹发生了！Python 成功强行追加了 org -> org 的连接规则！")
        print("现在回到 Hubble 刷新界面，你会发现两条规则都已经并存了。")
    else:
        print(f"追加失败，后端返回: {response.text}")
except Exception as e:
    print(f"请求发送失败: {e}")