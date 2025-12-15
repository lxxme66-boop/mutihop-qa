"""
RAG 搜索服务 - 改进版
集成连接池、熔断器、并发控制、监控告警四层防护架构
版本：v2.0-improved
"""

import configparser
import datetime
import faulthandler
import jieba
import jieba.analyse
import json
import logging
import os
import pymongo
import random
import re
import requests
import sys
import threading
import time
import tiktoken
import traceback
import torch
import numpy as np
import pandas as pd
import argparse

from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from apscheduler.schedulers.background import BackgroundScheduler
from elasticsearch import Elasticsearch
from nltk.stem.porter import PorterStemmer
from sentence_transformers import util
from zhkeybert import KeyBERT, extract_kws_zh
from retriever.retriever_memory_keywords import read_keywords_with_score_from_memory
from keybert import KeyBERT as KBERT
from torch import nn
from transformers import BertTokenizer, BertModel
from functools import wraps
from collections import deque, defaultdict
from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Callable
from flask import Flask, request, Response, jsonify

# 导入配置
from config_loader import config

# ==================== 配置日志 ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

# ==================== 第一层：连接状态一致性保证 ====================

class ConnectionState(Enum):
    """连接状态枚举"""
    IDLE = "idle"
    LEASED = "leased"
    IN_USE = "in_use"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass
class ConnectionLease:
    """连接租约"""
    request_id: str
    connection: Any
    service_type: str
    start_time: float
    max_lease_ms: int = 70000
    state: ConnectionState = ConnectionState.LEASED
    
    def is_expired(self) -> bool:
        return (time.time() - self.start_time) * 1000 > self.max_lease_ms
    
    def elapsed_ms(self) -> float:
        return (time.time() - self.start_time) * 1000


class SmartConnectionPool:
    """智能连接池管理器"""
    
    def __init__(self, service_name: str, max_connections: int = 50, 
                 high_water_mark: float = 0.8, critical_mark: float = 0.9,
                 wait_timeout: float = 120):
        self.service_name = service_name
        self.max_connections = max_connections
        self.high_water_mark = high_water_mark
        self.critical_mark = critical_mark
        self.wait_timeout = wait_timeout
        
        self.semaphore = threading.Semaphore(max_connections)
        self.active_leases: Dict[str, ConnectionLease] = {}
        self.leases_lock = threading.Lock()
        
        self.stats = {
            'total_requests': 0,
            'active_connections': 0,
            'waiting_connections': 0,
            'timeout_count': 0,
            'leak_count': 0,
            'cleanup_count': 0
        }
        self.stats_lock = threading.Lock()
        
        # 启动监控
        self._start_monitor()
    
    def acquire(self, timeout: Optional[float] = None) -> bool:
        """获取连接许可（简化版，用于装饰器）"""
        timeout = timeout or self.wait_timeout
        
        with self.stats_lock:
            self.waiting_connections += 1
            self.stats['total_requests'] += 1
        
        start_time = time.time()
        acquired = self.semaphore.acquire(timeout=timeout)
        wait_time = time.time() - start_time
        
        with self.stats_lock:
            self.waiting_connections -= 1
            if acquired:
                self.stats['active_connections'] += 1
                if wait_time > 5:
                    logging.warning(f'[ConnPool-{self.service_name}] ⚠️  Waited {wait_time:.1f}s')
            else:
                self.stats['timeout_count'] += 1
                logging.error(f'[ConnPool-{self.service_name}] ❌ Timeout after {wait_time:.1f}s')
        
        return acquired
    
    def release(self):
        """释放连接"""
        with self.stats_lock:
            self.stats['active_connections'] -= 1
        self.semaphore.release()
    
    def _start_monitor(self):
        """监控线程"""
        def monitor_loop():
            while True:
                time.sleep(10)
                usage_rate = self.stats['active_connections'] / self.max_connections
                
                if usage_rate > self.critical_mark:
                    logging.warning(f'[{self.service_name}] 连接池使用率 {usage_rate*100:.1f}% > {self.critical_mark*100}%')
        
        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()
    
    def get_stats(self) -> Dict:
        with self.stats_lock:
            return {
                'service': self.service_name,
                'max_connections': self.max_connections,
                'active': self.stats['active_connections'],
                'waiting': self.stats.get('waiting_connections', 0),
                'usage_rate': f"{self.stats['active_connections'] / self.max_connections * 100:.1f}%",
                'total_requests': self.stats['total_requests'],
                'timeout_count': self.stats['timeout_count']
            }


# ==================== 第二层：异步熔断与流量控制 ====================

class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """熔断器"""
    
    def __init__(self, service_name: str, failure_threshold: int = 5,
                 success_threshold: int = 3, open_duration: int = 60):
        self.service_name = service_name
        self.state = CircuitState.CLOSED
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.open_duration = open_duration
        
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.lock = threading.Lock()
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """熔断调用"""
        with self.lock:
            if self.state == CircuitState.OPEN:
                if time.time() - self.last_failure_time > self.open_duration:
                    logging.info(f'[{self.service_name}] 熔断器进入半开状态')
                    self.state = CircuitState.HALF_OPEN
                else:
                    raise Exception(f'{self.service_name} 服务熔断中')
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _on_success(self):
        with self.lock:
            self.failure_count = 0
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.success_threshold:
                    logging.info(f'[{self.service_name}] 熔断器恢复')
                    self.state = CircuitState.CLOSED
                    self.success_count = 0
    
    def _on_failure(self):
        with self.lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.failure_count >= self.failure_threshold:
                logging.error(f'[{self.service_name}] 熔断器打开，失败次数: {self.failure_count}')
                self.state = CircuitState.OPEN
                self.success_count = 0


class AdaptiveConcurrencyController:
    """自适应并发控制"""
    
    def __init__(self, initial_concurrency: int = 32, min_concurrency: int = 8,
                 max_concurrency: int = 64):
        self.current_concurrency = initial_concurrency
        self.min_concurrency = min_concurrency
        self.max_concurrency = max_concurrency
        
        self.success_count = 0
        self.failure_count = 0
        self.last_adjust_time = time.time()
        
        self.semaphore = threading.Semaphore(initial_concurrency)
        self.lock = threading.Lock()
    
    def acquire(self, timeout: float = 60) -> bool:
        return self.semaphore.acquire(timeout=timeout)
    
    def release(self, success: bool = True):
        self.semaphore.release()
        
        with self.lock:
            if success:
                self.success_count += 1
            else:
                self.failure_count += 1
            
            if time.time() - self.last_adjust_time > 10:
                self._adjust_concurrency()
                self.last_adjust_time = time.time()
    
    def _adjust_concurrency(self):
        total = self.success_count + self.failure_count
        if total == 0:
            return
        
        success_rate = self.success_count / total
        
        if success_rate > 0.95 and self.current_concurrency < self.max_concurrency:
            new_concurrency = min(self.current_concurrency + 8, self.max_concurrency)
            logging.info(f'[并发控制] 成功率 {success_rate:.1%}，增加并发: {self.current_concurrency} → {new_concurrency}')
            self.current_concurrency = new_concurrency
        elif success_rate < 0.8 and self.current_concurrency > self.min_concurrency:
            new_concurrency = max(self.current_concurrency - 8, self.min_concurrency)
            logging.warning(f'[并发控制] 成功率 {success_rate:.1%}，减少并发: {self.current_concurrency} → {new_concurrency}')
            self.current_concurrency = new_concurrency
        
        self.success_count = 0
        self.failure_count = 0


# ==================== 重试装饰器 ====================

def http_retry(max_retries: int = 3, initial_delay: float = 1, service_pool=None):
    """HTTP 请求重试装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            acquired = False
            if service_pool:
                acquired = service_pool.acquire()
                if not acquired:
                    raise Exception(f'{service_pool.service_name} 连接池超时')
            
            try:
                for attempt in range(max_retries):
                    try:
                        return func(*args, **kwargs)
                    except Exception as e:
                        if attempt == max_retries - 1:
                            logging.error(f'[HTTP Retry] 所有 {max_retries} 次重试失败: {e}')
                            raise
                        delay = initial_delay * (2 ** attempt)
                        logging.warning(f'[HTTP Retry] 第 {attempt + 1}/{max_retries} 次失败，{delay}s 后重试')
                        time.sleep(delay)
            finally:
                if acquired and service_pool:
                    service_pool.release()
        return wrapper
    return decorator


def mongodb_retry(max_retries: int = 3, initial_delay: float = 0.5):
    """MongoDB 快速重试装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise
                    delays = [0.5, 1, 2]
                    delay = delays[min(attempt, len(delays)-1)]
                    logging.warning(f'[MongoDB Retry] 第 {attempt+1}/{max_retries} 次失败，{delay}s 后重试')
                    time.sleep(delay)
        return wrapper
    return decorator


# ==================== 全局变量初始化 ====================

# 从配置文件加载
config.load('config.yaml')
config.print_summary()

# 服务配置
SERVER_HOST = config.server_host
SERVER_PORT = config.server_port

# 创建连接池
ENCODER_POOL = SmartConnectionPool(
    'Encoder',
    **config.get_pool_config('encoder')
)
MILVUS_POOL = SmartConnectionPool(
    'Milvus',
    **config.get_pool_config('milvus')
)
RERANKER_POOL = SmartConnectionPool(
    'Reranker',
    **config.get_pool_config('reranker')
)

# 创建熔断器
ENCODER_BREAKER = CircuitBreaker(
    'Encoder',
    **config.get_breaker_config('encoder')
)
MILVUS_BREAKER = CircuitBreaker(
    'Milvus',
    **config.get_breaker_config('milvus')
)
RERANKER_BREAKER = CircuitBreaker(
    'Reranker',
    **config.get_breaker_config('reranker')
)

# 并发控制
CONCURRENCY_CONTROLLER = AdaptiveConcurrencyController(
    **config.get('concurrency_control')
)

# 编码缓存
ENCODE_CACHE = {}
ENCODE_CACHE_LOCK = threading.Lock()
ENCODE_CACHE_MAX_SIZE = config.get('cache', 'encoder', 'max_size', default=2000)
ENCODE_CACHE_HIT = 0
ENCODE_CACHE_MISS = 0

# HTTP Session
HTTP_SESSION = requests.Session()
http_config = config.get('http_session', default={})
HTTP_ADAPTER = requests.adapters.HTTPAdapter(
    pool_connections=http_config.get('pool_connections', 80),
    pool_maxsize=http_config.get('pool_maxsize', 120),
    max_retries=http_config.get('max_retries', 0),
    pool_block=http_config.get('pool_block', True)
)
HTTP_SESSION.mount('http://', HTTP_ADAPTER)
HTTP_SESSION.mount('https://', HTTP_ADAPTER)

# 服务端点
ENCODER_URL = config.get('services', 'encoder', 'url')
MILVUS_URL = config.get('services', 'milvus', 'url')
RERANKER_URL = config.get('services', 'reranker', 'url')
MONGO_URL = config.mongodb_url

# 业务配置
RETRIEVE_CHUNK_NUM = config.get('search', 'retrieve_chunk_num', default=2000)
SCORE_THRESHOLD = config.get('search', 'score_threshold', default=-2)
TOKEN_LIMIT = config.get('search', 'token_limit', default=4000)
CONCAT_CHUNK_NUM = config.get('search', 'concat_chunk_num', default=4)

# MongoDB 配置
MONGO_PARALLEL_WORKERS = config.get('mongodb_query', 'parallel_workers', default=4)
MONGO_BATCH_TIMEOUT = config.get('mongodb_query', 'batch_timeout', default=150)
MONGO_MAX_TIME_MS = config.get('mongodb_query', 'max_time_ms', default=120000)

# 其他全局变量
MONGO_PIPELINE = None
MONGO_PIPELINE_RANK = None
ES = None
ENCODING = None
QUERY_CLASS_MODEL = None
QUERY_CLASS_TOKENIZER = None
KW_ZH_MODEL = None
KW_MODEL = None
PORTER_STEMMER = None
PROFESSIONAL_DICT = set()
MEMORY_KEYWORD_MATCH = {}
MEMORY_QUERY_MATCH = {}

BERT_LOCK = threading.Lock()
JIEBA_LOCK = threading.Lock()

# Flask app
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False

logging.info(f'[Init] 服务初始化完成: {SERVER_HOST}:{SERVER_PORT}')

# ==================== 辅助类和函数 ====================

class BERTClassifier(nn.Module):
    """BERT 分类器"""
    def __init__(self, bert_model_name, num_classes):
        super(BERTClassifier, self).__init__()
        self.bert = BertModel.from_pretrained(bert_model_name)
        self.dropout = nn.Dropout(0.1)
        self.fc = nn.Linear(self.bert.config.hidden_size, num_classes)

    def forward(self, input_ids, attention_mask):
        outputs = self.bert(input_ids=input_ids, attention_mask=attention_mask)
        pooled_output = outputs.pooler_output
        x = self.dropout(pooled_output)
        logits = self.fc(x)
        return logits


class mongodb:
    """MongoDB 连接类"""
    def __init__(self, url, db_name, table_name):
        self.url = url 
        self.db_name = db_name 
        self.table_name = table_name
        self.client = None
        self.db = None
        self.collection = None

    def connect(self):
        """连接 MongoDB"""
        mongo_config = config.get('services', 'mongodb', default={})
        self.client = pymongo.MongoClient(
            self.url, 
            maxPoolSize=mongo_config.get('max_pool_size', 800),
            minPoolSize=mongo_config.get('min_pool_size', 20),
            maxIdleTimeMS=mongo_config.get('max_idle_time_ms', 30000),
            connectTimeoutMS=mongo_config.get('connect_timeout_ms', 90000),
            socketTimeoutMS=mongo_config.get('socket_timeout_ms', 120000),
            serverSelectionTimeoutMS=mongo_config.get('server_selection_timeout_ms', 30000),
            retryReads=mongo_config.get('retry_reads', True),
            retryWrites=mongo_config.get('retry_writes', True),
            waitQueueTimeoutMS=mongo_config.get('wait_queue_timeout_ms', 60000),
            connect=True,
            heartbeatFrequencyMS=mongo_config.get('heartbeat_frequency_ms', 5000),
        )
        self.db = self.client[self.db_name]
        logging.info(f'[MongoDB] 已连接: {self.db_name}')
        self.collection = self.db[self.table_name]
    
    def insert_one(self, data):
        return self.collection.insert_one(data)

    def find_data(self, conditions):
        return self.collection.find(conditions)


def has_chinese(text: str) -> bool:
    """检查是否包含中文"""
    pattern = re.compile(r'[\u4e00-\u9fff]')
    return bool(re.search(pattern, text))


def levenshteinDistance(s1, s2):
    """计算编辑距离"""
    if len(s1) > len(s2):
        s1, s2 = s2, s1
    distances = range(len(s1) + 1)
    for i2, c2 in enumerate(s2):
        distances_ = [i2 + 1]
        for i1, c1 in enumerate(s1):
            if c1 == c2:
                distances_.append(distances[i1])
            else:
                distances_.append(1 + min((distances[i1], distances[i1 + 1], distances_[-1])))
        distances = distances_
    return distances[-1]


def get_cache_stats():
    """获取缓存统计"""
    total = ENCODE_CACHE_HIT + ENCODE_CACHE_MISS
    hit_rate = (ENCODE_CACHE_HIT / total * 100) if total > 0 else 0
    return {
        'size': len(ENCODE_CACHE),
        'hit': ENCODE_CACHE_HIT,
        'miss': ENCODE_CACHE_MISS,
        'hit_rate': f'{hit_rate:.1f}%'
    }


def check_query_relevance(query: str) -> bool:
    """检查查询相关性"""
    with BERT_LOCK:
        QUERY_CLASS_MODEL.eval()
        encoding = QUERY_CLASS_TOKENIZER(query, return_tensors='pt', max_length=128, 
                                         padding='max_length', truncation=True)
        input_ids = encoding['input_ids'].to('cpu')
        attention_mask = encoding['attention_mask'].to('cpu')

        with torch.no_grad():
            outputs = QUERY_CLASS_MODEL(input_ids=input_ids, attention_mask=attention_mask)

        probs = nn.Softmax(dim=0)(torch.squeeze(outputs, dim=0))
        model_score = probs.detach().cpu().numpy()[1]
        flag_query_rel = model_score >= 0.4
    
    logging.info(f'[Query Relevance] score={model_score:.3f}, relevant={flag_query_rel}')
    return flag_query_rel


def get_optimal_batch_size(total_conditions):
    """动态批次大小"""
    if total_conditions < 1000:
        return 32
    elif total_conditions < 2000:
        return 32
    elif total_conditions < 3000:
        return 64
    else:
        return 64


# ==================== 编码服务（带完整响应检查）====================

@http_retry(max_retries=5, initial_delay=10, service_pool=ENCODER_POOL)
def encode_from_net_cached(querys):
    """调用编码服务（带缓存和完整响应检查）"""
    global ENCODE_CACHE_HIT, ENCODE_CACHE_MISS
    
    # 缓存key
    if isinstance(querys, list):
        cache_key = '|'.join([str(q) for q in querys])
    else:
        cache_key = str(querys)
    
    # 检查缓存
    with ENCODE_CACHE_LOCK:
        if cache_key in ENCODE_CACHE:
            ENCODE_CACHE_HIT += 1
            return ENCODE_CACHE[cache_key]
        ENCODE_CACHE_MISS += 1
    
    # 调用服务
    url = ENCODER_URL
    if isinstance(querys, list):
        payload = {"queries": querys}
    else:
        payload = {"queries": [querys]}
    
    headers = {"Content-Type": "application/json"}
    timeout = config.get_timeout('encoder')
    
    # ⭐ 发送请求
    response = HTTP_SESSION.post(url, json=payload, headers=headers, timeout=timeout)
    
    # ⭐ 检查状态码
    if response.status_code != 200:
        error_msg = f'HTTP {response.status_code}: {response.text[:200]}'
        logging.error(f'[Encoder] {error_msg}')
        raise Exception(error_msg)
    
    # ⭐ 检查响应内容
    if not response.text or response.text.strip() == '':
        logging.error(f'[Encoder] 空响应')
        raise Exception('Empty response from encoder')
    
    # ⭐ 检查 Content-Type
    content_type = response.headers.get('Content-Type', '')
    if 'json' not in content_type.lower():
        logging.error(f'[Encoder] 非JSON响应: {content_type}')
        raise Exception(f'Non-JSON response: {content_type}')
    
    # ⭐ 安全解析 JSON
    try:
        result = response.json()
    except json.JSONDecodeError as e:
        logging.error(f'[Encoder] JSON解析失败: {e}, 响应: {response.text[:500]}')
        raise Exception(f'JSON parse error: {e}')
    
    # ⭐ 检查结果格式
    if 'embeddings' not in result:
        logging.error(f'[Encoder] 无效响应格式: {list(result.keys())}')
        raise Exception('Invalid response format')
    
    embeddings = result['embeddings']
    
    # 写入缓存
    with ENCODE_CACHE_LOCK:
        if len(ENCODE_CACHE) >= ENCODE_CACHE_MAX_SIZE:
            cleanup_size = config.get('cache', 'encoder', 'cleanup_size', default=200)
            for _ in range(cleanup_size):
                ENCODE_CACHE.pop(next(iter(ENCODE_CACHE)))
        ENCODE_CACHE[cache_key] = embeddings
    
    return embeddings


# ==================== 召回 Pipeline（带完整响应检查）====================

def recall_pipeline(**kwargs):
    """召回 pipeline"""
    query = kwargs['query']
    query_expand = kwargs.get('query_expand', [query])
    query_embed_expand = kwargs.get('query_embed_expand', [kwargs['query_embed']])
    query_en = kwargs.get('query_en', query)
    result_dict = kwargs.get('result_dict', {})
    
    # 关键词提取
    if has_chinese(query):
        keywords = extract_kws_zh(query, KW_ZH_MODEL, ngram_range=(1, 1))
    else:
        keywords = KW_MODEL.extract_keywords(query)
    kw0 = [k for (k, _) in keywords]

    with JIEBA_LOCK:
        jieba_token_num = sum(1 for _ in jieba.cut(query))
        kw_jieba = jieba.analyse.extract_tags(query, allowPOS=['nz', 'nr', 'vd', 'n', 'vn', 'x', 'eng', 'v'],
                                              topK=jieba_token_num // 2)
    
    kw_zh = []
    kw_zh += kw0
    for kw in kw_jieba:
        kw_zh.append(kw)
    kwargs['kw_zh'] = set(kw_zh)
    
    kw_en = KW_MODEL.extract_keywords(query_en)
    keywords_en_set = set([PORTER_STEMMER.stem(kw[0]) for kw in kw_en])
    kwargs['kw_en'] = keywords_en_set

    logging.info(f'[Recall] keywords_zh={kw_zh[:5]}, keywords_en={list(keywords_en_set)[:5]}')

    # ⭐ Milvus 向量召回（带熔断器和完整响应检查）
    url = MILVUS_URL
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Content-Length': '<calculated when request is sent>',
        'Accept-Encoding': 'gzip, deflate, br'
    }
    
    embed_recall_res = {}
    recall_max_score = 0.0
    
    # 检查连接池
    if not MILVUS_POOL.acquire(timeout=30):
        logging.warning(f'[Recall] ⚠️  Milvus 连接池满，返回部分结果')
        kwargs['result_dict'] = result_dict
        kwargs['flag_query_rel'] = True
        return kwargs
    
    try:
        # 使用熔断器
        def call_milvus():
            results = []
            for query_embed1 in query_embed_expand:
                sent_data = {
                    'topk': RETRIEVE_CHUNK_NUM,
                    'query_vec': json.dumps(query_embed1)
                }
                
                timeout = config.get_timeout('milvus')
                
                # ⭐ 发送请求
                response = HTTP_SESSION.post(url, verify=False, headers=headers, 
                                           data=sent_data, timeout=timeout)
                
                # ⭐ 检查状态码
                if response.status_code != 200:
                    logging.error(f'[Recall] HTTP {response.status_code}: {response.text[:200]}')
                    continue
                
                # ⭐ 检查响应内容
                res_json = response.content.decode('utf-8')
                if not res_json or res_json.strip() == '':
                    logging.error(f'[Recall] 空响应')
                    continue
                
                # ⭐ 安全解析 JSON
                try:
                    res_data = json.loads(res_json)
                except json.JSONDecodeError as e:
                    logging.error(f'[Recall] JSON解析失败: {e}, 响应: {res_json[:500]}')
                    continue
                
                # ⭐ 检查数据格式
                if 'data' not in res_data:
                    logging.error(f'[Recall] 无效响应格式: {list(res_data.keys())}')
                    continue
                
                data_obj = res_data.get('data')
                if not data_obj or 'arr' not in data_obj:
                    logging.error(f'[Recall] 缺少 arr 字段')
                    continue
                
                res_arr = [t.split(':') for t in data_obj.get('arr')]
                results.extend(res_arr)
            
            return results
        
        # 执行熔断调用
        res_arr_all = MILVUS_BREAKER.call(call_milvus)
        
        # 处理结果
        for [id_s, score_s, doc_s] in res_arr_all:
            res_key = (int(id_s), int(doc_s))
            
            if res_key in embed_recall_res:
                embed_recall_res[res_key] = max(float(score_s), embed_recall_res[res_key])
            else:
                embed_recall_res[res_key] = float(score_s)
        
    except Exception as e:
        logging.error(f'[Recall] ⚠️  Milvus 错误: {e}，返回部分结果 ({len(embed_recall_res)} 条)')
    finally:
        MILVUS_POOL.release()
    
    logging.info(f'[Recall] Milvus 返回 {len(embed_recall_res)} 个chunks')
    
    # 填充 result_dict
    for ((index, doc_id), score_s) in embed_recall_res.items():
        dct = {}
        combined_key = f"{index}_{doc_id}"
        dct['index'] = index
        dct['doc_id'] = doc_id
        dct['recall_score'] = score_s
        dct['final_score'] = -1.0
        dct['doc_name'] = 'null'
        dct['recall_channels'] = set(['sentence_embed'])
        result_dict[combined_key] = dct
        if recall_max_score < score_s: 
            recall_max_score = score_s
    
    logging.info(f'[Recall] 总计 {len(result_dict)} chunks, max_score={recall_max_score:.3f}')

    # 检查查询相关性
    key_match_cnt = len(PROFESSIONAL_DICT.intersection(set(kw_zh)))
    if key_match_cnt < 2 and recall_max_score <= 0.5:
        flag_query_rel = True
        for iq in range(len(query_expand)):
            flag_query_rel = check_query_relevance(query_expand[iq])
            if flag_query_rel:
                break
        if not flag_query_rel:
            kwargs['flag_query_rel'] = False
            return kwargs

    kwargs['result_dict'] = result_dict
    kwargs['flag_query_rel'] = True
    return kwargs


# ==================== MongoDB 批量查询 ====================

@mongodb_retry(max_retries=3, initial_delay=0.5)
def query_embeddings_batch(mongo_collection, batch_conditions: List[Dict], 
                          batch_id: str, total_batches: int,
                          timeout: float = 150.0) -> List[Dict]:
    """MongoDB 批量查询（带超时和部分结果）"""
    if not batch_conditions:
        return []

    find_condition = {"$or": batch_conditions}
    projection = {"_id": 0, "index": 1, "doc_id": 1, "embedding": 1}

    total_conditions = len(batch_conditions)
    batch_start = time.time()
    results = []

    logging.info(f"[MongoDB Batch {batch_id}/{total_batches}] 🔄 查询 {total_conditions} 条")

    try:
        cursor = (
            mongo_collection.find(find_condition, projection)
            .max_time_ms(int(timeout * 1000))
        )

        try:
            for doc in cursor:
                results.append(doc)
        finally:
            cursor.close()

        elapsed = time.time() - batch_start
        logging.info(f"[MongoDB Batch {batch_id}/{total_batches}] ✅ {len(results)} 条记录，耗时 {elapsed:.2f}s")
        return results

    except pymongo.errors.ExecutionTimeout as exc:
        elapsed = time.time() - batch_start
        logging.error(f"[MongoDB Batch {batch_id}/{total_batches}] ⏰ 服务端超时 {elapsed:.2f}s: {exc}")
        
        # 拆分查询
        if total_conditions > 150:
            mid = total_conditions // 2
            logging.info(f"[MongoDB Batch {batch_id}/{total_batches}] 🔀 拆分: {mid} + {total_conditions - mid}")
            first_half = query_embeddings_batch(
                mongo_collection, batch_conditions[:mid],
                f"{batch_id}.1", total_batches, timeout
            )
            second_half = query_embeddings_batch(
                mongo_collection, batch_conditions[mid:],
                f"{batch_id}.2", total_batches, timeout
            )
            merged = first_half + second_half
            logging.info(f"[MongoDB Batch {batch_id}/{total_batches}] 🔁 拆分合并 {len(merged)} 条")
            return merged
        
        if results:
            logging.warning(f"[MongoDB Batch {batch_id}/{total_batches}] ⚠️  返回超时前的 {len(results)} 条")
            return results
        raise

    except Exception as exc:
        elapsed = time.time() - batch_start
        logging.error(f"[MongoDB Batch {batch_id}/{total_batches}] ❌ 错误 {elapsed:.2f}s: {exc}")
        if results:
            logging.warning(f"[MongoDB Batch {batch_id}/{total_batches}] ⚠️  返回失败前的 {len(results)} 条")
            return results
        return []


# ==================== 排序 Pipeline ====================

def rank_pipeline(**kwargs):
    """排序 pipeline"""
    query = kwargs['query']
    query_embed = kwargs['query_embed']
    result_dict = kwargs['result_dict']
    
    search_index = [t['index'] for t in result_dict.values()]
    logging.info(f'[Rank] 处理 {len(search_index)} 个chunks')
    
    search_conditions = []
    for key in result_dict.keys():
        if isinstance(key, str) and '_' in key:
            index, doc_id = key.split('_')
            search_conditions.append({
                'index': int(index),
                'doc_id': int(doc_id)
            })
    
    search_start_time = time.time()
    
    # 并行批量查询
    embed_info = {}
    total_conditions = len(search_conditions)
    
    BATCH_SIZE = get_optimal_batch_size(total_conditions)
    total_batches = (total_conditions + BATCH_SIZE - 1) // BATCH_SIZE
    
    logging.info(f'[Rank] 🚀 并行查询: {total_conditions} 条，batch_size={BATCH_SIZE}，batches={total_batches}')
    
    successful_batches = 0
    failed_batches = 0
    partial_results = False
    
    with ThreadPoolExecutor(max_workers=MONGO_PARALLEL_WORKERS) as executor:
        future_to_batch = {}
        
        for i in range(0, total_conditions, BATCH_SIZE):
            batch_id = str(i // BATCH_SIZE + 1)
            batch_conditions = search_conditions[i:i + BATCH_SIZE]
            
            future = executor.submit(
                query_embeddings_batch,
                MONGO_PIPELINE_RANK,
                batch_conditions,
                batch_id,
                total_batches,
                MONGO_BATCH_TIMEOUT
            )
            future_to_batch[future] = batch_id
        
        for future in as_completed(future_to_batch):
            batch_id = future_to_batch[future]
            try:
                batch_results = future.result(timeout=200)

                for record in batch_results:
                    index = record.get('index')
                    doc_id = record.get('doc_id')
                    embedding = record.get('embedding')
                    if index is not None and doc_id is not None:
                        combined_key = f"{index}_{doc_id}"
                        embed_info[combined_key] = embedding

                successful_batches += 1

            except TimeoutError:
                failed_batches += 1
                partial_results = True
                logging.error(f'[Rank] ⏰ Batch {batch_id} 超时')

            except Exception as e:
                failed_batches += 1
                partial_results = True
                logging.error(f'[Rank] ❌ Batch {batch_id} 失败: {str(e)[:100]}')
    
    if partial_results:
        logging.warning(f'[Rank] ⚠️  部分结果: 成功={successful_batches}/{total_batches}, 失败={failed_batches}')
    else:
        logging.info(f'[Rank] ✅ 完成: 成功={successful_batches}/{total_batches}')
    
    logging.info(f'[Rank] 收集 {len(embed_info)} 个 embeddings，耗时 {time.time() - search_start_time:.2f}s')
    
    # 查询切片数据
    find_condition = {'$or': search_conditions} if search_conditions else {}
    try:
        data_iter = list(MONGO_PIPELINE.find_data(find_condition))
    except Exception as e:
        logging.warning(f'[Rank] ⚠️  数据查询失败: {e}')
        data_iter = []
    
    # 处理数据
    for dct in data_iter:
        index = dct['index']
        doc_id = dct['doc_id']
        combined_key = f"{index}_{doc_id}"
        
        if combined_key not in result_dict:
            continue
        
        shard = dct.get('shard', '')
        if len(shard) < 50:
            result_dict.pop(combined_key)
            continue
        
        doc_name = dct.get('doc_name', '')
        title = dct.get('doc_name', '')
        shard = re.sub(r"\[[0-9].{0,5}\]", "", shard)
        
        row = result_dict[combined_key]
        rank_score = 0
        
        row['rank_score'] = rank_score
        row['final_score'] = row.get('recall_score', 0)
        row['doc_name'] = doc_name
        row['title'] = title
        row['doc_id'] = doc_id
        row['shard'] = shard
        row['index'] = index

    logging.info(f'[Rank] 总耗时: {time.time() - search_start_time:.2f}s')
    kwargs['partial_results'] = partial_results
    return kwargs


# ==================== 轻量级重排（降级策略）====================

def lightweight_rerank_mode(**kwargs):
    """轻量级重排模式（降级策略）"""
    logging.info('[Rerank] ⚡ 轻量级重排模式')
    
    query = kwargs['query']
    result_dict = kwargs['result_dict']
    kw_zh = kwargs.get('kw_zh', set())
    kw_en = kwargs.get('kw_en', set())
    
    processed_count = 0
    skipped_count = 0
    
    for combined_key, chunk_data in result_dict.items():
        if 'shard' not in chunk_data or 'final_score' not in chunk_data:
            skipped_count += 1
            continue
            
        shard = chunk_data['shard']
        base_score = chunk_data['final_score']
        
        # 关键词匹配分数
        match_score = 0.0
        match_cnt = 0
        
        if has_chinese(shard):
            for kw in kw_zh:
                if kw in shard:
                    match_cnt += 1
        else:
            tokens_set = set([PORTER_STEMMER.stem(t) for t in re.split(r'[,\n;!?. ~]', shard)])
            match_cnt = len(tokens_set.intersection(kw_en))
        
        # 计算匹配比例
        if has_chinese(shard) and kw_zh:
            kw_num = len(kw_zh)
        elif not has_chinese(shard) and kw_en:
            kw_num = len(kw_en)
        else:
            kw_num = 1
        
        if match_cnt > 0:
            match_ratio = match_cnt / kw_num
            match_score = 0.5 + 0.5 * (1 - 1/(1 + match_ratio*2))
        else:
            match_score = 0.5
        
        # 最终分数：原始60% + 关键词40%
        final_score = base_score * 0.6 + match_score * 0.4
        
        chunk_data['rerank_score'] = final_score
        chunk_data['final_score'] = final_score
        chunk_data['match_cnt'] = match_cnt
        chunk_data['match_score'] = match_score
        chunk_data['rerank_mode'] = 'lightweight'
        
        processed_count += 1
    
    logging.info(f'[Rerank] ✅ 轻量级重排: 处理{processed_count}，跳过{skipped_count}')
    kwargs['result_dict'] = result_dict
    return kwargs


# ==================== 重排 Pipeline ====================

def rerank_pipeline(**kwargs):
    """重排 pipeline（带熔断器和降级策略）"""
    logging.info('[Rerank] 开始重排')
    
    query = kwargs['query']
    result_dict = kwargs['result_dict']
    
    # 检查 Reranker 连接池
    if not RERANKER_POOL.acquire(timeout=60):
        logging.warning(f'[Rerank] ⚠️  Reranker 连接池忙，使用轻量级重排')
        return lightweight_rerank_mode(**kwargs)
    
    try:
        # 使用熔断器
        def call_reranker():
            bge_server_url = RERANKER_URL
            bge_score_weight = 3.0
            
            sorted_top_chunk = sorted(result_dict.items(), key=lambda d: -d[1].get('final_score', 0))
            result_dict_sorted = {}
            bge_score_buff_dict = [[], []]
            
            for index in range(len(sorted_top_chunk)):
                combined_key = sorted_top_chunk[index][0]
                chunk_data = sorted_top_chunk[index][1]
                
                if 'shard' not in chunk_data:
                    continue
                    
                result_dict_sorted[combined_key] = chunk_data
                
                if index < 300:
                    bge_score_buff_dict[0].append(combined_key)
                    bge_score_buff_dict[1].append([query, chunk_data['shard']])
                    
                    if len(bge_score_buff_dict[0]) == 20:
                        bge_multi_data = {'type': 'multi', 'multi_data': bge_score_buff_dict[1]}
                        
                        timeout = config.get_timeout('reranker')
                        
                        # ⭐ 发送请求
                        response = HTTP_SESSION.post(
                            bge_server_url, 
                            data=json.dumps(bge_multi_data), 
                            timeout=timeout
                        )
                        
                        # ⭐ 检查状态码
                        if response.status_code != 200:
                            logging.warning(f'[Rerank] HTTP {response.status_code}，使用默认分数')
                            for combined_key in bge_score_buff_dict[0]:
                                result_dict_sorted[combined_key]['rerank_score'] = result_dict_sorted[combined_key]['final_score']
                            bge_score_buff_dict = [[], []]
                            continue
                        
                        # ⭐ 检查响应内容
                        if not response.text or response.text.strip() == '':
                            logging.warning(f'[Rerank] 空响应，使用默认分数')
                            for combined_key in bge_score_buff_dict[0]:
                                result_dict_sorted[combined_key]['rerank_score'] = result_dict_sorted[combined_key]['final_score']
                            bge_score_buff_dict = [[], []]
                            continue
                        
                        # ⭐ 安全解析 JSON
                        try:
                            bge_result = response.json()
                        except json.JSONDecodeError as e:
                            logging.warning(f'[Rerank] JSON解析失败: {e}，使用默认分数')
                            for combined_key in bge_score_buff_dict[0]:
                                result_dict_sorted[combined_key]['rerank_score'] = result_dict_sorted[combined_key]['final_score']
                            bge_score_buff_dict = [[], []]
                            continue
                        
                        # ⭐ 检查数据格式
                        if 'score' not in bge_result:
                            logging.warning(f'[Rerank] 无效格式: {list(bge_result.keys())}，使用默认分数')
                            for combined_key in bge_score_buff_dict[0]:
                                result_dict_sorted[combined_key]['rerank_score'] = result_dict_sorted[combined_key]['final_score']
                            bge_score_buff_dict = [[], []]
                            continue
                        
                        bge_rerank_score_list = bge_result['score']
                        
                        # 处理分数
                        for score_index in range(len(bge_rerank_score_list)):
                            rank_score = result_dict_sorted[bge_score_buff_dict[0][score_index]]['final_score'] + \
                                    bge_score_weight * bge_rerank_score_list[score_index]
                            result_dict_sorted[bge_score_buff_dict[0][score_index]]['rerank_score'] = rank_score
                            result_dict_sorted[bge_score_buff_dict[0][score_index]]['final_score'] = rank_score
                        
                        bge_score_buff_dict = [[], []]
                else:
                    bge_rerank_score = -8.0
                    rank_score = result_dict_sorted[combined_key]['final_score'] + bge_score_weight + bge_rerank_score
                    result_dict_sorted[combined_key]['rerank_score'] = rank_score
                    result_dict_sorted[combined_key]['final_score'] = rank_score

            # 处理剩余
            if len(bge_score_buff_dict[0]) > 0:
                bge_multi_data = {'type': 'multi', 'multi_data': bge_score_buff_dict[1]}
                try:
                    timeout = config.get_timeout('reranker')
                    response = HTTP_SESSION.post(
                        bge_server_url, 
                        data=json.dumps(bge_multi_data), 
                        timeout=timeout
                    )
                    if response.status_code == 200 and response.text:
                        bge_result = response.json()
                        if 'score' in bge_result:
                            bge_rerank_score_list = bge_result['score']
                            for score_index in range(len(bge_rerank_score_list)):
                                rank_score = result_dict_sorted[bge_score_buff_dict[0][score_index]]['final_score'] + \
                                                bge_score_weight * bge_rerank_score_list[score_index]
                                result_dict_sorted[bge_score_buff_dict[0][score_index]]['rerank_score'] = rank_score
                                result_dict_sorted[bge_score_buff_dict[0][score_index]]['final_score'] = rank_score
                except Exception as e:
                    logging.warning(f'[Rerank] 最后批次失败: {e}')
            
            return result_dict_sorted
        
        # 执行熔断调用
        result_dict_sorted = RERANKER_BREAKER.call(call_reranker)
        result_dict = result_dict_sorted
        
    except Exception as e:
        logging.error(f'[Rerank] 失败: {e}，降级到轻量级重排')
        return lightweight_rerank_mode(**kwargs)
    finally:
        RERANKER_POOL.release()
    
    # 关键词匹配调权
    kw_zh = kwargs.get('kw_zh', set())
    kw_en = kwargs.get('kw_en', set())
    kw_num = len(kw_zh) if kw_zh else 1
    
    for (combined_key, row) in result_dict.items():
        match_cnt = 0
        if row.get('final_score', 0) < 0.4 or 'shard' not in row:
            continue
        
        shard = row['shard']
        
        if has_chinese(shard):
            for kw in kw_zh:
                if kw in shard: 
                    match_cnt += 1
        else:
            tokens_set = set([PORTER_STEMMER.stem(t) for t in re.split(r'[,\n;!?. ~]', shard)])
            match_cnt = len(tokens_set.intersection(kw_en))

        match_score = (0.95 + pow(match_cnt / kw_num, 2)) if kw_num > 0 else 0.001
        row['match_cnt'] = match_cnt
        row['match_score'] = match_score
        row['final_score'] = row.get('final_score', 0) * match_score

    kwargs['result_dict'] = result_dict
    return kwargs


# ==================== 拼接 Chunks ====================

def mmrStep(lambda_param: float, selectedDocs: list, sorteddDocs: list, simMatrix: dict):
    """MMR 算法"""
    mmr = -9999.999
    res_index = -1
    
    if not selectedDocs:
        selectedDocs.append(0)
        return

    for list_idx, infoDict in enumerate(sorteddDocs):
        if list_idx in selectedDocs:
            continue
        
        mmr_score = lambda_param * infoDict.get('final_score', 0.0)
        current_index = infoDict['index']
        
        diversity_score = max(
            [simMatrix.get(
                (min(current_index, sorteddDocs[selected_list_idx]['index']), 
                 max(current_index, sorteddDocs[selected_list_idx]['index'])), 
                0.0
            ) for selected_list_idx in selectedDocs]
        )
        
        mmr_score -= (1 - lambda_param) * diversity_score * 30
        
        if mmr_score > mmr:
            mmr = mmr_score
            res_index = list_idx

    if res_index != -1:
        selectedDocs.append(res_index)
    return


def concat_shards_by_rank(**kwargs):
    """拼接 chunks"""
    query = kwargs['query']
    result_dict = kwargs['result_dict']
    top_doc_num = kwargs['top_doc_num']

    sorted_top_chunk = sorted(list(result_dict.values()), key=lambda d: -d.get('final_score', 0))
    
    simMatrix = {}
    if top_doc_num <= 5:
        sim_num = 5 * 5 + 30
    else:
        sim_num = top_doc_num * 5 + 30
    
    selectedDocs = []
    sim_num = min(sim_num, len(sorted_top_chunk))
    for i in range(sim_num):
        mmrStep(0.9, selectedDocs, sorted_top_chunk, simMatrix)

    res_arr_dict = {}
    res_arr = []
    res_num = 0

    this_chunk_num = 0
    this_index = []
    this_res = {}
    this_docs = []
    this_doc_ids = []
    this_shard = []
    this_title = []
    this_num_token = 0
    this_scores = 0.0

    for selected_index in selectedDocs:
        chunk_data = sorted_top_chunk[selected_index]
        
        doc_name = chunk_data.get('doc_name', '')
        shard = chunk_data.get('shard', '')
        index = chunk_data.get('index', 0)
        title = chunk_data.get('title', '')
        doc_id = chunk_data.get('doc_id', 0)

        tokens = ENCODING.encode(shard)
        this_num_token += len(tokens)
        this_shard.append(shard)
        this_index.append(index)
        this_title.append(title)
        this_chunk_num += 1
        this_scores += chunk_data.get('final_score', 0)

        this_docs.append(doc_name)
        this_doc_ids.append(doc_id)

        if this_num_token >= TOKEN_LIMIT:
            this_res['text'] = this_shard
            this_res['ans_id'] = res_num
            this_res['doc_name'] = this_docs
            this_res['doc_id'] = this_doc_ids
            this_res['index'] = this_index
            this_res['title'] = this_title
            this_res['score'] = this_scores / this_chunk_num
            this_res['concat_score'] = 0.5
            
            res_arr_dict[(this_res['score'], tuple(this_res['text']))] = this_res

            this_chunk_num = 0
            this_res = {}
            this_docs = []
            this_doc_ids = []
            this_shard = []
            this_index = []
            this_title = []
            this_num_token = 0
            this_scores = 0.0
            res_num += 1
        
        if res_num >= top_doc_num:
            break
    
    sorted_res_arr_dict = sorted(res_arr_dict.items(), key=lambda d: -d[0][0]) 
    for item_index, sorted_item in enumerate(sorted_res_arr_dict):
        sorted_item[1]['ans_id'] = item_index
        res_arr.append(sorted_item[1])

    return res_arr


# ==================== 数据加载 ====================

def load_data(table: str):
    """加载全局数据"""
    logging.info('🔄 加载全局数据...')
    start_time = time.time()

    global ENCODING
    global MONGO_PIPELINE
    global MONGO_PIPELINE_RANK
    global QUERY_CLASS_MODEL
    global QUERY_CLASS_TOKENIZER
    global PROFESSIONAL_DICT
    global MEMORY_KEYWORD_MATCH
    global MEMORY_QUERY_MATCH
    global KW_ZH_MODEL
    global KW_MODEL
    global PORTER_STEMMER
    global ES

    # MongoDB 连接
    mongo_db = config.mongodb_database
    MONGO_PIPELINE = mongodb(MONGO_URL, mongo_db, table)
    MONGO_PIPELINE.connect()
    
    # MongoDB Rank 连接
    mongo_config = config.get('services', 'mongodb', default={})
    client = pymongo.MongoClient(
        MONGO_URL, 
        maxPoolSize=mongo_config.get('max_pool_size', 800),
        minPoolSize=mongo_config.get('min_pool_size', 20),
        maxIdleTimeMS=mongo_config.get('max_idle_time_ms', 30000),
        connectTimeoutMS=mongo_config.get('connect_timeout_ms', 90000),
        socketTimeoutMS=mongo_config.get('socket_timeout_ms', 120000),
        serverSelectionTimeoutMS=mongo_config.get('server_selection_timeout_ms', 30000),
        retryReads=mongo_config.get('retry_reads', True),
        retryWrites=mongo_config.get('retry_writes', True),
        waitQueueTimeoutMS=mongo_config.get('wait_queue_timeout_ms', 60000),
        connect=True,
        heartbeatFrequencyMS=mongo_config.get('heartbeat_frequency_ms', 5000),
    )
    db = client[mongo_db]
    MONGO_PIPELINE_RANK = db[config.mongodb_collection]
    
    logging.info(f'[MongoDB] Rank collection 已连接')

    # Elasticsearch
    es_url = config.get('services', 'elasticsearch', 'url')
    ES = Elasticsearch(es_url)
    logging.info(f'[Elasticsearch] 已连接: {es_url}')

    # 加载用户词典
    user_dict_path = config.get('models', 'user_dict', default='config/ext_dict2.dct')
    jieba.load_userdict(user_dict_path)
    logging.info(f'[Jieba] 用户词典加载: {user_dict_path}')
    
    # Token编码器
    token_model = config.get('search', 'token_encode_model', default='gpt-3.5-turbo')
    ENCODING = tiktoken.encoding_for_model(token_model)

    # 查询分类模型
    classifier_config = config.get('models', 'query_classifier', default={})
    model_path = classifier_config.get('model_path', '/home/tcl/rqa_dir/query_class_model/bert-base-chinese')
    checkpoint_path = classifier_config.get('checkpoint_path', '/home/tcl/rqa_dir/query_class_model/query_classifier1.pth')
    
    QUERY_CLASS_MODEL = BERTClassifier(model_path, 2).to('cpu')
    QUERY_CLASS_TOKENIZER = BertTokenizer.from_pretrained(model_path)
    
    ckpt = torch.load(checkpoint_path, map_location=torch.device('cpu'))
    QUERY_CLASS_MODEL.load_state_dict(ckpt, strict=False)
    logging.info(f'[Model] 查询分类模型加载完成')

    # 专业词典
    fkw = open(user_dict_path, encoding='utf-8')
    for line in fkw:
        PROFESSIONAL_DICT.add(line.strip('\n'))
    fkw.close()
    logging.info(f'[Dict] 专业词典: {len(PROFESSIONAL_DICT)} 词')

    # 记忆关键词
    memory_keywords_path = config.get('models', 'memory_keywords', default='config/memory_keywords_recall_v20230916.txt')
    MEMORY_QUERY_MATCH, MEMORY_KEYWORD_MATCH = read_keywords_with_score_from_memory(memory_keywords_path)
    logging.info(f'[Memory] 关键词匹配: {len(MEMORY_KEYWORD_MATCH)} 条')

    # 关键词提取模型
    kw_config = config.get('models', 'keyword_extractor', default={})
    zh_model = kw_config.get('zh_model', '/mnt/hdd1/haoyangliu/em_model/kw/paraphrase-multilingual-MiniLM-L12-v2')
    en_model = kw_config.get('en_model', '/mnt/hdd1/haoyangliu/em_model/kw/paraphrase-multilingual-MiniLM-L12-v2')
    
    KW_ZH_MODEL = KeyBERT(model=zh_model)
    KW_MODEL = KBERT(model=en_model)
    PORTER_STEMMER = PorterStemmer()
    logging.info(f'[Model] 关键词提取模型加载完成')

    logging.info(f'✅ 全局数据加载完成，耗时 {time.time() - start_time:.2f}s')


def warmup_services():
    """预热服务连接"""
    logging.info('🔥 [Warmup] 测试服务连接...')
    
    # 测试编码服务
    try:
        test_query = "test connection"
        encode_from_net_cached(test_query)
        logging.info('[Warmup] ✅ 编码服务 OK')
    except Exception as e:
        logging.warning(f'[Warmup] ⚠️  编码服务不可用: {e}')
    
    # 测试 Milvus
    try:
        response = HTTP_SESSION.get(config.get('services', 'milvus', 'url').rsplit('/', 1)[0], timeout=(5, 10))
        logging.info('[Warmup] ✅ Milvus 服务 OK')
    except Exception as e:
        logging.warning(f'[Warmup] ⚠️  Milvus 服务不可用: {e}')
    
    logging.info('[Warmup] 服务预热完成')


def crontab_update_config():
    """定时更新配置"""
    try:
        # 重新加载配置
        config.load('config.yaml')
        logging.info('[Config] ✓ 配置已更新')
    except Exception as e:
        logging.error(f'[Config] 更新失败: {e}')


# ==================== Flask 路由 ====================

@app.route('/api-rqa-search/test', methods=['GET'])
def hello_world():
    return jsonify({'code': 0, 'msg': '', 'data': 'Service available'})


@app.route('/api-rqa-search/stats', methods=['GET'])
def get_stats():
    """获取服务统计信息"""
    stats = {
        'server': {
            'host': SERVER_HOST,
            'port': SERVER_PORT,
            'version': config.get('misc', 'version', default='v2.0')
        },
        'encode_cache': get_cache_stats(),
        'connection_pools': {
            'encoder': ENCODER_POOL.get_stats(),
            'milvus': MILVUS_POOL.get_stats(),
            'reranker': RERANKER_POOL.get_stats(),
        },
        'circuit_breakers': {
            'encoder': {'state': ENCODER_BREAKER.state.value, 'failures': ENCODER_BREAKER.failure_count},
            'milvus': {'state': MILVUS_BREAKER.state.value, 'failures': MILVUS_BREAKER.failure_count},
            'reranker': {'state': RERANKER_BREAKER.state.value, 'failures': RERANKER_BREAKER.failure_count},
        },
        'concurrency': {
            'current': CONCURRENCY_CONTROLLER.current_concurrency,
            'min': CONCURRENCY_CONTROLLER.min_concurrency,
            'max': CONCURRENCY_CONTROLLER.max_concurrency,
        }
    }
    return jsonify({'code': 0, 'msg': '', 'data': stats})


@app.route('/api-rqa-search/search', methods=['POST'])
def get_data():
    """搜索服务主函数"""
    form = request.form
    query = form.get('query', '', str)
    query_en = form.get('query_dst', '', str)
    id = form.get('id', 0, int)
    top_doc_num = form.get('top_doc_num', 0, int)
    
    if query == '':
        return jsonify({'code': -1, 'msg': 'query 不能为空', 'data': None}), 400
    if id == 0:
        return jsonify({'code': -1, 'msg': 'id 不能为空', 'data': None}), 400
    if top_doc_num == 0:
        return jsonify({'code': -1, 'msg': 'top_doc_num 不能为空', 'data': None}), 400

    start_time = time.time()
    code = 0
    msg = ''
    data = {}
    data['model'] = config.get('models', 'encoder_model', default='unknown')
    data['version'] = config.get('misc', 'version', default='v2.0')

    # 获取并发许可
    if not CONCURRENCY_CONTROLLER.acquire(timeout=60):
        return jsonify({
            'code': -1, 
            'msg': '服务繁忙，请稍后重试', 
            'data': {'arr': [], 'doc_num': 0}
        }), 503

    success = False
    try:
        json_arr = []
        
        logging.info(f'[Request] query="{query[:50]}...", top_doc_num={top_doc_num}')
        
        # 编码服务
        try:
            query_embed = encode_from_net_cached(query)
            query_rank_embed = query_embed
        except Exception as e:
            logging.error(f'[RAG服务] 编码失败: {e}')
            return jsonify({
                'code': -1, 
                'msg': f'编码服务不可用: {str(e)}', 
                'data': {'arr': [], 'doc_num': 0}
            }), 503
        
        result_dict = {}
        params = {}
        params['id'] = id
        params['query'] = query
        
        if has_chinese(query):
            params['query_zh'] = query
            params['query_en'] = query_en if query_en else query
        else:
            params['query_en'] = query
            params['query_zh'] = query
        
        query_expand = [query]
        params['query_expand'] = query_expand
        params['query_embed'] = query_embed
        params['query_embed_expand'] = [query_embed]
        params['query_rank_embed'] = query_rank_embed
        params['query_rank_embed_expand'] = [query_rank_embed]
        params['flag_query_rel'] = True
        
        if len(query_en.strip()) > 0:
            params['query_en'] = query_en
        params['result_dict'] = result_dict
        
        # Pipeline 执行
        recall_start = time.time()
        params = recall_pipeline(**params)
        logging.info(f'[Timing] Recall: {time.time() - recall_start:.2f}s')
        
        if not params['flag_query_rel']:
            code = 1
            data['msg'] = '查询与领域不相关'
            data['doc_num'] = 0
            data['arr'] = []
            return jsonify({'code': code, 'msg': msg, 'data': data})

        rank_start = time.time()
        params = rank_pipeline(**params)
        logging.info(f'[Timing] Rank: {time.time() - rank_start:.2f}s')
        
        # 检查部分结果
        if params.get('partial_results', False):
            data['partial_results'] = True
            data['warning'] = '部分数据源超时，返回部分结果'
        
        rerank_start = time.time()
        params = rerank_pipeline(**params)
        logging.info(f'[Timing] Rerank: {time.time() - rerank_start:.2f}s')
        
        params['top_doc_num'] = top_doc_num

        concat_start = time.time()
        similar_shards = concat_shards_by_rank(**params)
        logging.info(f'[Timing] Concat: {time.time() - concat_start:.2f}s')
        
        for dict in similar_shards:
            score = dict.get('score', 0)
            if score < SCORE_THRESHOLD:
                break
            json_arr.append(dict)
        
        data['arr'] = json_arr
        data['doc_num'] = len(json_arr)
        success = True

    except Exception as e:
        code = -1
        msg = str(e)
        data['msg'] = msg
        data['doc_num'] = 0
        data['arr'] = []
        logging.error(f'[ERROR] {traceback.format_exc()}')
        return jsonify({'code': code, 'msg': msg, 'data': data}), 500
    finally:
        # 释放并发许可
        CONCURRENCY_CONTROLLER.release(success=success)

    now = datetime.datetime.now()
    data['ts'] = int(datetime.datetime.timestamp(now) * 1000)
    
    total_time = time.time() - start_time
    logging.info(f'[Request] ✅ 总耗时: {total_time:.2f}s, 结果: {len(json_arr)} 条')
    logging.info(f'[Cache] {get_cache_stats()}')
    
    http_status = 200 if code == 0 else 500
    return jsonify({'code': code, 'msg': msg, 'data': data}), http_status


# ==================== 主程序 ====================

if __name__ == '__main__':
    faulthandler.enable()
    
    print(f'\n{"="*80}')
    print(f'RAG 搜索服务 - 改进版 v2.0')
    print(f'{"="*80}')
    print(f'启动地址: http://{SERVER_HOST}:{SERVER_PORT}')
    print(f'配置文件: config.yaml')
    print(f'{"="*80}\n')
    
    # 定时任务调度器
    scheduler = BackgroundScheduler()
    scheduler.add_job(crontab_update_config, 'interval', seconds=180, 
                     coalesce=True, replace_existing=True)
    scheduler.start()
    
    # 加载数据
    table_name = config.mongodb_collection
    load_data(table_name)
    
    # 预热服务
    if config.get('misc', 'warmup_on_startup', default=True):
        warmup_services()
    
    # 打印配置摘要
    print(f'\n{"="*80}')
    print(f'服务就绪')
    print(f'{"="*80}')
    print(f'连接池:')
    print(f'  Encoder: {ENCODER_POOL.get_stats()}')
    print(f'  Milvus: {MILVUS_POOL.get_stats()}')
    print(f'  Reranker: {RERANKER_POOL.get_stats()}')
    print(f'熔断器:')
    print(f'  全部就绪')
    print(f'并发控制:')
    print(f'  初始并发: {CONCURRENCY_CONTROLLER.current_concurrency}')
    print(f'  最小-最大: {CONCURRENCY_CONTROLLER.min_concurrency}-{CONCURRENCY_CONTROLLER.max_concurrency}')
    print(f'{"="*80}\n')
    
    logging.info(f'✅ 服务启动: http://{SERVER_HOST}:{SERVER_PORT}')
    
    # 启动 Flask 服务
    app.run(SERVER_HOST, port=SERVER_PORT, threaded=True, processes=1)

