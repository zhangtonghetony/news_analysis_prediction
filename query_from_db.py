from insert2db import graph_handler
from config import config
from openai import OpenAI
import requests
import urllib.parse
import json
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from abc import ABC, abstractmethod


class BaseQueryDB(ABC):
    """查询数据库类的抽象基类，定义所有查询数据库处理类必须遵守的接口规范"""
    def __init__(self, graph_url: str, graph_port: str, graph_name: str, base_url: str):
        self.graph_url = graph_url
        self.graph_port = graph_port
        self.graph_name = graph_name
        self.base_url = base_url

    @abstractmethod
    def query(self, user_input: str, similarity_threshold: float = 0.3):
        """抽象方法：对外统一暴露的面向前端/路由的 Graph RAG 主入口（返回流式生成器对象）
        规范参数：user_input - 用户输入的查询文本, similarity_threshold - 相似度阈值
        """
        pass

    @abstractmethod
    def query_with_nodes(self, user_input: str, similarity_threshold: float = 0.3):
        """抽象方法：对外统一暴露的面向前端/路由的 Graph RAG 主入口（返回检索到的节点和流式生成器对象）
        规范参数：user_input - 用户输入的查询文本, similarity_threshold - 相似度阈值
        """
        pass


class QueryDB(BaseQueryDB):
    def __init__(self):
        # 提取基础配置变量用于调用父类初始化
        graph_url = config['graph_url']
        graph_port = config['graph_port']
        graph_name = config['graph_name']
        constructed_base_url = f"http://{graph_url}:{graph_port}/graphs/{graph_name}"

        super().__init__(graph_url, graph_port, graph_name, constructed_base_url)

        # 初始化 OpenAI 客户端
        self.client = OpenAI(
            api_key=config["api_key"], 
            base_url=config["base_url"]
        )

    def _get_embedding(self, text: str) -> list[float]:
        """将用户提问转换为向量"""
        response = self.client.embeddings.create(
            model=config["embedding_model"], 
            input=[text]
        )
        return response.data[0].embedding

    def _vector_search(self, query_vector: list[float], threshold: float = 0.2) -> tuple[list[dict], list[dict]]:
        """
        全内存降级版向量检索（sklearn.cosine_similarity 矩阵加速版）
        """
        vertices_matched = []
        edges_matched = []
        expected_dim = len(query_vector)
        
        # 转换用户向量为 sklearn 要求的 2D 矩阵格式 (1, 维度)
        q_matrix = np.array(query_vector).reshape(1, -1)

        try:
            # 批量处理顶点
            v_url = f"{self.base_url}/graph/vertices?page&limit=500"
            v_response = requests.get(v_url)
            if v_response.status_code == 200:
                all_vertices = v_response.json().get("vertices", [])
                
                v_vectors = []
                valid_vertices = []
                
                # 过滤出带有效 embedding 的点
                for v in all_vertices:
                    props = v.get("properties", {})
                    emb = props.get("embeddings") or props.get("embedding")
                    if isinstance(emb, str):
                        try: emb = json.loads(emb)
                        except: continue
                    
                    if isinstance(emb, list) and len(emb) == expected_dim:
                        v_vectors.append(emb)
                        valid_vertices.append(v)
                    else:
                        actual_len = len(emb) if hasattr(emb, '__len__') or isinstance(emb, (list, str)) else "未知"
                        print(f"⚠️ 警告：顶点【{v.get('properties', {}).get('name', v.get('id'))}】的 embedding 无效，实际类型: {type(emb)}，实际长度: {actual_len} (期望: {expected_dim})")
                        
                
                # 利用 sklearn 进行矩阵级并行余弦计算（笛卡尔积思想）
                if v_vectors:
                    v_matrix = np.array(v_vectors)  # 形状为 (点数量, 1536)
                    # 算出来的 similarities 形状是 (1, 点数量)
                    v_similarities = cosine_similarity(q_matrix, v_matrix)[0]
                    
                    # 过滤并绑定得分
                    for idx, sim_score in enumerate(v_similarities):
                        if sim_score >= threshold:
                            valid_vertices[idx]["score"] = float(sim_score)
                            vertices_matched.append(valid_vertices[idx])

            # ================== 2. 批量处理边 ==================
            e_url = f"{self.base_url}/graph/edges?page&limit=500"
            e_response = requests.get(e_url)
            if e_response.status_code == 200:
                all_edges = e_response.json().get("edges", [])
                
                e_vectors = []
                valid_edges = []
                
                for e in all_edges:
                    props = e.get("properties", {})
                    emb = props.get("embeddings") or props.get("embedding")
                    
                    if isinstance(emb, str):
                        try: emb = json.loads(emb)
                        except: continue
                    
                    # ✅ 核心防线：边向量类型和维度必须同时与用户查询（1024维）完美对齐
                    if isinstance(emb, list) and len(emb) == expected_dim:
                        e_vectors.append(emb)
                        valid_edges.append(e)
                    else:
                        # 🛡️ 安全防御：防止 len(None) 崩溃
                        actual_len = len(emb) if hasattr(emb, '__len__') or isinstance(emb, (list, str)) else "未知"
                        
                        # 🟢 针对边的定制化日志：边没有 name，我们打印它的 label（关系名，如 attacks）和源/目标点
                        source_id = e.get("source", "未知")
                        target_id = e.get("target", "未知")
                        edge_label = e.get("label", "未知关系")
                        
                        print(f"⚠️ 警告：边【{source_id} ──({edge_label})──► {target_id}】的 embedding 无效，实际类型: {type(emb)}，实际长度: {actual_len} (期望: {expected_dim})")
                
                # 🚀 边向量矩阵并行计算
                if e_vectors:
                    e_matrix = np.array(e_vectors, dtype=np.float32)
                    e_similarities = cosine_similarity(q_matrix, e_matrix)[0]
                    
                    for idx, sim_score in enumerate(e_similarities):
                        if sim_score >= threshold:
                            valid_edges[idx]["score"] = float(sim_score)
                            edges_matched.append(valid_edges[idx])

            # 保持 Top-5 截断逻辑
            vertices_matched = sorted(vertices_matched, key=lambda x: x.get("score", 0), reverse=True)[:5]
            edges_matched = sorted(edges_matched, key=lambda x: x.get("score", 0), reverse=True)[:5]

            print(f"🎯 [sklearn 加速召回成功] 匹配顶点 {len(vertices_matched)} 个，边 {len(edges_matched)} 条")

        except Exception as e:
            print(f"❌ 矩阵向量检索时发生故障: {e}")
            
        return vertices_matched, edges_matched

    def _graph_traversal_extension(self, seed_vertices: list[dict]) -> list[dict]:
        """
        既返回关系（relationship），也返回节点（entity），确保与数据流水线全兼容
        """
        # 初始化结果列表
        results = []
        # 检查种子顶点是否为空，如果为空则直接返回空列表
        if not seed_vertices:
            return []
        
        # 遍历处理每个种子顶点
        for v in seed_vertices:
            # 提取顶点 ID
            vid = v.get("id")
            if not vid: continue
        
            try:
                encoded_id = urllib.parse.quote(f'"{vid}"', safe="")
                # 先获取与种子节点相关的所有边
                edge_url = f"{self.base_url.replace('/gremlin', '')}/graph/edges?vertex_id={encoded_id}&direction=BOTH"
                edge_resp = requests.get(edge_url, timeout=10)
            
                if edge_resp.status_code != 200: continue
            
                edges = edge_resp.json().get("edges", [])
                for edge in edges:
                    # 确定邻居 ID
                    out_v = edge.get("outV")
                    in_v = edge.get("inV")
                    target_id = in_v if out_v == vid else out_v
                
                    # 获取邻居节点详情
                    node_url = f"{self.base_url.replace('/gremlin', '')}/graph/vertices/{urllib.parse.quote(f'\"{target_id}\"', safe='')}"
                    node_resp = requests.get(node_url, timeout=10)
                
                    if node_resp.status_code == 200:
                        node_data = node_resp.json()
                        props = node_data.get("properties", {})
                        
                        # 把节点作为 'entity' 类型加入结果
                        results.append({
                            "type": "entity",
                            "name": props.get("name", target_id),
                            "entity_type": props.get("entity_type", "Unknown"),
                            "description": props.get("description", "")
                        })
                        
                        # 把关系三元组加入结果列表
                        edge_props = edge.get("properties", {})
                        results.append({
                            "type": "relationship",
                            "source": v.get("properties", {}).get("name", vid),
                            "target": props.get("name", target_id), # 使用真实名字
                            "label": edge.get("label", "related_to"),
                            "description": edge_props.get("description", "关联事件"),
                            "score": float(edge_props.get("score", 0.0)),
                            "time": edge_props.get("time", "unknown")
                        })
            
            except Exception as e:
                print(f"⚠️ 拓扑检索异常: {e}")
            
        return results

    def _generate_answer(self, query: str, context_data: list[dict]):
        """
        将所有知识图谱线索打包，送入高阶思考大模型进行流式生成 (Yields Text Chunks)
        💡 核心设计：仅过滤并吐出最终 content，对前端隐藏思考过程
        """
        # 将图谱结构化数据扁平化为大模型可读的文本线索
        formatted_context = ""
        for idx, item in enumerate(context_data, 1):
            time_str = f"时间: {item['time']}" if item.get("time") else "时间: 未知"
            score_str = f"相似度可靠性: {item['score']:.2f}" if item.get("score") else ""
    
            if item.get("type") == "relationship" or ("source" in item and "target" in item):
                formatted_context += f"线索 {idx} [{time_str} | {score_str}]: 【{item['source']}】 ──({item['label']})──► 【{item['target']}】，细节事实: {item.get('description', '无')}\n"
            else:
                formatted_context += f"线索 {idx} [{score_str}]: 实体 【{item.get('name')}】 ({item.get('entity_type', '未知')})，细节描述: {item.get('description', '无')}\n"

        if not formatted_context:
            formatted_context = "图数据库未检索到直接相关的强确定性线索，请基于自身常识提供深度推演。"

        # 构造高阶 RAG 提示词
        system_prompt = (
            "你是一位精通全球地缘政治与宏观经济的首席分析师。\n"
            "你的任务是结合图数据库检索出来的【真实线索】，回答用户的提问，并进行合理的因果推导与前瞻性预测。\n\n"
            f"【图谱线索（基于最新抓取的新闻事实构建）】:\n{formatted_context}\n"
            "【分析要求】:\n"
            "1. 必须优先紧密围绕【图谱线索】展开推导，严禁捏造与线索冲突的历史事实。\n"
            "2. 针对用户提出的预测/总结性问题，允许并鼓励利用你自身的宏观内生知识库进行多步因果链条（Multi-hop）的延展推理。\n"
            "3. 输出一份逻辑严密、分条目、具备专业度的分析报告。\n"
            "4. 线索中包含【时间】与【相似度可靠性】。请优先信任可靠性得分高、时效性最新的线索，并按照事件发生的时间先后顺序进行逻辑推演。"
        )

        try:
            # 🚨 激活流式传输开关： stream=True
            response = self.client.chat.completions.create(
                model=config.get('query_model', 'qwen3-max'),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                stream=True,  # 开启流式
                extra_body={"enable_thinking": True}  # 保持开启思考模式以确保回答的高质量基调
            )
            
            for chunk in response:
                if not chunk.choices:
                    continue
                
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                
                # 🛡️ 像素级拦截：直接无视 reasoning_content，只有当 content 有文本内容时才实时泵出
                if content:
                    yield content
                    
        except Exception as e:
            yield f"❌ 大模型理解与生成阶段发生异常: {e}"

    def query(self, user_input: str, similarity_threshold: float = 0.3):
        """
        对外统一暴露的面向前端/路由的 Graph RAG 主入口（返回流式生成器对象）
        """
        print(f"🔍 [1/4] 正在对用户提问进行向量化...")
        query_vector = self._get_embedding(user_input)
        
        print(f"🧭 [2/4] 正在进入 HugeGraph 检索高相关性实体与关系...")
        matched_vertices, matched_edges = self._vector_search(query_vector, similarity_threshold)
        
        # 将初始召回的点和边规范化
        all_facts = []
        for v in matched_vertices:
            props = v.get("properties", {})
            all_facts.append({
                "type": "entity",
                "name": props.get("name", v.get("id")),
                "entity_type": props.get("entity_type", "Unknown"),
                "description": props.get("description", "")
            })
            
        for e in matched_edges:
            props = e.get("properties", {})
            all_facts.append({
                "type": "relationship",
                "source": e.get("source", ""),
                "target": e.get("target", ""),
                "label": e.get("label", ""),
                "description": props.get("description", ""),
                "score": props.get("score", 0),
                "time": props.get("time", "")
            })

        print(f"🕸️ [3/4] 顺藤摸瓜：正在基于种子节点进行 2-Hop 语法拓扑扩展...")
        extended_triplets = self._graph_traversal_extension(matched_vertices)
        print(f"扩展后的图谱线索数量: {len(extended_triplets)}")
        all_facts.extend(extended_triplets)
        
        # 简单去重
        unique_facts = [dict(t) for t in {tuple(d.items()) for d in all_facts}]

        print(f"🧠 [4/4] 正在将 {len(unique_facts)} 条图谱线索打包送入旗舰大模型进行思考预测...")
        
        # 核心修改：直接向上传递生成器对象（Generator Object），供前端实时消费
        return self._generate_answer(user_input, unique_facts)
    
    def query_with_nodes(self, user_input: str, similarity_threshold: float = 0.3):
        """
        对外统一暴露的面向前端/路由的 Graph RAG 主入口（返回检索到的节点和流式生成器对象）
        :return: (检索到的节点列表, 流式生成器)
        """
        print(f"🔍 [1/4] 正在对用户提问进行向量化...")
        query_vector = self._get_embedding(user_input)
        
        print(f"🧭 [2/4] 正在进入 HugeGraph 检索高相关性实体与关系...")
        matched_vertices, matched_edges = self._vector_search(query_vector, similarity_threshold)
        
        # 将初始召回的点和边规范化
        all_facts = []
        for v in matched_vertices:
            props = v.get("properties", {})
            all_facts.append({
                "type": "entity",
                "name": props.get("name", v.get("id")),
                "entity_type": props.get("entity_type", "Unknown"),
                "description": props.get("description", "")
            })
            
        for e in matched_edges:
            props = e.get("properties", {})
            all_facts.append({
                "type": "relationship",
                "source": e.get("source", ""),
                "target": e.get("target", ""),
                "label": e.get("label", ""),
                "description": props.get("description", ""),
                "score": props.get("score", 0),
                "time": props.get("time", "")
            })

        print(f"🕸️ [3/4] 顺藤摸瓜：正在基于种子节点进行 2-Hop 语法拓扑扩展...")
        extended_triplets = self._graph_traversal_extension(matched_vertices)
        print(f"扩展后的图谱线索数量: {len(extended_triplets)}")
        all_facts.extend(extended_triplets)
        
        # 简单去重
        unique_facts = [dict(t) for t in {tuple(d.items()) for d in all_facts}]

        print(f"🧠 [4/4] 正在将 {len(unique_facts)} 条图谱线索打包送入旗舰大模型进行思考预测...")
        
        # 返回检索到的节点和流式生成器
        return unique_facts, self._generate_answer(user_input, unique_facts)


if __name__ == "__main__":
    # 本地极简联调测试
    query_engine = QueryDB()
    test_query = "最近以色列在黎巴嫩南部的军事行动会对金融避险资产产生什么传导影响？"
    report = query_engine.query(test_query)
    print("\n================ 最终大模型深度预测报告 ================\n")
    print(report)