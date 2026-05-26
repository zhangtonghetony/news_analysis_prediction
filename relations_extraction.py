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
        
        # 🛡️ 核心防御 3：使用多策略解析机制，确保上游循环即使遇到脏数据也绝对不崩溃
        def try_parse_json(content_to_parse):
            strategies = [
                # 策略1：直接解析
                lambda s: json.loads(s),
                # 策略2：尝试修复末尾不完整
                lambda s: self._fix_incomplete_json(s),
                # 策略3：提取最外层数组
                lambda s: self._extract_json_array(s),
                # 策略4：尝试修复单引号问题
                lambda s: self._fix_single_quotes(s),
                # 策略5：尝试清理多余字符
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
        
        if relations_data is not None:
            return relations_data
        
        # 如果所有策略都失败，返回空列表而不是抛出异常
        print(f"❌ 警告：大模型吐出的格式无法被标准 JSON 解析。")
        print(f"👉 原始脏数据内容为: {relations[:100]}...")
        return []
    
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
        """尝试修复单引号问题"""
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

