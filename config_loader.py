"""
配置加载模块
加载和解析 config.yaml 配置文件
"""

import yaml
from typing import Dict, Any


class Config:
    """配置类 - 单例模式"""
    
    _instance = None
    _config = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def load(self, config_path: str = "config.yaml"):
        """加载配置文件"""
        with open(config_path, 'r', encoding='utf-8') as f:
            self._config = yaml.safe_load(f)
        print(f'[Config] ✓ 配置加载成功: {config_path}')
        return self
    
    def get(self, *keys, default=None):
        """获取配置值（支持嵌套）
        
        示例:
            config.get('services', 'encoder', 'url')
            config.get('connection_pools', 'encoder', 'max_connections')
        """
        value = self._config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value
    
    def get_service_config(self, service_name: str) -> Dict[str, Any]:
        """获取服务配置"""
        return self.get('services', service_name, default={})
    
    def get_pool_config(self, pool_name: str) -> Dict[str, Any]:
        """获取连接池配置"""
        return self.get('connection_pools', pool_name, default={})
    
    def get_breaker_config(self, breaker_name: str) -> Dict[str, Any]:
        """获取熔断器配置"""
        return self.get('circuit_breakers', breaker_name, default={})
    
    def get_timeout(self, service_name: str) -> tuple:
        """获取服务超时配置（返回 (connect_timeout, read_timeout)）"""
        service_config = self.get_service_config(service_name)
        connect_timeout = service_config.get('connect_timeout', 30)
        read_timeout = service_config.get('read_timeout', 60)
        return (connect_timeout, read_timeout)
    
    @property
    def server_host(self) -> str:
        return self.get('server', 'host', default='0.0.0.0')
    
    @property
    def server_port(self) -> int:
        return self.get('server', 'port', default=9510)
    
    @property
    def mongodb_url(self) -> str:
        return self.get('services', 'mongodb', 'url')
    
    @property
    def mongodb_database(self) -> str:
        return self.get('services', 'mongodb', 'database', default='rqa')
    
    @property
    def mongodb_collection(self) -> str:
        return self.get('services', 'mongodb', 'collection')
    
    def print_summary(self):
        """打印配置摘要"""
        print(f'\n{"="*80}')
        print(f'配置摘要')
        print(f'{"="*80}')
        print(f'服务地址: {self.server_host}:{self.server_port}')
        print(f'MongoDB: {self.mongodb_url}')
        print(f'编码服务: {self.get("services", "encoder", "url")}')
        print(f'Milvus: {self.get("services", "milvus", "url")}')
        print(f'Reranker: {self.get("services", "reranker", "url")}')
        print(f'Elasticsearch: {self.get("services", "elasticsearch", "url")}')
        print(f'\n连接池配置:')
        for pool_name in ['encoder', 'milvus', 'reranker', 'mongodb']:
            pool_config = self.get_pool_config(pool_name)
            print(f'  {pool_name}: max={pool_config.get("max_connections")}')
        print(f'\n熔断器配置:')
        for breaker_name in ['encoder', 'milvus', 'reranker', 'mongodb']:
            breaker_config = self.get_breaker_config(breaker_name)
            print(f'  {breaker_name}: threshold={breaker_config.get("failure_threshold")}')
        print(f'\n并发控制: {self.get("concurrency_control", "initial_concurrency")} -> '
              f'{self.get("concurrency_control", "max_concurrency")}')
        print(f'{"="*80}\n')


# 全局配置实例
config = Config()
