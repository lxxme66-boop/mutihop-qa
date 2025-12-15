# RAG 搜索服务 - 改进版 v2.0

完整的 RAG 搜索服务改进版，集成连接池、熔断器、并发控制、监控告警四层防护架构。

## 🎯 核心改进

### 1. 完整的响应检查机制 ✅
所有 HTTP 请求都经过严格检查：
- ✅ 检查 HTTP 状态码
- ✅ 检查响应内容是否为空
- ✅ 检查 Content-Type 是否为 JSON
- ✅ 安全的 JSON 解析（try-except）
- ✅ 验证必需字段

### 2. 正确的超时配置 ✅
恢复到原版的超时时间：
- **Encoder**: 240s 连接 + 480s 读取（原版：240/480）
- **Milvus**: 360s 连接 + 720s 读取（原版：360/720）
- **Reranker**: 360s 连接 + 720s 读取（原版：360/720）

### 3. 四层防护架构 ✅

#### 第一层：连接状态一致性
- `SmartConnectionPool`: 智能连接池
- 连接租约管理
- 高水位自动清理
- 泄漏检测

#### 第二层：异步熔断与流量控制
- `CircuitBreaker`: 熔断器
- `AdaptiveConcurrencyController`: 自适应并发控制
- 自动降级策略

#### 第三层：批处理与智能调度
- MongoDB 批量查询优化
- 超时自动拆分
- 部分结果返回

#### 第四层：全景监控与自愈
- 实时统计信息
- 连接池监控
- 熔断器状态监控

## 📁 文件结构

```
.
├── config.yaml                    # 配置文件（核心）
├── config_loader.py               # 配置加载模块
├── search_service_improved.py     # 主服务代码
├── start.sh                       # 启动脚本
├── README_IMPROVED.md             # 本文档
└── config/                        # 配置目录
    ├── ext_dict2.dct             # 用户词典
    └── memory_keywords_recall_v20230916.txt
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install pyyaml pymongo requests flask elasticsearch \
    sentence-transformers zhkeybert keybert tiktoken \
    transformers torch nltk jieba apscheduler
```

### 2. 检查配置

编辑 `config.yaml`，确认所有服务端点正确：

```yaml
services:
  encoder:
    url: "http://8.130.183.20:8031/encode"  # 修改为你的地址
  milvus:
    url: "http://8.130.183.20:8033/api-vec-search/search"
  reranker:
    url: "http://8.130.183.20:8032/query_bge_reranker/"
  mongodb:
    url: "mongodb://root:example@10.70.223.31:27017"
  elasticsearch:
    url: "http://10.70.222.234:9200"
```

### 3. 启动服务

```bash
# 方式 1：前台运行（推荐用于测试）
bash start.sh

# 方式 2：直接运行
python3 search_service_improved.py

# 方式 3：后台运行
nohup python3 search_service_improved.py > logs/service.log 2>&1 &
```

### 4. 测试服务

```bash
# 健康检查
curl http://localhost:9510/api-rqa-search/test

# 查看统计信息
curl http://localhost:9510/api-rqa-search/stats

# 搜索请求
curl -X POST http://localhost:9510/api-rqa-search/search \
  -d "query=什么是IGZO&id=1&top_doc_num=5"
```

## 📊 监控统计

访问 `/api-rqa-search/stats` 查看实时统计：

```json
{
  "code": 0,
  "data": {
    "server": {
      "host": "0.0.0.0",
      "port": 9510,
      "version": "v2.0"
    },
    "encode_cache": {
      "size": 150,
      "hit": 80,
      "miss": 70,
      "hit_rate": "53.3%"
    },
    "connection_pools": {
      "encoder": {
        "service": "Encoder",
        "max_connections": 48,
        "active": 5,
        "usage_rate": "10.4%",
        "timeout_count": 0
      },
      ...
    },
    "circuit_breakers": {
      "encoder": {
        "state": "closed",
        "failures": 0
      },
      ...
    },
    "concurrency": {
      "current": 32,
      "min": 8,
      "max": 64
    }
  }
}
```

## 🔧 配置说明

### 超时配置

在 `config.yaml` 中调整超时：

```yaml
services:
  encoder:
    connect_timeout: 240  # 连接超时（秒）
    read_timeout: 480     # 读取超时（秒）
```

**建议值**：
- **快服务**（Encoder, Milvus）: 240/480 秒
- **慢服务**（Reranker, MongoDB）: 360/720 秒

### 连接池配置

```yaml
connection_pools:
  encoder:
    max_connections: 48      # 最大连接数
    high_water_mark: 0.8     # 80% 触发预防性清理
    critical_mark: 0.9       # 90% 触发强制清理
    max_lease_ms: 120000     # 最大租约时间（毫秒）
```

### 熔断器配置

```yaml
circuit_breakers:
  encoder:
    failure_threshold: 10    # 失败多少次触发熔断
    success_threshold: 3     # 成功多少次恢复
    open_duration: 60        # 熔断持续时间（秒）
```

**快服务 vs 慢服务**：
- **快服务**: `failure_threshold: 10`（更宽容）
- **慢服务**: `failure_threshold: 5`（更敏感）

### 并发控制

```yaml
concurrency_control:
  initial_concurrency: 32  # 初始并发数
  min_concurrency: 8       # 最小并发数
  max_concurrency: 64      # 最大并发数
  success_rate_threshold: 0.95  # 目标成功率
```

## 🐛 故障排查

### 问题 1: JSON 解析错误 `Expecting value: line 1 column 1 (char 0)`

**原因**: 外部服务返回空响应

**解决**:
1. 检查外部服务状态（8.130.183.20）
2. 查看服务日志
3. 熔断器会自动降级

**检查命令**:
```bash
# 测试编码服务
curl -X POST http://8.130.183.20:8031/encode \
  -H "Content-Type: application/json" \
  -d '{"queries":["test"]}' -v

# 测试 Milvus
curl -X POST http://8.130.183.20:8033/api-vec-search/search \
  -d "topk=10&query_vec=[0.1,0.2,0.3]" -v
```

### 问题 2: 连接超时错误

**原因**: 超时配置过短或服务负载过高

**解决**:
1. 增加超时时间（`config.yaml` 中的 `connect_timeout` 和 `read_timeout`）
2. 检查外部服务负载
3. 增加连接池大小

### 问题 3: 熔断器频繁打开

**原因**: 外部服务不稳定

**解决**:
1. 检查外部服务状态
2. 增加 `failure_threshold`（容忍更多失败）
3. 增加 `open_duration`（延长恢复时间）

### 问题 4: MongoDB 查询超时

**原因**: 批量查询数据量大

**解决**:
1. 增加 `mongodb_query.batch_timeout`（默认 150秒）
2. 减小 `batch_size`（默认 32）
3. 检查 MongoDB 索引

## 📈 性能优化建议

### 1. 根据硬件调整连接池

**低配服务器**（4核8G）:
```yaml
connection_pools:
  encoder:
    max_connections: 24
  milvus:
    max_connections: 32
  reranker:
    max_connections: 100
```

**高配服务器**（16核32G）:
```yaml
connection_pools:
  encoder:
    max_connections: 96
  milvus:
    max_connections: 128
  reranker:
    max_connections: 400
```

### 2. 根据负载调整并发

**低负载**（< 10 QPS）:
```yaml
concurrency_control:
  initial_concurrency: 16
  max_concurrency: 32
```

**高负载**（> 100 QPS）:
```yaml
concurrency_control:
  initial_concurrency: 64
  max_concurrency: 128
```

### 3. 启用缓存

编码缓存可以大幅提升性能：

```yaml
cache:
  encoder:
    enabled: true
    max_size: 5000  # 增加缓存容量
    ttl: 7200       # 延长过期时间
```

## 🆚 原版 vs 改进版对比

| 特性 | 原版 | 改进版 | 说明 |
|------|------|--------|------|
| **响应检查** | ❌ 缺失 | ✅ 完整 | 所有 HTTP 请求都有检查 |
| **超时配置** | ✅ 正确 | ✅ 正确 | 保持原版超时时间 |
| **连接池** | ✅ 简单版 | ✅ 智能版 | 租约管理、泄漏检测 |
| **熔断器** | ❌ 无 | ✅ 有 | 自动降级、自动恢复 |
| **并发控制** | ❌ 无 | ✅ 自适应 | 根据成功率动态调整 |
| **监控统计** | ❌ 无 | ✅ 完整 | 实时监控、告警 |
| **降级策略** | ❌ 无 | ✅ 有 | 轻量级重排 |
| **配置管理** | ⚠️  散乱 | ✅ 统一 | YAML 配置文件 |

## 🔍 日志说明

### 正常日志

```
[Recall] keywords_zh=['IGZO', 'TFT'], keywords_en=['oxide', 'semiconductor']
[Recall] Milvus 返回 1523 个chunks
[Recall] 总计 1523 chunks, max_score=0.856
[Rank] 🚀 并行查询: 1523 条，batch_size=64，batches=24
[Rank] ✅ 完成: 成功=24/24
[Rerank] 开始重排
[Request] ✅ 总耗时: 3.45s, 结果: 5 条
```

### 异常日志（触发降级）

```
ERROR:root:[Reranker] HTTP 500: Internal Server Error
ERROR:root:[Reranker] 熔断器打开，失败次数: 5
INFO:root:[Rerank] ⚡ 轻量级重排模式
INFO:root:[Rerank] ✅ 轻量级重排: 处理300，跳过0
```

### 熔断恢复日志

```
INFO:root:[Reranker] 熔断器进入半开状态
INFO:root:[Reranker] 熔断器恢复
```

## 📞 技术支持

如有问题，请检查：

1. **配置文件** (`config.yaml`) 是否正确
2. **外部服务** 是否正常运行
3. **日志文件** (`logs/service.log`) 查看详细错误
4. **统计接口** (`/api-rqa-search/stats`) 查看服务状态

## 🎉 总结

这个改进版相比原版：

1. ✅ **修复了 JSON 解析错误**（添加完整响应检查）
2. ✅ **修复了超时问题**（恢复正确的超时配置）
3. ✅ **增加了熔断器**（自动降级保护）
4. ✅ **增加了监控**（实时统计）
5. ✅ **增加了配置管理**（统一 YAML 配置）
6. ✅ **保持了原版的业务逻辑**（完全兼容）

**现在可以正常运行了！** 🚀
