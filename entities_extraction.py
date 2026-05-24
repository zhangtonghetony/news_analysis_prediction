from config import config
from openai import OpenAI
import numpy as np
import json
import os
import re


class EntityExtractor:
    def __init__(self):
        # 初始化OpenAI客户端
        self.client = OpenAI(
            api_key=config['api_key'],
            base_url=config['base_url']
        )
        
        # 读取实体提取prompt模板
        PROMPT_PATH = os.path.join(os.path.dirname(__file__), 'prompts', 'entities_extraction.txt')
        with open(PROMPT_PATH, 'r', encoding='utf-8') as f:
            self.entity_prompt_template = f.read()
    
    def _extract_entities(self, text: str) -> list[dict]:
        formatted_prompt = self.entity_prompt_template.replace('{text}', text)
        
        response = self.client.chat.completions.create(
            model=config['language_model'],
            messages=[{'role': 'user', 'content': formatted_prompt}],
            extra_body={"enable_thinking": False}
        )
        
        content = response.choices[0].message.content
        content = content.strip()
        
        if content.startswith('```'):
            content = content.split('\n', 1)[-1] if '\n' in content else ''
            if content.endswith('```'):
                content = content[:-3].strip()
        
        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    raise ValueError(f"无法解析模型返回的JSON内容: {content[:200]}...") from e
            else:
                raise ValueError(f"无法解析模型返回的JSON内容: {content[:200]}...") from e
        
        
        return data
    
    def _entity_embedding(self, entities: list[dict], name_weight: float = 0.3, description_weight: float = 0.7) -> list[list[float]]:
        if not entities:
            return []
        
        texts_to_embed = []
        for entity in entities:
            name = entity.get('name', '')
            description = entity.get('description', '')
            texts_to_embed.append(name)
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
        for i in range(len(entities)):
            name_vector = all_embeddings[2 * i]
            description_vector = all_embeddings[2 * i + 1]
            
            weighted_vector = [
                name_weight * nv + description_weight * dv
                for nv, dv in zip(name_vector, description_vector)
            ]
            norm = np.linalg.norm(weighted_vector)
            final_vector = weighted_vector / norm if norm > 0 else weighted_vector
            final_vector_list = final_vector.tolist()
            result_vectors.append(final_vector_list)
        
        return result_vectors

    def final_extract_entities(self, text: str) -> list[dict]:
        entities = self._extract_entities(text)
        result_vectors = self._entity_embedding(entities)
        for i in range(len(entities)):
             entities[i]['embeddings'] = result_vectors[i]
        return entities


if __name__ == '__main__':
    extractor = EntityExtractor()
    entities = extractor.final_extract_entities("2024年3月，阿里巴巴集团在杭州举办了年度技术大会，马云发表了主题演讲。")
    print(entities)
