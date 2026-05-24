from config import config
from openai import OpenAI  
import numpy as np
import pandas as pd
import json
import os
import re

class RelationsExtractor:
    def __init__(self):
        # 初始化OpenAI客户端
        self.client = OpenAI(
            api_key=config['api_key'],
            base_url=config['base_url']
        )
        
        # 读取关系提取prompt模板
        PROMPT_PATH = os.path.join(os.path.dirname(__file__), 'prompts', 'relations_extraction.txt')
        with open(PROMPT_PATH, 'r', encoding='utf-8') as f:
            self.relation_prompt_template = f.read()
    
    def _extract_relations(self, entities_list: list[dict], original_text: str) -> list[dict]:
        formatted_prompt = self.relation_prompt_template.replace('{entities_list}', str(entities_list))
        formatted_prompt = formatted_prompt.replace('{original_text}', original_text)
        
        response = self.client.chat.completions.create(
            model=config['language_model'],
            messages=[{"role": "user", "content": formatted_prompt}],
            extra_body={"enable_thinking": False}
        )
        relations = response.choices[0].message.content
        
        # 🛡️ 核心防御 1：清洗两端空白，防止空字符串直接触发 json.loads 崩溃
        relations = relations.strip() if relations else ""
        if not relations:
            print("⚠️ 提示：大模型未针对该摘要输出任何关系内容，自动兜底返回空列表。")
            return []
            
        # 🛡️ 核心防御 2：强力剥离可能存在的 Markdown JSON 代码块包裹 (```json ... ```)
        if "```" in relations:
            json_match = re.search(r"```json\s*(.*?)\s*```", relations, re.DOTALL)
            if json_match:
                relations = json_match.group(1)
            else:
                json_match = re.search(r"```\s*(.*?)\s*```", relations, re.DOTALL)
                if json_match:
                    relations = json_match.group(1)
        
        # 🛡️ 核心防御 3：安全的解析异常捕获网，确保上游循环即使遇到脏数据也绝对不崩溃
        try:
            relations_data = json.loads(relations)
            return relations_data
        except json.JSONDecodeError as e:
            print(f"❌ 警告：大模型吐出的格式无法被标准 JSON 解析。")
            print(f"👉 原始脏数据内容为: {relations}")
            return []
    
    def _relation_embedding(self, relations: list[dict], source_weight: float = 0.3, target_weight: float = 0.3, description_weight: float = 0.4) -> list[list[float]]:
        if not relations:
            return []
        
        texts_to_embed = []
        for relation in relations:
            source = relation.get('source', '')
            target = relation.get('target', '')
            description = relation.get('description', '')
            texts_to_embed.append(source)
            texts_to_embed.append(target)
            texts_to_embed.append(description)
        
        batch_size = 8
        all_embeddings = []
        
        for i in range(0, len(texts_to_embed), batch_size):
            batch = texts_to_embed[i:i + batch_size]
            response = self.client.embeddings.create(
                model=config['embedding_model'],
                input=batch
            )
            batch_embeddings = [item.embedding for item in response.data]
            all_embeddings.extend(batch_embeddings)
        
        result_vectors = []
        for i in range(len(relations)):
            source_vector = all_embeddings[3 * i]
            target_vector = all_embeddings[3 * i + 1]
            description_vector = all_embeddings[3 * i + 2]
            
            weighted_vector = [
                source_weight * sv + target_weight * tv + description_weight * dv
                for sv, tv, dv in zip(source_vector, target_vector, description_vector)
            ]
            norm = np.linalg.norm(weighted_vector)
            final_vector = weighted_vector / norm if norm > 0 else weighted_vector
            final_vector_list = final_vector.tolist()
            result_vectors.append(final_vector_list)
        
        return result_vectors

    def final_extract_relations(self, entities_list: list[dict], original_text: str) -> list[dict]:
        relations = self._extract_relations(entities_list, original_text)
        result_vectors = self._relation_embedding(relations)
        for i in range(len(relations)):
            relations[i]['embeddings'] = result_vectors[i]
        return relations
        



      


if __name__ == '__main__':
    extractor = RelationsExtractor()
    relations = extractor.final_extract_relations([{"name" : "马云", "description": "阿里巴巴集团创始人"}, {"name": "阿里巴巴集团", "description": "中国最大的电子商务平台"}, {"name": "杭州", "description": "中国浙江省省会"}],"2024年3月，阿里巴巴集团在杭州举办了年度技术大会，马云发表了主题演讲。")
    print((relations))

