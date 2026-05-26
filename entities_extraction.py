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
        
        # 清理内容：去除 markdown 代码块包裹
        if content.startswith('```'):
            content = content.split('\n', 1)[-1] if '\n' in content else ''
            if content.endswith('```'):
                content = content[:-3].strip()
        
        # 定义多种解析策略，按优先级尝试
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
            
            for i, strategy in enumerate(strategies):
                try:
                    result = strategy(content_to_parse)
                    if isinstance(result, list):
                        return result
                except (json.JSONDecodeError, ValueError):
                    continue
            
            return None
        
        data = try_parse_json(content)
        
        if data is not None:
            return data
        
        # 如果所有策略都失败，返回空列表而不是抛出异常
        print(f"警告：无法解析模型返回的JSON内容，返回空列表。原始内容片段: {content[:100]}...")
        return []
    
    def _fix_incomplete_json(self, content: str) -> list:
        """尝试修复不完整的JSON"""
        # 移除多余的换行和空格
        content = content.strip()
        
        # 统计括号数量，尝试补全
        open_brackets = content.count('[') + content.count('{')
        close_brackets = content.count(']') + content.count('}')
        diff = open_brackets - close_brackets
        
        if diff > 0 and content.startswith('['):
            # 尝试补全闭合括号
            fixed = content
            for _ in range(diff):
                fixed += ']'
            return json.loads(fixed)
        elif content.startswith('[') and not content.endswith(']'):
            # 尝试在末尾添加闭合括号
            return json.loads(content + ']')
        
        raise ValueError("无法修复不完整的JSON")
    
    def _extract_json_array(self, content: str) -> list:
        """从文本中提取最外层的JSON数组"""
        # 查找数组的起始和结束位置
        start = content.find('[')
        if start == -1:
            raise ValueError("未找到数组起始")
        
        # 尝试找到匹配的结束括号
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
        # 简单处理：将单引号替换为双引号（注意不要替换字符串内的单引号）
        content = content.strip()
        
        # 使用正则表达式更安全地替换
        # 只替换不在引号内的单引号
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
        # 移除控制字符
        content = re.sub(r'[\x00-\x1F\x7F]', '', content)
        
        # 移除多余的逗号（如 "[1, 2, 3,]" 中的最后一个逗号）
        content = re.sub(r',\s*([}\]])', r'\1', content)
        
        # 移除首尾的空白字符和特殊符号
        content = content.strip()
        
        if not content:
            raise ValueError("内容为空")
        
        return json.loads(content)
    
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
