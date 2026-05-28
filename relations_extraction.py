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
        """
        提取实体间的关系。
        核心改动：在不修改原始 entities_list 的前提下，为大模型生成一个“脱敏版”视图。
        """
        # 1. 安全拦截
        if not entities_list or not original_text.strip():
            return []

        # 影子脱敏：仅提取模型需要的字段，过滤掉 embedding
        # 这样做既保留了模型参考所需的 description，又移除了会导致token消耗增加的embedding字段
        entities_for_model = []
        for ent in entities_list:
            if isinstance(ent, dict):
                entities_for_model.append({
                    "name": ent.get("name", ""),
                    "entity_type": ent.get("entity_type", ""),
                    "description": ent.get("description", "")
                })
            else:
                entities_for_model.append({"name": str(ent)})

        # 组装 Prompt
        formatted_prompt = self.relation_prompt_template.replace('{entities_list}', json.dumps(entities_for_model, ensure_ascii=False))
        formatted_prompt = formatted_prompt.replace('{original_text}', original_text)
        
        # API 崩溃防御：全包裹 try-except，确保流式爬虫不中断
        try:
            response = self.client.chat.completions.create(
                model=config['language_model'],
                messages=[{"role": "user", "content": formatted_prompt}],
                extra_body={"enable_thinking": False}
            )
            relations = response.choices[0].message.content
        except Exception as e:
            print(f"❌ API 调用失败: {e}")
            return []
        
        # 清洗与解析 (保留原始的所有防御逻辑)
        relations = relations.strip() if relations else ""
        if not relations:
            return []
            
        if "```" in relations:
            json_match = re.search(r"```json\s*(.*?)\s*```", relations, re.DOTALL)
            if not json_match:
                json_match = re.search(r"```\s*(.*?)\s*```", relations, re.DOTALL)
            if json_match:
                relations = json_match.group(1)
        
        def try_parse_json(content_to_parse):
            strategies = [
                lambda s: json.loads(s),
                lambda s: self._fix_incomplete_json(s),
                lambda s: self._extract_json_array(s),
                lambda s: self._fix_single_quotes(s),
                lambda s: self._clean_and_parse(s),
            ]
            for strategy in strategies:
                try:
                    result = strategy(content_to_parse)
                    if isinstance(result, list):
                        return result
                except (json.JSONDecodeError, ValueError):
                    continue
            return None
        
        relations_data = try_parse_json(relations)
        return relations_data if relations_data is not None else []

    def _fix_incomplete_json(self, content: str) -> list:
        """尝试修复不完整的JSON"""
        content = content.strip()
        open_brackets = content.count('[') + content.count('{')
        close_brackets = content.count(']') + content.count('}')
        diff = open_brackets - close_brackets
        
        if diff > 0 and content.startswith('['):
            fixed = content
            for _ in range(diff):
                fixed += ']'
            return json.loads(fixed)
        elif content.startswith('[') and not content.endswith(']'):
            return json.loads(content + ']')
            
        raise ValueError("无法修复不完整的JSON")
        
    def _extract_json_array(self, content: str) -> list:
        """从文本中提取最外层的JSON数组"""
        start = content.find('[')
        if start == -1: 
            raise ValueError("未找到数组起始")
            
        bracket_count = 1
        end = start + 1
        while end < len(content) and bracket_count > 0:
            if content[end] == '[':
                bracket_count += 1
            elif content[end] == ']':
                bracket_count -= 1
            end += 1
            
        if bracket_count == 0:
            array_str = content[start:end]
            return json.loads(array_str)
            
        raise ValueError("无法找到匹配的结束括号")
        
    def _fix_single_quotes(self, content: str) -> list:
        """使用状态机精准修复单引号问题，保护字符串内部合法字符"""
        content = content.strip()
        result = []
        in_string = False
        escape = False
        
        for char in content:
            if escape:
                result.append(char)
                escape = False
            elif char == '\\':
                result.append(char)
                escape = True
            elif char == '"':
                in_string = not in_string
                result.append(char)
            elif char == "'" and not in_string:
                result.append('"')
            else:
                result.append(char)
                
        return json.loads(''.join(result))
        
    def _clean_and_parse(self, content: str) -> list:
        """清理内容并尝试解析"""
        content = re.sub(r'[\x00-\x1F\x7F]', '', content)
        content = re.sub(r',\s*([}\]])', r'\1', content)
        content = content.strip()
        
        if not content:
            raise ValueError("内容为空")
            
        return json.loads(content)
    def _relation_embedding(self, relations: list[dict], source_weight: float = 0.3, target_weight: float = 0.3, description_weight: float = 0.4) -> list[list[float]]:
        if not relations: return []
        
        texts_to_embed = []
        for r in relations:
            texts_to_embed.extend([r.get('source', ''), r.get('target', ''), r.get('description', '')])
        
        all_embeddings = []
        batch_size = 8
        for i in range(0, len(texts_to_embed), batch_size):
            batch = texts_to_embed[i:i + batch_size]
            try:
                response = self.client.embeddings.create(model=config['embedding_model'], input=batch)
                all_embeddings.extend([item.embedding for item in response.data])
            except:
                all_embeddings.extend([[0.0]*1536] * len(batch)) # 容错处理
        
        result_vectors = []
        for i in range(len(relations)):
            sv, tv, dv = all_embeddings[3*i], all_embeddings[3*i+1], all_embeddings[3*i+2]
            weighted = [source_weight*s + target_weight*t + description_weight*d for s, t, d in zip(sv, tv, dv)]
            norm = np.linalg.norm(weighted)
            result_vectors.append((weighted / norm if norm > 0 else weighted).tolist())
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

