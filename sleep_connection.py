import json
import requests
import os
import urllib.parse
import numpy as np
from config import config
from openai import OpenAI
from query_from_db import QueryDB
from insert2db import GraphDBHandler


class SleepConnection:
    def __init__(self, query_engine=None, db_handler=None):
        """初始化潜伏关系自动化挖掘与演进引擎"""
        self.client = OpenAI(
            api_key=config["api_key"], 
            base_url=config["base_url"]
        )
        # 依赖注入：优先使用外部传入的引擎，否则初始化默认引擎
        self.query_db = query_engine if query_engine else QueryDB()
        self.db_handler = db_handler if db_handler else GraphDBHandler()

        # 安全且精准地获取图数据库配置并拼装完整 REST 路径
        graph_host = config.get("graph_url", "127.0.0.1").strip()
        graph_port = config.get("graph_port", "8080")
        graph_name = config.get("graph_name", "hugegraph")
        
        # 如果配置里本身没带端口，则把端口和标准 REST 路径拼上去
        if ":" not in graph_host:
            graph_host = f"{graph_host}:{graph_port}/graphs/{graph_name}"
        
        # 自动补全协议头防错机制，确保 requests 库能够正常发起 HTTP 请求
        if not graph_host.startswith('http://') and not graph_host.startswith('https://'):
            graph_host = f"http://{graph_host}"
            
        self.graph_url = graph_host.rstrip('/')
        
        # 动态获取当前文件所在目录的 prompts/sleep_build.txt 路径
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.prompt_path = os.path.join(current_dir, "prompts", "sleep_build.txt")

    def _load_prompt_template(self) -> str:
        """内部辅助方法：加载外部 Prompt 模板"""
        if not os.path.exists(self.prompt_path):
            raise FileNotFoundError(f"找不到指定的 Prompt 提示词文件: {self.prompt_path}")
        with open(self.prompt_path, "r", encoding="utf-8") as f:
            return f.read()

    def _relation_embedding(self, relations: list[dict], source_weight: float = 0.3, 
                           target_weight: float = 0.3, description_weight: float = 0.4) -> list[list[float]]:
        """
        内部辅助方法：将输出的关系列表送入向量模型进行加权向量化并归一化
        权重分配：source: 0.3, target: 0.3, description: 0.4
        """
        if not relations: 
            return []
        
        # 提取所有文本片段组装成一维列表
        texts_to_embed = [] # 一维列表，包含所有关系的 source、target、description
        for r in relations:
            texts_to_embed.extend([r.get('source', ''), r.get('target', ''), r.get('description', '')])
        
        # 分批调用 Embedding 接口（每批 8 个文本，防超出接口限制）
        all_embeddings = [] # 二维列表，包含所有关系的 source、target、description 向量
        batch_size = 8   
        for i in range(0, len(texts_to_embed), batch_size):
            batch = texts_to_embed[i:i + batch_size]
            try:
                response = self.client.embeddings.create(
                    model=config.get('embedding_model', 'text-embedding-v4'), 
                    input=batch
                )
                all_embeddings.extend([item.embedding for item in response.data])
            except Exception as e:
                print(f"[Embedding 异常] 分批向量化失败: {e}，进行零向量容错处理。")
                all_embeddings.extend([[0.0] * 1536] * len(batch))  # 容错处理，生成1536维零向量
        
        # 三合一加权合成与归一化
        result_vectors = []
        for i in range(len(relations)):
            sv = all_embeddings[3 * i]
            tv = all_embeddings[3 * i + 1]
            dv = all_embeddings[3 * i + 2]
            
            # 加权求和
            weighted = [
                source_weight * s + target_weight * t + description_weight * d 
                for s, t, d in zip(sv, tv, dv)
            ]
            
            # 归一化处理
            norm = np.linalg.norm(weighted)
            if norm > 0:
                normalized_vector = (weighted / norm).tolist()
            else:
                normalized_vector = weighted
                
            result_vectors.append(normalized_vector)
            
        return result_vectors

    def _fetch_low_degree_nodes_internal(self, limit: int) -> list[dict]:
        """
        内部核心方法：完全基于 HugeGraph REST API 遍历全图顶点，
        通过实时扫描每个节点的连接边数量进行拓扑度数统计，并在内存中进行升序排序。
        """
        print("📊 [图谱遍历] 正在请求 HugeGraph 获取系统全量顶点并统计边数量...")
        try:
            # 批量拉取顶点（参考 QueryDB._vector_search 的设计）
            v_url = f"{self.graph_url}/graph/vertices?page&limit=500"
            v_response = requests.get(v_url, timeout=15)
            if v_response.status_code != 200:
                print(f"❌ [HugeGraph 错误] 顶点数据读取失败，状态码: {v_response.status_code}")
                return []
                
            all_vertices = v_response.json().get("vertices", [])
            node_degree_list = []

            # 遍历每一个节点，查询它连接的边的数量 (Degree)
            for v in all_vertices:
                vid = v.get("id")
                if not vid:
                    continue
                
                props = v.get("properties", {})
                name = props.get("name", vid)
                description = props.get("description", "暂无背景描述")
                
                try:
                    # 编码节点 ID 并请求它关联的所有边
                    encoded_id = urllib.parse.quote(f'"{vid}"', safe="")
                    edge_url = f"{self.graph_url}/graph/edges?vertex_id={encoded_id}&direction=BOTH"
                    edge_resp = requests.get(edge_url, timeout=10)
                    
                    if edge_resp.status_code == 200:
                        edges = edge_resp.json().get("edges", [])
                        degree = len(edges)  # 连着的边越少，代表越属于数据孤岛
                    else:
                        degree = 0
                except Exception as e:
                    print(f"⚠️ 统计顶点【{name}】度数时发生微小异常: {e}")
                    degree = 0

                node_degree_list.append({
                    "name": name,
                    "description": description,
                    "degree": degree
                })

            # 3. 核心算法：按连接的边数量（degree）升序排列，优先选择最少的送入大模型
            sorted_nodes = sorted(node_degree_list, key=lambda x: x["degree"])
            
            # 截取前 limit 个作为本次处理的待进化实体
            selected_nodes = sorted_nodes[:limit]
            
            print(f"📈 [拓扑分析结束] 成功扫描到 {len(node_degree_list)} 个实体。已锁定边最少的 {len(selected_nodes)} 个节点准备演进。")
            return selected_nodes

        except Exception as e:
            print(f"❌ [HugeGraph 内部排序崩溃]: {e}")
            return []

    def run_daily_evolution(self, entity_limit: int = 25):
        """
        核心主控流程：每24小时执行一次全图拓扑演进。
        基于 HugeGraph REST API 捞取已连接边较少的顶点送入大模型，加权向量化，最终全部直接落库建边。
        
        :param entity_limit: 筛选送入大模型的顶点数量（默认25个）
        """
        print(f"\n🎬 [自动演进] 开始触发 HugeGraph 节点扫描流程...")
        
        try:
            low_degree_entities = self._fetch_low_degree_nodes_internal(limit=entity_limit)
            
            if not low_degree_entities:
                print("⚠️  [自动演进] 未检索到有效顶点，本次拓扑演进中止。")
                return
                
            print(f"📦 [自动演进] 开始组装大模型上下文 (当前批次共 {len(low_degree_entities)} 个实体)...")

            # 格式化实体列表，注入Prompt 模板
            entities_text_list = [
                f"- 实体名称: {ent.get('name', '未知实体')}\n  背景描述: {ent.get('description', '暂无背景描述')}"
                for ent in low_degree_entities
            ]
            entities_text = "\n".join(entities_text_list)
            
            # 加载并渲染外部提示词模板
            template = self._load_prompt_template()
            final_prompt = template.replace("{entities_text}", entities_text)

            print("🧠 [自动演进] 正在向大模型提交批量推理请求（HugeGraph 1对多深度关联挖掘）...")
            
            # 调用大模型，开启 json_object 强约束模式
            response = self.client.chat.completions.create(
                model=config['language_model'],  
                messages=[{"role": "user", "content": final_prompt}],
                response_format={"type": "json_object"}
            )
            
            # 解析大模型吐出的标准 JSON 数据
            raw_content = response.choices[0].message.content
            json_data = json.loads(raw_content)
            
            relations = json_data.get("relations", json_data) if isinstance(json_data, dict) else json_data

            if not isinstance(relations, list) or not relations:
                print("✨ [自动演进] 大模型判定当前实体之间无需建边，演进结束。")
                return

            print(f"🔍 [自动演进] 大模型抽取到 {len(relations)} 条关系。开始执行加权复合向量合成...")

            # 关系列表批量向量化回填
            result_vectors = self._relation_embedding(relations)
            for i in range(len(relations)):
                relations[i]['embeddings'] = result_vectors[i]

            # 遍历结果，执行落库建边（包含基础防错校验）
            success_count = 0
            for rel in relations:
                source = rel.get("source", "").strip()
                target = rel.get("target", "").strip()
                relation_type = rel.get("relation_type", "潜在关联").strip()
                score = float(rel.get("score", rel.get("confidence", 0.0)))
                description = rel.get("description", "").strip()
                time_node = rel.get("time", "unknown").strip()
                embeddings = rel.get("embeddings", [])

                # 基础防错：空值过滤
                if not source or not target:
                    continue
                    
                # 基础防错：自环边拦截
                if source == target:
                    print(f"🚫 [防错拦截] 过滤自环关联: {source} -> {target}")
                    continue

                # 直接调用系统的图数据库处理器批量打入 HugeGraph
                print(f"🚀 [建边] {source} --({relation_type})--> {target}")
                
                self.db_handler.add_edge(
                    {
                        "source": source,
                        "target": target,
                        "relation_type": relation_type,
                        "description": description,
                        "time": time_node, 
                        "score": int(score),
                        "embeddings": embeddings               
                    }
                )
                success_count += 1

            print(f"✨ [自动演进成功] 本轮已成功往 HugeGraph 中激活并植入 {success_count} 条深层网状边关系。")

        except Exception as e:
            print(f"💥 [自动演进崩溃] 离线建边管道流运行异常: {e}")


if __name__ == "__main__":
    sleep_conn = SleepConnection()
    sleep_conn.run_daily_evolution()