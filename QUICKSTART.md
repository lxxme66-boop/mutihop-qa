# RAG 搜索服务 - 快速参考卡片

## 📁 文件清单

| 文件 | 说明 | 必需 |
|------|------|------|
| `config.yaml` | 配置文件 | ✅ 必需 |
| `config_loader.py` | 配置加载模块 | ✅ 必需 |
| `search_service_improved.py` | 主服务代码 | ✅ 必需 |
| `start.sh` | 启动脚本 | ⚠️  推荐 |
| `README_IMPROVED.md` | 完整文档 | ℹ️  参考 |
| `CHANGES.md` | 改进对比 | ℹ️  参考 |

## 🚀 30秒快速启动

```bash
# 1. 安装依赖
pip install pyyaml pymongo requests flask

# 2. 编辑配置（修改为你的服务地址）
vim config.yaml

# 3. 启动服务
bash start.sh
```

## ⚙️ 核心配置

### 必改项 ⚠️

```yaml
# config.yaml

services:
  encoder:
    url: "http://8.130.183.20:8031/encode"  # ⚠️  改为你的地址
  milvus:
    url: "http://8.130.183.20:8033/api-vec-search/search"  # ⚠️  改为你的地址
  reranker:
    url: "http://8.130.183.20:8032/query_bge_reranker/"  # ⚠️  改为你的地址
  mongodb:
    url: "mongodb://root:example@10.70.223.31:27017"  # ⚠️  改为你的地址
    database: "rqa"  # ⚠️  改为你的数据库
    collection: "paper_shards_detail_table_20230908"  # ⚠️  改为你的集合
```

### 推荐调整项 ℹ️

**低配服务器**（4核8G）:
```yaml
connection_pools:
  encoder:
    max_connections: 24  # 默认 48
  milvus:
    max_connections: 32  # 默认 64
  reranker:
    max_connections: 100  # 默认 200

concurrency_control:
  max_concurrency: 32  # 默认 64
```

**高配服务器**（16核32G）:
```yaml
connection_pools:
  encoder:
    max_connections: 96  # 默认 48
  milvus:
    max_connections: 128  # 默认 64
  reranker:
    max_connections: 400  # 默认 200

concurrency_control:
  max_concurrency: 128  # 默认 64
```

## 🧪 测试命令

```bash
# 健康检查
curl http://localhost:9510/api-rqa-search/test

# 查看统计
curl http://localhost:9510/api-rqa-search/stats | python -m json.tool

# 搜索测试
curl -X POST http://localhost:9510/api-rqa-search/search \
  -d "query=什么是IGZO&id=1&top_doc_num=5"
```

## 🔧 常见问题

### Q1: 启动失败，提示 "缺少 PyYAML"

```bash
pip install pyyaml
```

### Q2: 连接超时错误

**检查**：外部服务是否可访问
```bash
curl http://8.130.183.20:8031/encode -v
```

**解决**：增加超时时间
```yaml
services:
  encoder:
    connect_timeout: 300  # 增加到 300 秒
    read_timeout: 600
```

### Q3: JSON 解析错误

**原因**：外部服务返回异常

**检查日志**：
```bash
tail -f logs/service.log | grep ERROR
```

**自动保护**：熔断器会自动降级

### Q4: 内存占用过高

**检查缓存大小**：
```yaml
cache:
  encoder:
    max_size: 1000  # 减小缓存（默认 2000）
```

**减少连接池**：
```yaml
connection_pools:
  reranker:
    max_connections: 100  # 减少连接数（默认 200）
```

## 📊 监控看板

访问 `http://localhost:9510/api-rqa-search/stats`

### 关键指标

| 指标 | 正常值 | 异常值 | 说明 |
|------|--------|--------|------|
| `usage_rate` | < 70% | > 90% | 连接池使用率 |
| `circuit_breaker.state` | `closed` | `open` | 熔断器状态 |
| `cache.hit_rate` | > 30% | < 10% | 缓存命中率 |
| `active_connections` | < max | = max | 活跃连接数 |

### 熔断器状态

- ✅ `closed`: 正常
- ⚠️  `half_open`: 恢复中
- ❌ `open`: 熔断中（自动降级）

## 🛠️ 调优建议

### 1. 优化缓存命中率

```yaml
cache:
  encoder:
    max_size: 5000  # 增加缓存
    ttl: 7200  # 延长过期时间
```

### 2. 提升并发能力

```yaml
concurrency_control:
  max_concurrency: 128  # 增加最大并发
  
connection_pools:
  encoder:
    max_connections: 96  # 增加连接池
```

### 3. 加速 MongoDB 查询

```yaml
mongodb_query:
  parallel_workers: 8  # 增加并行线程（默认 4）
  batch_timeout: 200  # 增加超时（默认 150）
```

## 🔄 更新配置

配置每 3 分钟自动重新加载，或手动重启：

```bash
# 查找进程
ps aux | grep search_service_improved

# 杀死进程
kill <PID>

# 重新启动
bash start.sh
```

## 📞 排查流程

```
服务异常
   ↓
1. 查看日志: tail -f logs/service.log
   ↓
2. 检查统计: curl .../stats
   ↓
3. 测试外部服务:
   - curl 编码服务
   - curl Milvus
   - curl Reranker
   - mongo 连接测试
   ↓
4. 调整配置（增加超时/减少并发）
   ↓
5. 重启服务
```

## 📚 完整文档

- **完整说明**: `README_IMPROVED.md`
- **改进对比**: `CHANGES.md`
- **配置文件**: `config.yaml`（有详细注释）

## ✅ 检查清单

部署前检查：

- [ ] 已安装所有依赖
- [ ] 已修改 `config.yaml` 中的服务地址
- [ ] 外部服务可访问（编码、Milvus、Reranker、MongoDB）
- [ ] 模型文件存在（用户词典、查询分类模型等）
- [ ] 端口 9510 未被占用
- [ ] 有足够的内存（建议 > 8GB）

## 🎉 成功标志

服务正常运行时，你会看到：

```
================================================================================
服务就绪
================================================================================
连接池:
  Encoder: {'service': 'Encoder', 'max_connections': 48, 'active': 0, ...}
  Milvus: {'service': 'Milvus', 'max_connections': 64, 'active': 0, ...}
  Reranker: {'service': 'Reranker', 'max_connections': 200, 'active': 0, ...}
熔断器:
  全部就绪
并发控制:
  初始并发: 32
  最小-最大: 8-64
================================================================================

INFO:root:✅ 服务启动: http://0.0.0.0:9510
 * Running on http://0.0.0.0:9510/ (Press CTRL+C to quit)
```

**现在可以使用了！** 🚀
