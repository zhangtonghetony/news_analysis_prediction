import requests
import urllib.parse
import json
from config import config
from fetch_data import NewsFetcher
from spider_news import NewsSpider
from entities_extraction import EntityExtractor
from relations_extraction import RelationsExtractor
from openai import OpenAI

newsfetcher = NewsFetcher()
entityextractor = EntityExtractor()
relationextractor = RelationsExtractor()
spider = NewsSpider()


# 将把新闻数据转换为实体和关系功能封装为一个函数transform_news
def transform_news():
    domestic_entities = []
    domestic_relations = []
    foreign_entities = []
    foreign_relations = []

    domestic_news = newsfetcher.fetch_domestic_news()
    foreign_news = newsfetcher.fetch_foreign_news()

    for news in domestic_news[:7]:
        entities = entityextractor.final_extract_entities(news['标题+具体内容']+news['时间'])
        text_to_send = news['标题+具体内容'] + news['时间']
        print(len(text_to_send))
        domestic_entities.append(entities)
        relations = relationextractor.final_extract_relations(entities, news['标题+具体内容']+news['时间'])
        domestic_relations.append(relations)
    for news in foreign_news[:7]:
        entities = entityextractor.final_extract_entities(news['标题+具体内容']+news['时间'])
        foreign_entities.append(entities)
        relations = relationextractor.final_extract_relations(entities, news['标题+具体内容']+news['时间'])
        foreign_relations.append(relations)
    
    # 实体和关系列表的长度应该相等
    assert len(domestic_entities) == len(domestic_relations)
    assert len(foreign_entities) == len(foreign_relations)

    return domestic_entities, domestic_relations, foreign_entities, foreign_relations



# 不使用不稳定的官方库连接数据库，直接使用http请求
class GraphDBHandler:
    def __init__(self):
        self.graph_url = config['graph_url']
        self.graph_port = config['graph_port']
        self.graph_name = config['graph_name']
        self.base_url = f"http://{self.graph_url}:{self.graph_port}/graphs/{self.graph_name}"

        self.client = OpenAI(
            api_key=config["api_key"], base_url=config["base_url"]
        )



    def add_vertex(self, properties: dict):
        """
        添加/更新顶点（完全防御版：解决空格URL问题 + 严格白名单过滤）
        """
        # 核心防御 1：对包含空格或特殊字符的顶点名称进行标准 URL 编码
        safe_name = urllib.parse.quote(properties["name"])
        vertex_id = f"11:{safe_name}"

        # 纯 HTTP 查询
        get_url = f"{self.base_url}/graph/vertices/{vertex_id}"
        existing_vertex = None

        try:
            get_response = requests.get(get_url)
            # 检查响应状态码是否为 200（成功），以此判断顶点是否存在
            if get_response.status_code == 200:
                existing_vertex = get_response.json()
        except requests.exceptions.RequestException as e:
            if (
                not hasattr(e, "response")
                or e.response.status_code != 404
            ):
                print(f"查询顶点是否存在时发生网络错误: {e}")
                return None

        # 开始准备拼装要写入图库的属性
        raw_properties = properties.copy()

        # 统一转换可能存在的复数/单数 embedding 字段
        if "embeddings" in raw_properties:
            raw_properties["embedding"] = raw_properties.pop("embeddings")

        # 执行"描述去重与追加"的核心文本逻辑
        if existing_vertex:
            old_props = existing_vertex.get("properties", {})
            old_desc = old_props.get("description", "")
            new_desc = raw_properties.get("description", "")

            if new_desc in old_desc:
                raw_properties["description"] = old_desc
                raw_properties["embedding"] = old_props.get("embedding")
            else:
                raw_properties["description"] = (
                    f"{old_desc} | 最新线索：{new_desc}"
                )
                print(
                    f"正在为融合后的实体 【{properties['name']}】 重新生成向量..."
                )
                response = self.client.embeddings.create(
                    model=config["embedding_model"],
                    input=[raw_properties["description"]],
                )
                raw_properties["embedding"] = response.data[0].embedding

        #  核心防御 2：属性严格清洗白名单
        # 假设Hubble 里的实体属性【只建了】这 4 个，那就只允许这 4 个 Key 提交给后端！
        # 如果还建了别属性（比如 category），把它加进这个列表里。
        ALLOWED_KEYS = ["name", "entity_type", "description", "embedding"]

        final_cleaned_props = {}
        for key in ALLOWED_KEYS:
            if key in raw_properties:
                final_cleaned_props[key] = raw_properties[key]

        # 纯 HTTP 写入/覆盖
        post_url = f"{self.base_url}/graph/vertices"
        post_data = {"label": "entity", "properties": final_cleaned_props}

        post_response = None
        try:
            post_response = requests.post(post_url, json=post_data)
            post_response.raise_for_status()
            print(f"🟢 顶点 【{properties['name']}】 成功安全入库/融合！")
            return post_response.json()
        except requests.exceptions.RequestException as e:
            print(
                f"❌ 写入/更新顶点 【{properties['name']}】 彻底失败: {e}"
            )
            if post_response is not None:
                # 这里将向你吐露它最后为什么不爽（比如具体哪个属性没对齐）
                print(f"【HugeGraph 后端真实拒绝原因】: {post_response.text}")
            return None
    
    def add_edge(self, properties: dict):
        """
        :param properties: 包含 source, target, relation_type, description, time, score, embeddings 的字典
        :return: 插入的边信息
        """
        prefix = '11'
        url = f"{self.base_url}/graph/edges"
        
        # 浅拷贝一份属性，防止污染修改到上游的原始数据
        edge_props = properties.copy()
        
        # 剥离并提取出不属于边属性的字段（用于构造图的拓扑结构）
        source_name = edge_props.pop('source')
        target_name = edge_props.pop('target')
        
        # 字段映射微调（对齐Hubble 里的元数据名称）
        # 大模型吐出的是 'embeddings'（复数），把它改成图库里建的 'embedding'（单数）
        if 'embeddings' in edge_props:
            edge_props['embedding'] = edge_props.pop('embeddings')

        # 4. 构造规范的 HugeGraph HTTP 请求体
        data = {
            "label": 'related_to', # 万能边
            "outV": f"{prefix}:{source_name}",
            "inV": f"{prefix}:{target_name}",
            "properties": edge_props # 此时的 edge_props 只剩干净的四个业务属性加向量了
        }

        try:
            response = requests.post(url, json=data)
            response.raise_for_status()
            print(f"🔗 边 【{source_name}】──({data['properties']['relation_type']})──>【{target_name}】成功连线！")
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ 插入边失败: {e}")
            #  核心改动：只要 response 拿到了，不管 raise_for_status 怎么闹，我们强行打印出后端吐的所有文本
            if response is not None:
                print(f"👉 【HugeGraph 后端真实死因】: {response.text}")
            else:
                print("👉 请求连后端都没送达（可能是网络不通或URL写错了）")
            return None

graph_handler = GraphDBHandler()


# 从新闻数据中提取实体和关系，然后插入到数据库中（完整逻辑）
def insert_news_to_db():
    domestic_entities, domestic_relations, foreign_entities, foreign_relations = transform_news()
    for entities, relations in zip(domestic_entities, domestic_relations):
        for entity in entities:
            graph_handler.add_vertex(entity)
        for relation in relations:
            graph_handler.add_edge(relation)
    for entities, relations in zip(foreign_entities, foreign_relations):
        for entity in entities:
            graph_handler.add_vertex(entity)
        for relation in relations:
            graph_handler.add_edge(relation)

# 从爬虫获取的新闻中提取实体和关系，并插入至数据库
def insert_sp_news_to_db():
    news_list = spider.get_news_list()
    for news in news_list[:10]:
        detail_url = news['url']
        text = spider.crawl_detail_page(detail_url)
        if text:
            entities = entityextractor.final_extract_entities(text)
            for entity in entities:
                graph_handler.add_vertex(entity)
            
            relations = relationextractor.final_extract_relations(entities, text)
            for relation in relations:
                graph_handler.add_edge(relation)







if __name__ == '__main__':
    
    # name = "俄罗斯政府"
    # desc = "俄罗斯政府是一个国家的政府机构，负责管理俄罗斯的国家政策、法律、法律程序、法律程序、法律程序、法律程序、法律程序、法律程序、法律程序、法律程序、法律程序、法律程序、法律程序、法律程序、法律程序、法律程序、法律程序、法律程序、法律程序、法律程序、法律程序、法律程序、法律程序、法律程序、法律程序、法律程序程序、法律程序、法律程序、法律程序。"
    # embedding = [0.1524, -0.3412, 0.8871, 0.0456]
    
    # vertex = graph_handler.add_vertex(
    #       {
    #           'name': name,
    #           'description': desc,
    #           'embedding': embedding
    #       }
    #   )
    # graph_handler.add_edge(
    # {
    #     'source': '普京',
    #     'target': name,
    #     'relation_type': 'belongs_to',
    #     'description': desc,
    #     'time': '2024-01-01',
    #     'score': 8,
    #     'embeddings': embedding
    # }
    # )
    insert_sp_news_to_db()
    