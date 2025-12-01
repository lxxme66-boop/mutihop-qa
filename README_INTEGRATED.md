# 半导体专家级多跳QA生成器 - 集成版

> **完整版本**: 融合8维度评估 + 4重增强检查 + 25项最终验证 + 完整chunk支持

---

## 🎯 核心特性

### ✅ 已完成的功能集成

1. **8维度质量评估体系**（新系统）
   - 问题通用性、回答相关性、逻辑一致性、术语使用
   - 事实正确性、答案通用性、答案准确完整性、答案可靠性
   - 一票否决机制
   - 自动迭代优化（最多2轮）

2. **4重增强质量检查**（原系统）⭐ 新增
   - ✅ 检查1: QA有效性检查（基于chunk）
   - ✅ 检查2: 直接生成测试（3次采样 + 一致性评估）
   - ✅ 检查3: LLM判断答案（与标准答案对比）
   - ✅ 检查4: 替代答案检查（验证多样性）

3. **25项最终验证**（新系统）
   - 问题质量（6项）
   - 答案质量（8项）
   - 推理质量（6项）
   - 技术正确性（5项）
   - 最终得分 0-25分

4. **完整chunk支持** ⭐⭐⭐
   - 所有单跳QA包含原始文献chunk
   - 生成prompt强制chunk约束
   - 所有检查验证chunk遵守性
   - 推理步骤标注chunk引用

5. **智能桥接链接**
   - 基于答案实体 → 问题实体的智能链接
   - 优先跨论文链接
   - 自动推断桥接类型（causal/compositional/inferential）

---

## 📊 输出字段对比

### **新增字段**（相比原版本）

```json
{
  // ⭐ 单跳QA增加chunk字段
  "single_hops": [
    {
      "id": 2076,
      "question": "...",
      "answer": "...",
      "chunk": "原始文献内容（新增）"  // ⭐⭐⭐
    }
  ],
  
  // ⭐ 推理步骤增加chunk引用
  "reasoning_steps": [
    {
      "step": 1,
      "content": "...",
      "based_on": "单跳QA-1",
      "chunk_reference": "具体引用片段（新增）"  // ⭐
    }
  ],
  
  // ⭐⭐⭐ 4重增强质量检查（完全新增）
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
    "overall_passed": true  // ⭐ 核心指标
  },
  
  // ⭐ chunk约束检查（质量评估中新增）
  "quality_evaluation": {
    "chunk_grounding_check": {
      "all_info_from_chunks": true,
      "external_info_detected": false,
      "problematic_statements": []
    }
  },
  
  // ⭐ 新增标识
  "bridge_type": "causal",  // 桥接类型
  "passed_enhanced_checks": true  // 4重检查通过标识
}
```

---

## 🚀 快速开始

### **1. 准备数据**

**输入格式** (必须包含chunk字段):

```json
{
  "id": 2076,
  "question": "单跳问题",
  "answer": "单跳答案",
  "chunk": "原始文献内容（必须字段）",  // ⭐⭐⭐
  "paper_name": "paper_001.pdf"
}
```

示例数据: `example_input.jsonl`

### **2. 运行测试**

```bash
# 给测试脚本添加执行权限
chmod +x test_integrated.sh

# 运行测试（会提示输入LLM配置）
./test_integrated.sh
```

### **3. 正式生成**

```bash
python expert_qa_integrated.py \
  --input_file single_hop_qa.jsonl \
  --output_file multihop_qa.jsonl \
  --llm_url http://localhost:8000/v1/completions \
  --model Qwen2.5-72B-Instruct \
  --num_samples 50 \
  --quality_filter medium+ \
  --output_format both
```

---

## 📈 质量保障流程

```
输入: 单跳QA（包含chunk）
    ↓
┌─────────────────────────────────┐
│ Step 1: 智能选择单跳QA           │
│ - 优先跨论文桥接                 │
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│ Step 2: 生成多跳QA（基于chunk）  │
│ - 强制chunk约束                 │
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│ Step 3: 8维度评估 + 迭代优化     │
│ - 含chunk约束检查               │
│ - 最多2轮优化                   │
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│ Step 4: 4重增强质量检查 ⭐ 新增  │
│ - 有效性检查                    │
│ - 直接生成测试（3次）            │
│ - LLM判断                       │
│ - 替代答案检查                  │
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│ Step 5: 25项最终验证             │
│ - 全面质量检查                  │
│ - 得分 0-25                     │
└─────────────────────────────────┘
    ↓
输出: 高质量多跳QA
```

---

## 📝 主要参数说明

| 参数 | 说明 | 默认值 | 推荐值 |
|-----|------|--------|--------|
| `--quality_filter` | 质量过滤级别 | `medium+` | `high`（严格）/ `medium+`（平衡）|
| `--num_samples` | 生成数量 | 10 | 50-100 |
| `--max_refine_rounds` | 最大优化轮数 | 2 | 2-3 |
| `--min_hops` / `--max_hops` | 跳数范围 | 2-3 | 2-4 |
| `--output_format` | 输出格式 | `jsonl` | `both`（同时输出jsonl和json）|

### **质量过滤级别**

- `high`: **同时满足**
  - overall_quality = high
  - passed_final_validation = True
  - passed_enhanced_checks = True  ⭐
  
- `medium+`: **同时满足**
  - overall_quality ∈ {high, medium}
  - passed_final_validation = True
  
- `all`: 保留所有生成结果

---

## 📊 预期质量指标

| 指标 | 目标值 | 说明 |
|-----|--------|------|
| **8维度评估通过率** | ≥70% | overall_quality ≥ medium |
| **25项验证通过率** | ≥80% | final_score ≥ 20 |
| **4重检查通过率** ⭐ | ≥60% | overall_passed = True |
| **综合通过率（high模式）** | ≥40% | 同时通过所有检查 |
| **平均得分** | ≥22/25 | 质量优秀 |

---

## 📂 文件结构

```
/workspace/
├── expert_qa_integrated.py      # 主程序（集成版）⭐⭐⭐
├── INTEGRATION_GUIDE.md         # 详细使用指南
├── README_INTEGRATED.md         # 本文件
├── example_input.jsonl          # 示例输入数据
├── test_integrated.sh           # 快速测试脚本
│
├── agent_final_new.py           # 原系统Agent
├── knowledge_base_new.py        # 原系统KB
├── llm_client.py                # 原系统LLM客户端
├── main_final.py                # 原系统主程序
├── prompts_final.py             # 原系统Prompt模板
└── utils.py                     # 原系统工具函数
```

---

## 🔧 核心代码修改

### **1. Prompt模板增强**

所有prompt添加chunk支持：

```python
# 生成prompt
compose_multihop_qa = '''
...
## 单跳问答对（包含原始chunk）
{single_hops}

## 【核心要求】
### 1. 基于chunk的约束（最高优先级）⭐⭐⭐
- ✅ 答案的每一句话都必须能在chunk中找到依据
- ✗ 禁止引入chunk外的任何事实、数据、结论
...
'''

# 评估prompt
evaluate_8dimensions = '''
...
**单跳问答依据（包含chunk）：**
{single_hop_qas}

### 8. 答案可靠性 (Answer Reliability) ⭐⭐⭐
- [ ] ⚠️ 答案是否脱离了chunk？（禁止）
- [ ] ⚠️ 答案是否引入了chunk外的信息？（禁止）
...
'''

# 4重检查prompt（新增）
qa_valid_check = '''
⚠️ **核心检查原则**：
1. 问题和答案必须基于给定的子问答对和chunk
2. 不得引入chunk中没有的事实、数据、结论
...
'''
```

### **2. 知识库增强**

```python
class SemiconductorKB:
    def __init__(self, qa_data: List[Dict], llm: LLMClient):
        # 验证chunk字段 ⭐
        for qa in qa_data:
            if 'chunk' not in qa:
                print(f"[WARNING] QA-{qa.get('id')} 缺少chunk字段")
                qa['chunk'] = ""
    
    def get_qa_with_chunk(self, qa_id: str) -> Dict:
        """获取QA（包含chunk）"""
        qa = self.qa_data.get(qa_id)
        if qa and 'chunk' not in qa:
            qa['chunk'] = ""
        return qa
    
    def format_single_hops_for_prompt(self, qa_ids: List[str], 
                                     include_chunk: bool = True) -> str:
        """格式化单跳QA用于prompt（包含chunk）"""
        for i, qa_id in enumerate(qa_ids):
            qa = self.get_qa_with_chunk(qa_id)
            qa_str += f"问题: {qa['question']}\n"
            qa_str += f"答案: {qa['answer']}\n"
            
            if include_chunk and qa.get('chunk'):
                chunk_text = qa['chunk'][:1000]  # 截断长chunk
                qa_str += f"原始chunk（知识来源）:\n{chunk_text}\n"
        ...
    
    def get_chunks_text(self, qa_ids: List[str]) -> str:
        """获取所有chunk的合并文本（用于4重检查）"""
        chunks = []
        for qa_id in qa_ids:
            qa = self.get_qa_with_chunk(qa_id)
            chunk = qa.get('chunk', '')
            if chunk:
                chunks.append(f"[Chunk from QA-{qa_id}]\n{chunk}")
        return "\n\n".join(chunks)
```

### **3. Agent增强（4重检查）**

```python
class ExpertQAAgent:
    async def check_qa_valid(self, question, answer, single_hop_ids):
        """检查1: QA有效性（基于chunk）"""
        single_hops_text = self.kb.format_single_hops_for_prompt(
            single_hop_ids, include_chunk=True
        )
        prompt = self.prompts.qa_valid_check.format(...)
        ...
    
    async def direct_generate(self, question, single_hop_ids, n_samples=3):
        """检查2: 直接生成测试（带chunk参考）"""
        chunks_text = self.kb.get_chunks_text(single_hop_ids)
        prompt = self.prompts.direct_gen_check.format(
            question=question, chunks=chunks_text
        )
        # 并发生成3次
        tasks = [self.llm.generate(prompt, temperature=0.8) 
                for _ in range(n_samples)]
        responses = await asyncio.gather(*tasks)
        # 计算一致性
        ...
    
    async def llm_judge_answer(self, question, gt_answer, pred_answer, single_hop_ids):
        """检查3: LLM判断答案（基于chunk）"""
        chunks_text = self.kb.get_chunks_text(single_hop_ids)
        prompt = self.prompts.llm_judge.format(...)
        ...
    
    async def check_alternative_answer(self, question, gt_answer, pred_answer, single_hop_ids):
        """检查4: 替代答案检查（基于chunk）"""
        chunks_text = self.kb.get_chunks_text(single_hop_ids)
        prompt = self.prompts.check_alternative_ans.format(...)
        ...
    
    async def run_4fold_checks(self, qa_data, single_hop_ids):
        """执行4重增强质量检查"""
        is_valid, valid_analysis = await self.check_qa_valid(...)
        direct_answers, consistency = await self.direct_generate(...)
        judge_result = await self.llm_judge_answer(...)
        is_alternative = await self.check_alternative_answer(...)
        
        return {
            'validity_check': {'passed': is_valid, ...},
            'direct_generation': {'consistency': consistency, ...},
            'llm_judgment': {'result': judge_result, ...},
            'alternative_answer': {'is_alternative': is_alternative, ...},
            'overall_passed': (is_valid and consistency>=0.5 and ...)
        }
    
    async def generate_one(self, num_hops=2):
        """生成一个多跳QA（完整流程）"""
        # Step 1: 选择单跳QA
        single_hop_ids, bridge_info, bridge_type = self.kb.select_single_hops_smart(num_hops)
        
        # Step 2: 生成多跳QA
        qa_data = await self.generate_multihop_qa(...)
        
        # Step 3: 8维度评估 + 迭代优化
        for round_idx in range(self.max_refine_rounds + 1):
            evaluation = await self.evaluate_quality(qa_data, single_hop_ids)
            if evaluation['overall_quality'] == 'high':
                break
            qa_data = await self.refine_qa(qa_data, evaluation, single_hop_ids)
        
        # Step 4: 4重增强质量检查 ⭐ 新增
        enhanced_checks = await self.run_4fold_checks(qa_data, single_hop_ids)
        qa_data['enhanced_quality_checks'] = enhanced_checks
        
        # Step 5: 25项最终验证
        final_validation = await self.final_validate(qa_data, single_hop_ids)
        qa_data['final_validation'] = final_validation
        
        # 构建最终输出（包含chunk）
        single_hops = []
        for qa_id in single_hop_ids:
            qa = self.kb.get_qa_with_chunk(qa_id)
            single_hops.append({
                'id': qa_id,
                'question': qa['question'],
                'answer': qa['answer'],
                'chunk': qa.get('chunk', '')  # ⭐ 包含chunk
            })
        
        result = {
            'single_hops': single_hops,
            'enhanced_quality_checks': enhanced_checks,  # ⭐ 新增
            'passed_enhanced_checks': enhanced_checks['overall_passed'],  # ⭐ 新增
            ...
        }
        return result
```

---

## 🎓 最佳实践

### **1. 数据准备**

✅ **推荐做法**:
- 确保每个单跳QA都有chunk字段
- Chunk长度500-2000字符为佳
- Chunk内容与问答高度相关

❌ **避免做法**:
- Chunk为空或无关内容
- Chunk过长（>5000字符）
- Chunk缺少关键技术信息

### **2. 参数调优**

**初始测试**:
```bash
--num_samples 10 \
--quality_filter all \
--output_format both
```
→ 分析质量分布，确定合适的过滤级别

**正式生成**:
```bash
--num_samples 100 \
--quality_filter medium+ \
--max_refine_rounds 2
```
→ 平衡质量和效率

**高质量模式**:
```bash
--num_samples 200 \
--quality_filter high \
--max_refine_rounds 3
```
→ 严格筛选，通过率约40%

### **3. 结果筛选**

**推荐筛选标准**:

1. **顶级质量** (用于发表/产品):
   ```python
   passed_enhanced_checks == True AND
   final_score >= 24 AND
   overall_quality == 'high'
   ```

2. **优质样本** (用于训练数据):
   ```python
   passed_final_validation == True AND
   final_score >= 22 AND
   chunk_grounding_check.all_info_from_chunks == True
   ```

3. **可用样本** (用于分析/研究):
   ```python
   passed_final_validation == True AND
   overall_quality in ['high', 'medium']
   ```

---

## 🔍 故障排除

### **问题1: chunk字段缺失警告**

```
[WARNING] QA-2076 缺少chunk字段，将添加空chunk
```

**解决**:
- 检查输入数据格式
- 确保每行JSON包含`"chunk": "..."`
- 使用`example_input.jsonl`作为参考

### **问题2: 4重检查通过率低**

```
passed_enhanced_checks: False (比例高)
```

**可能原因**:
1. 答案脱离chunk
2. 直接生成一致性低
3. LLM判断标准严格

**解决**:
- 提高chunk质量
- 增加`max_refine_rounds`
- 使用更强大的LLM模型
- 调整一致性阈值（代码中修改）

### **问题3: LLM API错误**

```
RuntimeError: LLM API错误 500
```

**解决**:
- 检查LLM服务状态
- 验证API地址和端口
- 检查模型名称是否正确
- 查看LLM服务日志

---

## 📞 技术支持

### **获取帮助**

1. 查看详细文档: `INTEGRATION_GUIDE.md`
2. 运行测试脚本: `./test_integrated.sh`
3. 查看示例数据: `example_input.jsonl`

### **报告问题**

请提供:
- 运行命令和参数
- 输入数据样例（含chunk）
- 错误信息/日志
- 质量报告文件

---

## 📜 变更日志

### v1.0-integrated (2025-12-01)

**新增功能**:
- ✅ 4重增强质量检查（有效性+直接生成+LLM判断+替代答案）
- ✅ 完整chunk支持（数据结构+prompt+检查）
- ✅ chunk约束验证（所有阶段）
- ✅ 推理步骤chunk引用
- ✅ 智能桥接链接优化

**修改功能**:
- 📝 所有prompt模板添加chunk约束
- 📝 8维度评估增加chunk检查维度
- 📝 25项验证增加chunk相关项
- 📝 知识库增加chunk管理方法

**输出字段变更**:
- 新增: `single_hops[].chunk`
- 新增: `reasoning_steps[].chunk_reference`
- 新增: `enhanced_quality_checks`（完整对象）
- 新增: `quality_evaluation.chunk_grounding_check`
- 新增: `passed_enhanced_checks`

---

## 📄 License

本项目遵循原项目的许可证。

---

## 🙏 致谢

感谢原系统和新系统的开发者，本集成版融合了两套系统的优势，提供了更全面、更严格的质量保障机制。

---

**最后更新**: 2025-12-01  
**版本**: v1.0-integrated  
**作者**: Claude-4.5-Sonnet (Integration)
