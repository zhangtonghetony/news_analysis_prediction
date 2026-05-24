import requests
import json
import datetime
import random

# ================= 1. 配置 HugeGraph 基础信息 =================
BASE_URL = "http://localhost:8080"
GRAPH_NAME = "hugegraph"
HEADERS = {"Content-Type": "application/json"}

print("========= 🔗 HugeGraph 智能 Schema 兼容建边工具 (类型修复版) =========")

# ================= 2. 自动探查 Schema 字段 =================
edge_label = input("1. 请输入【边类型/Label】(直接回车默认为 related_to): ").strip() or "related_to"

print(f"\n正在尝试获取 '{edge_label}' 的数据库 Schema 字段定义...")
schema_url = f"{BASE_URL}/graphs/{GRAPH_NAME}/schema/edgelabels/{edge_label}"

valid_properties = []
try:
    res = requests.get(schema_url)
    if res.status_code == 200:
        valid_properties = res.json().get("properties", [])
        print(f"🔍 成功从数据库探测到该边允许包含的属性字段: {valid_properties}")
    else:
        print(f"⚠️ 探测失败(状态码 {res.status_code})。后端未返回字段详情。")
except Exception as e:
    print(f"⚠️ 探查接口异常 ({e})，将切换到【手动确认字段】模式。")

if not valid_properties:
    print("\n请手动指定你数据库里【实际存在】的属性字段（多个请用逗号分隔）。")
    user_fields = input("请输入真实属性列表: ").strip()
    if user_fields:
        valid_properties = [f.strip() for f in user_fields.split(",") if f.strip()]

# ================= 3. 进入建边循环 =================
print("\n" + "="*40)
print("配置就绪！现在开始连线拉边。输入 'q' 退出。")
print("="*40 + "\n")

url = f"{BASE_URL}/graphs/{GRAPH_NAME}/graph/edges"

while True:
    out_v = input("▶ 请输入【源节点 ID】(outV): ").strip()
    if out_v.lower() == 'q': break
        
    in_v = input("▶ 请输入【目标节点 ID】(inV): ").strip()
    if in_v.lower() == 'q': break

    props_payload = {}
    print("\n--- 动态收集数据库支持的属性值 ---")
    
    default_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mock_embed = [round(random.uniform(-1, 1), 4) for _ in range(4)]
    
    for field in valid_properties:
        if field == "source":
            val = input("• source (源概念名): ").strip() or "未命名源"
            props_payload["source"] = val
        elif field == "target":
            val = input("• target (目标概念名): ").strip() or "未命名目标"
            props_payload["target"] = val
        elif field == "description":
            val = input("• description (传导逻辑描述): ").strip() or "手动建立的关系链"
            props_payload["description"] = val
        elif field == "type":
            val = input("• type (关系类型分类): ").strip() or "常规关联"
            props_payload["type"] = val
        elif field == "time":
            val = input(f"• time (时间, 回车默认当前): ").strip() or default_time
            props_payload["time"] = val
            
        # 🔥 🔥 🔥 针对 score 进行强转 Int 修复 🔥 🔥 🔥
        elif field == "score":
            val = input("• score (【整数】型得分，如 9 或 95，回车默认 95): ").strip()
            if val:
                try:
                    # 先转 float 再转 int，可以完美处理输入 "9.0" 或 "9" 的情况，统一变成 9
                    props_payload["score"] = int(float(val))
                except:
                    props_payload["score"] = 95
            else:
                props_payload["score"] = 95
                
        elif field == "embedding":
            val = input("• embedding (逗号分隔数字, 回车默认生成伪向量): ").strip()
            if val:
                try: props_payload["embedding"] = [float(x.strip()) for x in val.split(",")]
                except: props_payload["embedding"] = mock_embed
            else:
                props_payload["embedding"] = mock_embed
        else:
            val = input(f"• {field} (自定义字段输入): ").strip()
            props_payload[field] = val

    # 组装 Payload
    payload = {
        "label": edge_label,
        "outV": out_v,
        "inV": in_v,
        "properties": props_payload
    }

    try:
        response = requests.post(url, headers=HEADERS, data=json.dumps(payload))
        if response.status_code in [200, 201]:
            print(f"\n✅ 【连线成功！】 ──({edge_label})──► 关系属性已成功灌入！\n")
        else:
            print(f"\n❌ 【连线失败】错误码: {response.status_code}")
            print(f"后端拒绝原因: {response.text}\n")
    except Exception as e:
        print(f"\n❌ 网络请求异常: {e}\n")

print("程序已安全退出。")