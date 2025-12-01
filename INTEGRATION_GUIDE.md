# 半导体专家级多跳QA生成器 - 集成版使用指南

## 📋 概述

本版本是**完整集成版**，融合了两套系统的优势：
1. ✅ **新系统**: 8维度质量评估 + 迭代优化 + 25项最终验证
2. ✅ **原系统**: 4重增强质量检查（有效性检查 + 直接生成测试 + LLM判断 + 替代答案检查）
3. ✅ **核心特性**: 完整支持chunk字段，所有生成和检查都基于原始chunk

---

## 🎯 核心功能特性

### 1. **基于Chunk的约束生成** ⭐⭐⭐

**最高优先级**: 所有生成内容必须严格基于提供的chunk信息！

- ✅ 答案的每一句话都必须能在chunk中找到依据
- ✅ 只能重组和推理chunk中已有的信息
- ✗ 禁止引入chunk外的任何事实、数据、结论
- ✗ 禁止编造、推测、发散

### 2. **双重质量保障体系**

#### **第一层：8维度质量评估（新系统）**

```
1. 问题通用性 (Question Universality)
2. 回答相关性 (Relevance)
3. 逻辑一致性 (Logical Consistency)
4. 术语使用 (Terminology Usage)
5. 事实正确性 (Factual Correctness)
6. 答案通用性 (Answer Universality)
7. 答案准确完整性 (Answer Completeness)
8. 答案可靠性 (Answer Reliability) ⭐ 重点检查chunk约束
```

**特性**:
- 一票否决机制（任一维度low且触发veto → 整体low）
- 自动生成改进建议
- 支持迭代优化（最多2轮）

#### **第二层：4重增强质量检查（原系统）** ⭐ 新增

```
检查1: QA有效性检查
  - 验证问题是否唯一、可解答
  - 验证答案是否基于chunk
  - 验证语法和可读性

检查2: 直接生成测试
  - LLM直接回答问题（带chunk参考）
  - 生成3次，计算一致性得分
  - 阈值: consistency >= 0.5

检查3: LLM判断答案
  - 比较生成答案与标准答案
  - 基于chunk信息判断正确性
  - 结果: Correct / Incorrect / Unknown

检查4: 替代答案检查
  - 验证直接生成的答案是否也正确
  - 基于chunk信息判断
  - 结果: yes / no
```

**通过条件**:
```
overall_passed = (
    有效性检查 == True AND
    一致性 >= 0.5 AND
    (LLM判断 == Correct OR 替代答案 == yes)
)
```

#### **第三层：25项最终验证（新系统）**

```
A. 问题质量（6项）
   - 清晰性、通用性、单一性、多跳性、术语准确性、实际价值

B. 答案质量（8项）
   - 准确性、完整性、简洁性、通用性、术语准确性、逻辑性
   - ⭐ 基于单跳QA、基于chunk（核心检查）

C. 推理质量（6项）
   - 清晰性、正确性、多跳特性、基于单跳QA、基于chunk、因果合理性

D. 技术正确性（5项）
   - 原理正确、数值合理、方法准确、符合共识、无事实错误
```

**评分**: 25/25 → 通过/修改/拒绝

---

## 📊 输出字段说明

### **核心字段**

```json
{
  "id": "multihop_20251201_143025_1234",
  "question": "多跳问题（单一、通用、基于chunk）",
  "answer": "多跳答案（完整、准确、基于chunk）",
  
  // ⭐ 单跳QA（包含chunk）
  "single_hops": [
    {
      "id": 2076,
      "question": "单跳问题1",
      "answer": "单跳答案1",
      "chunk": "原始文献chunk（知识来源）"  // ⭐ 新增
    },
    {
      "id": 5269,
      "question": "单跳问题2",
      "answer": "单跳答案2",
      "chunk": "原始文献chunk（知识来源）"  // ⭐ 新增
    }
  ],
  
  "num_hops": 2,
  "bridge_info": "QA-1的答案中提到的'散射'是QA-2问题的核心概念",
  
  // ⭐ 推理步骤（带chunk引用）
  "reasoning_steps": [
    {
      "step": 1,
      "content": "第一步推理内容",
      "based_on": "单跳QA-1",
      "chunk_reference": "引用的具体chunk内容片段"  // ⭐ 新增
    },
    {
      "step": 2,
      "content": "第二步推理内容",
      "based_on": "单跳QA-2",
      "chunk_reference": "引用的具体chunk内容片段"  // ⭐ 新增
    }
  ],
  
  "key_concepts": ["热致损耗", "界面散射"],
  "bridge_type": "causal",
  
  // ⭐⭐⭐ 质量评估结果
  "quality_evaluation": {
    "dimension_scores": {
      "question_universality": {"score": "high", "issues": [], "veto": false},
      "relevance": {"score": "high", "issues": [], "veto": false},
      // ... 其他6个维度
      "answer_reliability": {"score": "high", "issues": [], "veto": false}
    },
    "overall_quality": "high",
    "veto_triggered": false,
    "chunk_grounding_check": {  // ⭐ chunk验证
      "all_info_from_chunks": true,
      "external_info_detected": false,
      "problematic_statements": []
    }
  },
  
  // ⭐⭐⭐ 4重增强质量检查（新增）
  "enhanced_quality_checks": {
    "validity_check": {
      "passed": true,
      "analysis": "问答对有效，基于chunk"
    },
    "direct_generation": {
      "answers": ["答案1", "答案2", "答案3"],
      "consistency": 0.75,
      "passed": true
    },
    "llm_judgment": {
      "result": "Correct",
      "passed": true
    },
    "alternative_answer": {
      "is_alternative": true,
      "passed": true
    },
    "overall_passed": true  // ⭐ 4重检查总体结果
  },
  
  // ⭐⭐⭐ 25项最终验证
  "final_validation": {
    "validation_results": {
      "passed_items": [1, 2, 3, ..., 25],
      "failed_items": []
    },
    "overall_pass": true,
    "final_score": 25,
    "recommendation": "approve"
  },
  
  // 优化历史
  "refinement_history": [
    {
      "round": 1,
      "changes": ["改进了术语使用", "增强了逻辑连贯性"]
    }
  ],
  
  // 质量标签
  "overall_quality": "high",
  "final_score": 25,
  "passed_final_validation": true,
  "passed_enhanced_checks": true,  // ⭐ 新增
  
  "generated_at": "2025-12-01T14:30:25"
}
```

---

## 🚀 使用方法

### **1. 数据准备**

**输入数据格式** (JSONL):

```json
{
  "id": 2076,
  "question": "在低温（10mK）条件下，SAW谐振器的品质因子（Q值）为何提升...",
  "answer": "<think>...",
  "chunk": "原始文献内容...",  // ⭐ 必须字段
  "paper_name": "paper_001.pdf"
}
```

⚠️ **重要**: 每条单跳QA **必须** 包含 `chunk` 字段！

如果缺少chunk，程序会自动添加空字符串，但会影响生成质量。

### **2. 运行命令**

**基础用法**:

```bash
python expert_qa_integrated.py \
  --input_file single_hop_qa.jsonl \
  --output_file multihop_qa.jsonl \
  --llm_url http://localhost:8000/v1/completions \
  --model Qwen2.5-72B-Instruct \
  --num_samples 50
```

**高质量模式** (严格过滤):

```bash
python expert_qa_integrated.py \
  --input_file single_hop_qa.jsonl \
  --output_file multihop_qa_high.jsonl \
  --llm_url http://localhost:8000/v1/completions \
  --model Qwen2.5-72B-Instruct \
  --num_samples 100 \
  --quality_filter high \
  --max_refine_rounds 3 \
  --min_hops 2 \
  --max_hops 4
```

**参数说明**:

| 参数 | 说明 | 默认值 |
|-----|------|--------|
| `--input_file` | 单跳QA数据文件（必须包含chunk） | 必填 |
| `--output_file` | 输出文件路径 | 必填 |
| `--llm_url` | LLM API地址 | 必填 |
| `--model` | 模型名称 | 必填 |
| `--num_samples` | 生成数量 | 10 |
| `--min_hops` | 最小跳数 | 2 |
| `--max_hops` | 最大跳数 | 3 |
| `--max_refine_rounds` | 最大优化轮数 | 2 |
| `--quality_filter` | 质量过滤 (`high`/`medium+`/`all`) | `medium+` |
| `--output_format` | 输出格式 (`jsonl`/`json`/`both`) | `jsonl` |

**质量过滤说明**:

- `high`: 只保留 overall_quality=high **且** 通过25项验证 **且** 通过4重检查
- `medium+`: 保留 overall_quality≥medium **且** 通过25项验证
- `all`: 保留所有生成的QA

### **3. 输出文件**

运行后会生成3个文件：

```
multihop_qa.jsonl          # 主输出（JSONL格式）
multihop_qa.json           # JSON格式（如果指定）
multihop_qa_report.json    # 质量报告
```

**质量报告示例**:

```json
{
  "total": 50,
  "quality_distribution": {
    "high": 35,
    "medium": 12,
    "low": 3
  },
  "final_validation": {
    "passed": 45,
    "rate": 0.9
  },
  "enhanced_checks": {
    "passed": 42,
    "rate": 0.84
  },
  "average_score": 23.5,
  "bridge_type_distribution": {
    "causal": 25,
    "compositional": 15,
    "inferential": 10
  }
}
```

---

## 🔄 完整生成流程

```
┌─────────────────────────────────────────────────────────────┐
│  Step 1: 智能选择单跳QA（包含chunk）                        │
│  - 基于桥接实体优先跨论文链接                                │
│  - 自动推断桥接类型（causal/compositional/inferential）     │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  Step 2: 生成多跳QA（基于chunk）                            │
│  - Prompt中包含完整chunk信息                                │
│  - 强制约束：答案必须基于chunk                               │
│  - 生成带chunk引用的推理步骤                                │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  Step 3: 8维度质量评估 + 迭代优化                           │
│  - 评估8个维度（含chunk约束检查）                           │
│  - 如果quality < high，自动优化                             │
│  - 最多优化2轮                                              │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  Step 4: 4重增强质量检查 ⭐ 新增                            │
│  ├─ 检查1: QA有效性（基于chunk）                            │
│  ├─ 检查2: 直接生成测试（3次，带chunk参考）                │
│  ├─ 检查3: LLM判断答案（基于chunk）                         │
│  └─ 检查4: 替代答案检查（基于chunk）                        │
│  → 输出: overall_passed (True/False)                        │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  Step 5: 25项最终验证                                       │
│  - 全面检查问题、答案、推理、技术正确性                      │
│  - 重点验证chunk约束（第14、19项）                          │
│  → 输出: final_score (0-25) + recommendation               │
└─────────────────────────────────────────────────────────────┘
                           ↓
                    ┌────────────┐
                    │ 保存结果    │
                    └────────────┘
```

---

## ⚠️ 关键注意事项

### **1. Chunk字段的重要性**

- **最高优先级**: 所有生成和检查都依赖chunk字段
- 如果单跳QA缺少chunk，会导致：
  - 答案可能脱离原始信息
  - 4重检查可能失败
  - 最终验证得分降低

**解决方案**: 确保输入数据包含完整的chunk字段

### **2. 质量保障机制**

本系统采用**三重质量保障**:

1. **生成阶段**: Prompt中强制chunk约束
2. **评估阶段**: 8维度质量评估（含chunk检查）
3. **验证阶段**: 4重增强检查 + 25项最终验证

**通过标准**:

- `quality_filter='high'`: 需同时通过所有检查
- `quality_filter='medium+'`: 需通过8维度评估和25项验证
- `quality_filter='all'`: 保留所有结果（用于分析）

### **3. 性能优化建议**

- **并发生成**: 使用异步IO，单个样本生成约60-120秒
- **批量大小**: 建议每批50-100个样本
- **质量过滤**: 使用`high`模式可能导致通过率<50%，需生成更多样本

---

## 📈 质量指标

### **预期指标**

| 指标 | 目标值 | 说明 |
|-----|--------|------|
| 8维度评估通过率 | ≥70% | overall_quality ≥ medium |
| 25项验证通过率 | ≥80% | final_score ≥ 20 |
| 4重检查通过率 | ≥60% | overall_passed = True |
| 综合通过率（high模式） | ≥40% | 同时通过所有检查 |

### **关键质量点**

1. **Chunk约束** (第8维度、第14/19验证项)
   - 答案不得脱离chunk信息
   - 禁止引入外部知识

2. **通用性** (第1/6维度、第2验证项)
   - 不特指论文
   - 不使用自指表述

3. **完整性** (第7维度、第8验证项)
   - 准确回答问题
   - 完整覆盖所有方面

---

## 🔧 故障排除

### **问题1: JSON解析失败**

**现象**: `[WARNING] JSON解析失败`

**原因**: LLM输出格式不规范

**解决**:
- 检查LLM配置（temperature建议0.3-0.7）
- 使用更强大的模型（如Qwen2.5-72B）
- 查看原始输出，手动修正Prompt

### **问题2: 4重检查通过率低**

**现象**: `passed_enhanced_checks=False` 比例高

**原因**: 
- 答案脱离chunk
- 直接生成一致性低
- LLM判断标准严格

**解决**:
- 确保chunk字段完整且质量高
- 增加`max_refine_rounds`（如3轮）
- 使用更强大的LLM模型

### **问题3: 25项验证得分低**

**现象**: `final_score < 20`

**原因**: 
- 问题通用性不足
- 答案不完整
- 推理不清晰

**解决**:
- 增加优化轮数
- 检查单跳QA质量
- 调整质量过滤阈值

---

## 📚 示例输出

完整示例见输出文件中的JSON结构。

**关键字段说明**:

```json
{
  "single_hops": [/* 包含chunk的单跳QA */],
  "reasoning_steps": [/* 包含chunk引用的推理步骤 */],
  
  "quality_evaluation": {
    "chunk_grounding_check": {/* chunk约束验证 */}
  },
  
  "enhanced_quality_checks": {/* 4重检查结果 */},
  "final_validation": {/* 25项验证结果 */},
  
  "passed_enhanced_checks": true,  // ⭐ 核心指标1
  "passed_final_validation": true, // ⭐ 核心指标2
  "overall_quality": "high"        // ⭐ 核心指标3
}
```

---

## 🎓 最佳实践

1. **数据准备**
   - 确保单跳QA包含完整chunk
   - Chunk长度建议500-2000字符
   - 清理无关的格式标记

2. **参数调优**
   - 初始运行使用`quality_filter='all'`，分析质量分布
   - 根据需求调整过滤级别
   - `max_refine_rounds=2`通常足够，3轮可能过度优化

3. **批量生成**
   - 分批生成，每批50-100个
   - 定期检查中间结果
   - 使用质量报告分析问题

4. **结果筛选**
   - 优先使用`passed_enhanced_checks=True`的样本
   - 关注`chunk_grounding_check`结果
   - 验证`final_score ≥ 23`的高质量样本

---

## 📞 技术支持

如遇到问题，请提供：
1. 运行命令和参数
2. 输入数据样例（包含chunk字段）
3. 错误信息或异常输出
4. 质量报告文件

---

## 版本信息

- **版本**: v1.0-integrated
- **日期**: 2025-12-01
- **特性**: 
  - ✅ 8维度质量评估 + 迭代优化
  - ✅ 4重增强质量检查（新增）
  - ✅ 25项最终验证
  - ✅ 完整chunk支持
  - ✅ 智能桥接链接
