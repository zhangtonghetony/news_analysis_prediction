import yaml
import os

# 全局配置变量，用于缓存加载后的配置，避免重复读取文件
_config = None

def _load_config():
    """加载配置文件，使用单例模式确保只加载一次"""
    global _config
    # 如果配置尚未加载，则从文件读取
    if _config is None:
        # 构建配置文件路径：当前文件所在目录下的 config.yml
        config_path = os.path.join(os.path.dirname(__file__), 'config.yml')
        with open(config_path, 'r', encoding='utf-8') as f:
            # yaml.safe_load: 安全地解析YAML文件，只创建简单的Python对象（如字典、列表、字符串等）
            # 相比 yaml.load，safe_load 不会执行任意Python代码，可防止代码注入攻击
            _config = yaml.safe_load(f)
    return _config

# 模块加载时自动初始化配置
config = _load_config()

if __name__ == '__main__':
    print("Configuration loaded successfully:")
    print(config)
