#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
半导体专家级多跳QA生成器 - 集成4重质量检查版
功能特性：
1. ✅ 8维度质量评估 + 迭代优化
2. ✅ 25项最终验证
3. ✅ 4重增强质量检查（来自原系统）
4. ✅ 完整支持chunk字段
5. ✅ 所有prompt都基于chunk生成
"""

import json
import asyncio
import aiohttp
import random
import re
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
from datetime import datetime
import argparse


# ========================================================================
# 第1部分：Prompt模板（集成chunk支持）
# ========================================================================

class ExpertQAPrompts:
    """半导体QA生成的Prompt模板（集成chunk）"""
    
    # ===== 多跳QA生成（强化chunk约束）=====
    compose_multihop_qa = '''你是半导体领域的资深专家。基于以下单跳问答对，生成一个高质量的多跳问答。

**重要约束：所有生成内容必须严格基于提供的chunk信息！**

# 输入信息

## 单跳问答对（包含原始chunk）

{single_hops}

---

## 桥接信息
{bridge_info}

## 目标
生成一个 **{num_hops}跳** 的多跳问答对

---

## 【核心要求】（严格执行）

### 1. 基于chunk的约束（最高优先级）⭐⭐⭐
- ✅ **答案的每一句话都必须能在chunk中找到依据**
- ✅ **只能重组和推理chunk中已有的信息**
- ✗ **禁止引入chunk外的任何事实、数据、结论**
- ✗ **禁止编造、推测、发散**

### 2. 问题设计准则：

**(1) 因果链完整性**
- 问题需呈现完整技术逻辑链：机制A → 参数B → 现象C
- 体现{num_hops}步推理的必要性
- 所有技术点必须在chunk中有明确提及

**(2) 通用性（严格执行）**
- ✓ 问题必须具有通用性，不局限于特定论文
- ✗ 禁止使用"本文"、"本研究"、"本实验"等自指表述
- ✗ 禁止引用文献或文章自定义的专有名词
- ✓ 确保不读论文也能理解问题含义

**(3) 单一性（严格执行）**
- ✓ 问题只包含一个核心疑问点
- ✗ 禁止连接多个子问题

### 3. 答案生成准则（基于chunk）：

**(1) 严格基于chunk（最高优先级）⭐⭐⭐**
- ✅ 答案的每一句话都必须有chunk支撑
- ✅ 每提到一个数据、结论、机制，必须能在chunk中找到原文
- ✅ 推理过程只能基于chunk中的信息进行逻辑组合
- ✗ 禁止使用chunk外的专业知识
- ✗ 禁止发散到相关但未提及的技术点

**(2) 完整性（严格执行）**
- ✓ 必须完整回答问题的所有方面
- ✓ 必须体现{num_hops}步推理过程
- ✗ 禁止仅引导句

**(3) 质量自检（生成后必须检查）**
生成答案后，逐句自问：
- [ ] 这句话在哪个chunk中有依据？
- [ ] 这个数据在chunk中出现过吗？
- [ ] 这个结论是从chunk推导的，还是我自己加的？

---

输出JSON格式：
```json
{{
    "multihop_question": "多跳问题（单一、通用、{num_hops}步推理链）",
    "multihop_answer": "多跳答案（完整、准确、基于chunk推导）",
    "reasoning_steps": [
        {{
            "step": 1, 
            "content": "第一步推理内容（至少15字）", 
            "based_on": "单跳QA-1",
            "chunk_reference": "引用的具体chunk内容片段（20-50字）"
        }},
        {{
            "step": 2, 
            "content": "第二步推理内容（至少15字）", 
            "based_on": "单跳QA-2",
            "chunk_reference": "引用的具体chunk内容片段（20-50字）"
        }}
    ],
    "key_concepts": ["核心概念1", "核心概念2"],
    "bridge_type": "{bridge_type}",
    "quality_check": {{
        "is_single_question": true,
        "is_universal": true,
        "no_paper_reference": true,
        "answer_complete": true,
        "answer_based_on_chunks": true,
        "all_info_from_chunks": true
    }}
}}
```
'''

    # ===== 8维度质量评估（添加chunk验证）=====
    evaluate_8dimensions = '''你是半导体领域的QA质量评估专家。基于8个核心维度评估以下多跳问答的质量。

# 待评估的问答

**问题：**
{question}

**答案：**
{answer}

**推理步骤：**
{reasoning_steps}

**单跳问答依据（包含chunk）：**
{single_hop_qas}

---

## 8维度评估标准（一票否决机制）

### 1. 问题通用性 (Question Universality)
- [ ] 问题是否依据子问题答案生成？
- [ ] 问题是否具有实际意义和通用性？
- [ ] 问题中是否引用文献或文章自定义的专有名词？（禁止）
- [ ] 是否是多跳问题？（必须是）

### 2. 回答相关性 (Relevance)
- [ ] 回答是否精准聚焦问题核心？
- [ ] 是否存在答非所问？
- [ ] 答案是否只是仅引导句未提供实质性内容？（禁止）

### 3. 逻辑一致性 (Logical Consistency)
- [ ] 回答的推理过程是否清晰、连贯、无矛盾？
- [ ] 是否存在逻辑跳跃、断裂或自相矛盾？

### 4. 术语使用 (Terminology Usage)
- [ ] 专业术语的使用是否准确、恰当、完整？
- [ ] 是否存在术语误用、滥用、缺失？

### 5. 事实正确性 (Factual Correctness)
- [ ] 技术细节、参数、原理是否符合行业共识？
- [ ] 是否存在事实性错误或过时信息？

### 6. 答案通用性 (Answer Universality)
- [ ] 答案是否特指论文？（禁止）
- [ ] 答案中是否引用文献或文章自定义的专有名词？（禁止）
- [ ] 答案是否使用"本文"、"本研究"等自指表述？（禁止）

### 7. 答案准确完整性 (Answer Completeness)
- [ ] 答案是否准确回答了问题？（严格执行）
- [ ] 答案是否完整回答了问题（回答了各个子问题）？（严格执行）
- [ ] 答案是否简洁凝练，无冗余？

### 8. 答案可靠性 (Answer Reliability) ⭐⭐⭐ 重点检查
- [ ] 答案是否依据子问题的答案回答的？（严格执行）
- [ ] 答案是否可以从子问题答案中逻辑推导得出？
- [ ] ⚠️ **答案是否脱离了chunk？（禁止）**
- [ ] ⚠️ **答案是否引入了chunk外的信息？（禁止）**

**一票否决**: 不基于chunk、脱离原始信息 → `low`

---

输出JSON格式：
```json
{{
    "dimension_scores": {{
        "question_universality": {{"score": "high/medium/low", "issues": [], "veto": false}},
        "relevance": {{"score": "high/medium/low", "issues": [], "veto": false}},
        "logical_consistency": {{"score": "high/medium/low", "issues": [], "veto": false}},
        "terminology_usage": {{"score": "high/medium/low", "issues": [], "veto": false}},
        "factual_correctness": {{"score": "high/medium/low", "issues": [], "veto": false}},
        "answer_universality": {{"score": "high/medium/low", "issues": [], "veto": false}},
        "answer_completeness": {{"score": "high/medium/low", "issues": [], "veto": false}},
        "answer_reliability": {{"score": "high/medium/low", "issues": [], "veto": false}}
    }},
    "overall_quality": "high/medium/low",
    "veto_triggered": false,
    "veto_reasons": [],
    "chunk_grounding_check": {{
        "all_info_from_chunks": true,
        "external_info_detected": false,
        "problematic_statements": []
    }},
    "improvement_suggestions": [],
    "suitable_for_rl": true
}}
```
'''

    # ===== QA优化（基于chunk）=====
    refine_qa = '''你是半导体QA优化专家。基于评估反馈优化问答对。

**关键原则：优化过程必须保持答案基于chunk！**

# 原始问答对

**问题：** {question}
**答案：** {answer}

# 评估反馈

{evaluation_feedback}

# 单跳问答依据（包含chunk）

{single_hop_qas}

---

## 优化要求

### 1. 针对性改进
根据评估指出的具体问题进行改进（不改变整体框架）

### 2. chunk约束（最高优先级）⭐⭐⭐
- ✅ 优化后的答案必须仍然基于chunk
- ✅ 不得在优化过程中引入新的外部信息
- ✅ 只能重组和优化chunk中已有的表述

### 3. 保持核心信息
- 不改变问题的核心意图
- 保留答案的关键技术点
- 保持推理链的完整性

---

输出JSON格式：
```json
{{
    "refined_question": "优化后的问题",
    "refined_answer": "优化后的答案（必须基于chunk）",
    "changes_made": ["改进点1", "改进点2"],
    "chunk_grounding_preserved": true
}}
```
'''

    # ===== 25项最终验证 =====
    final_validation = '''你是半导体QA的终审专家。对以下问答进行25项全面检查。

# 待验证的问答对

**问题：** {question}
**答案：** {answer}

**单跳问答依据（包含chunk）：**
{single_hop_qas}

---

## 25项验证清单

### A. 问题质量（6项）
1. [ ] 问题是否清晰、具体、无歧义？
2. [ ] 问题是否具有通用性（不特指某篇论文）？
3. [ ] 问题是否单一（不包含多个子问题）？
4. [ ] 问题是否体现多跳推理的必要性？
5. [ ] 问题的技术术语使用是否准确？
6. [ ] 问题是否有实际价值（非trivial）？

### B. 答案质量（8项）
7. [ ] 答案是否准确回答了问题？
8. [ ] 答案是否完整（涵盖问题所有方面）？
9. [ ] 答案是否简洁（无冗余信息）？
10. [ ] 答案是否通用（不自指论文）？
11. [ ] 答案的技术术语使用是否准确？
12. [ ] 答案是否逻辑连贯、无矛盾？
13. [ ] 答案是否基于单跳QA的信息？⭐
14. [ ] 答案是否基于chunk（无编造信息）？⭐⭐⭐

### C. 推理质量（6项）
15. [ ] 推理步骤是否清晰、完整？
16. [ ] 推理逻辑是否正确、无跳跃？
17. [ ] 推理是否体现了多跳特性？
18. [ ] 推理是否基于单跳QA的答案？
19. [ ] 推理是否基于chunk信息？⭐
20. [ ] 推理的因果关系是否合理？

### D. 技术正确性（5项）
21. [ ] 技术原理是否正确？
22. [ ] 数值/参数是否合理？
23. [ ] 材料/方法描述是否准确？
24. [ ] 技术细节是否符合领域共识？
25. [ ] 是否存在事实性错误？

---

输出JSON格式：
```json
{{
    "validation_results": {{
        "passed_items": [1, 2, 3, ...],
        "failed_items": [
            {{"item": 14, "reason": "答案引入了chunk外的数据"}},
            {{"item": 20, "reason": "因果推理不严密"}}
        ]
    }},
    "overall_pass": true/false,
    "final_score": 23,
    "critical_issues": [],
    "recommendation": "approve/revise/reject"
}}
```
'''

    # ===== 有效性检查（添加chunk）=====
    qa_valid_check = '''检查该半导体问答对的有效性。

⚠️ **核心检查原则**：
1. 问题和答案必须基于给定的子问答对和chunk
2. 不得引入chunk中没有的事实、数据、结论
3. 答案必须围绕chunk，没有过于发散

问答对有效当且仅当：
1. 问题不是简单拼接多个问题
2. 提供的答案是唯一正确答案
3. 问题有唯一答案
4. 基于chunk可以解答
5. 问题答案语法合理，可读性强
6. 问题没有事实错误
7. 答案中没有事实错误
8. ⚠️ 答案围绕chunk回答的，没有过于发散
9. ⚠️ 答案没有引入chunk中没有的信息
10. ⚠️ 问题涉及的所有技术点都在chunk中有明确提及

完整的问答对信息：
问题: {question}
答案: {answer}

子问答对（包含chunk）: 
{single_hops_with_chunks}

输出JSON格式：
```json
{{
    "judgement": "yes 或 no",
    "analysis": "分析说明（50字内）",
    "chunk_grounding": "是否基于chunk: yes/no"
}}
```
'''

    # ===== 直接生成测试（添加chunk）=====
    direct_gen_check = """你是一个半导体领域的资深技术专家。请认真阅读以下问题，基于半导体专业知识给出准确、具体的答案。

问题：
{question}

⚠️ **参考信息（chunk）**：
以下是相关的技术背景信息（来自原始文献），可以参考但不能直接复制：

{chunks}

---

## 【回答要求】
1. 必须基于半导体领域的专业知识
2. 可以参考上述chunk信息，但要用自己的话重新组织
3. 如果问题涉及具体数值/参数/材料，必须给出具体信息
4. 禁止使用"合适的材料"、"适当的温度"等模糊表述
5. 答案简洁直接（50-150字）
6. 只基于确定的专业知识，不确定时说明需要具体条件

输出格式：
<answer>
[你的答案]
</answer>
"""

    # ===== LLM判断答案（添加chunk）=====
    llm_judge = """你是半导体领域的专业评估专家。判断预测答案是否正确回答了问题。

问题: {question}
标准答案: {gt_answer}
预测答案: {pred_answer}

⚠️ **技术背景（chunk）**：
{chunks}

## 【判断标准】
### 关键信息匹配
1. 数值/参数必须准确（允许±5%误差）
2. 材料名称必须准确
3. 工艺方法必须一致
4. 技术机制必须正确

### 允许的差异（视为Correct）
- ✅ 表述顺序不同但信息完整
- ✅ 使用同义词或等价术语
- ✅ 预测答案更详细但包含核心信息
- ✅ 基于chunk的合理推理

### 不允许的差异（视为Incorrect）
- ❌ 关键数值差异>±5%
- ❌ 材料名称不匹配或模糊表述
- ❌ 技术机制错误或相反
- ❌ 与chunk信息矛盾

仅输出以下两个词之一：
- **Correct**（预测答案正确）
- **Incorrect**（预测答案错误）
"""

    # ===== 替代答案检查（添加chunk）=====
    check_alternative_ans = '''判断预测答案是否也是该问题的正确答案。

问题: {question}
标准答案: {gt_answer}
预测答案: {pred_answer}

技术背景（chunk）: 
{chunks}

## 【判断原则】
1. 预测答案必须基于chunk且准确回答问题
2. 关键信息（数值/材料/方法）必须准确
3. 不得引入chunk中没有的信息

判断为"yes"的条件（必须全部满足）：
- ✅ 基于chunk信息
- ✅ 准确回答问题
- ✅ 技术正确无误

判断为"no"的情况（任一即否定）：
- ❌ 关键信息错误
- ❌ 未基于chunk
- ❌ 未回答问题核心

输出JSON格式：
{{
    "judgement": "yes 或 no",
    "reason": "判断理由（30字内）"
}}
'''

    # ===== 概念提取（使用LLM）=====
    extract_concepts_llm = '''你是半导体领域的专家。从以下问题中提取3-5个核心技术概念。

问题：{question}

要求：
1. 提取的概念必须是技术术语（如"能带结构"、"载流子迁移率"）
2. 概念应具有通用性（不特指某篇论文）
3. 按重要性排序
4. 每个概念3-6个汉字

输出JSON格式：
```json
{{
    "concepts": ["概念1", "概念2", "概念3"]
}}
```
'''


# ========================================================================
# 第2部分：LLM客户端
# ========================================================================

class LLMClient:
    """异步LLM客户端（支持vLLM/SGLang）"""
    
    def __init__(self, base_url: str, model: str, timeout: int = 300):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout
        
        # 检测服务类型
        if 'v1/completions' in base_url or 'generate' in base_url:
            self.api_type = 'vllm'
        elif 'v1/chat/completions' in base_url:
            self.api_type = 'openai'
        else:
            self.api_type = 'sglang'
        
        print(f"[LLM] 初始化客户端: {self.api_type} | {base_url}")
    
    async def generate(self, prompt: str, max_tokens: int = 4096, 
                      temperature: float = 0.7, **kwargs) -> str:
        """异步生成"""
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            if self.api_type == 'vllm':
                payload = {
                    "model": self.model,
                    "prompt": prompt,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    **kwargs
                }
            else:  # openai/sglang
                payload = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    **kwargs
                }
            
            async with session.post(self.base_url, json=payload) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(f"LLM API错误 {resp.status}: {error_text}")
                
                result = await resp.json()
                
                # 提取生成文本
                if self.api_type == 'vllm':
                    return result['choices'][0]['text']
                else:
                    return result['choices'][0]['message']['content']
    
    def parse_json(self, text: str) -> Dict:
        """容错解析JSON"""
        # 1. 提取```json ... ```
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            text = json_match.group(1)
        
        # 2. 提取``` ... ```
        if not json_match:
            code_match = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
            if code_match:
                text = code_match.group(1)
        
        # 3. 查找第一个{...}
        brace_match = re.search(r'\{.*\}', text, re.DOTALL)
        if brace_match:
            text = brace_match.group(0)
        
        # 4. 解析JSON
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            print(f"[WARNING] JSON解析失败: {e}")
            print(f"原始文本: {text[:200]}...")
            return {}


# ========================================================================
# 第3部分：知识库（支持chunk + 智能链接）
# ========================================================================

class SemiconductorKB:
    """半导体知识库 - 智能链接版（支持chunk）"""
    
    def __init__(self, qa_data: List[Dict], llm: LLMClient):
        # 验证chunk字段
        for qa in qa_data:
            if 'chunk' not in qa:
                print(f"[WARNING] QA-{qa.get('id', 'unknown')} 缺少chunk字段，将添加空chunk")
                qa['chunk'] = ""
        
        self.qa_data = {qa['id']: qa for qa in qa_data}
        self.qa_ids = list(self.qa_data.keys())
        self.llm = llm
        
        # 索引
        self.concept_cache = {}
        self.paper_to_qas = defaultdict(list)
        self.qa_to_paper = {}
        self.entity_to_qas = defaultdict(list)
        self.qa_to_entities = defaultdict(list)
        
        self._build_indexes()
        
        print(f"[KB] 加载 {len(self.qa_data)} 条单跳QA（包含chunk）")
        print(f"[KB] 论文数量: {len(self.paper_to_qas)}")
    
    def _build_indexes(self):
        """构建索引"""
        for qa_id, qa in self.qa_data.items():
            # 论文索引
            paper = qa.get('paper_name', 'unknown')
            self.paper_to_qas[paper].append(qa_id)
            self.qa_to_paper[qa_id] = paper
            
            # 实体索引（简单关键词提取）
            text = qa['question'] + ' ' + qa['answer']
            entities = self._extract_keywords(text)
            self.qa_to_entities[qa_id] = entities
            for entity in entities:
                self.entity_to_qas[entity].append(qa_id)
    
    def _extract_keywords(self, text: str, top_n: int = 5) -> List[str]:
        """简单关键词提取"""
        # 使用常见技术词汇作为关键词
        keywords = []
        tech_terms = ['半导体', '晶体管', '芯片', '材料', '器件', '工艺', 
                     '性能', '电路', '金刚石', '硅', 'GaN', 'SiC', '量子']
        
        for term in tech_terms:
            if term in text:
                keywords.append(term)
        
        return keywords[:top_n]
    
    def get_qa_with_chunk(self, qa_id: str) -> Dict:
        """获取QA（包含chunk）"""
        qa = self.qa_data.get(qa_id)
        if qa and 'chunk' not in qa:
            qa['chunk'] = ""
        return qa
    
    def find_bridgeable_qas(self, base_qa_id: str, top_k: int = 10) -> List[Tuple[str, str, str]]:
        """
        查找可桥接的QA（智能链接）
        
        返回: [(qa_id, bridge_entity, bridge_type), ...]
        """
        base_qa = self.get_qa_with_chunk(base_qa_id)
        base_answer = base_qa['answer']
        
        # 提取答案中的关键实体
        answer_entities = self._extract_keywords(base_answer)
        
        candidates = []
        
        for entity in answer_entities:
            # 查找问题中包含该实体的QA
            for qa_id in self.entity_to_qas.get(entity, []):
                if qa_id == base_qa_id:
                    continue
                
                next_qa = self.get_qa_with_chunk(qa_id)
                if entity in next_qa['question']:
                    # 判断桥接类型
                    bridge_type = self._infer_bridge_type(base_answer, next_qa['question'])
                    candidates.append((qa_id, entity, bridge_type))
        
        # 优先返回跨论文的链接
        base_paper = self.qa_to_paper[base_qa_id]
        cross_paper = [(qid, e, t) for qid, e, t in candidates 
                       if self.qa_to_paper.get(qid) != base_paper]
        same_paper = [(qid, e, t) for qid, e, t in candidates 
                      if self.qa_to_paper.get(qid) == base_paper]
        
        return (cross_paper + same_paper)[:top_k]
    
    def _infer_bridge_type(self, answer: str, question: str) -> str:
        """推断桥接类型"""
        if any(word in question for word in ['为什么', '原因', '机制', '如何影响']):
            return 'causal'
        elif any(word in question for word in ['提升', '优化', '改善', '增强']):
            return 'compositional'
        else:
            return 'inferential'
    
    def select_single_hops_smart(self, num_hops: int = 2) -> Tuple[List[str], str, str]:
        """
        智能选择单跳QA（优先跨论文链接）
        
        返回: (qa_ids, bridge_info, bridge_type)
        """
        # 随机选择第一个QA
        base_id = random.choice(self.qa_ids)
        selected_ids = [base_id]
        
        # 逐步链接
        for _ in range(num_hops - 1):
            candidates = self.find_bridgeable_qas(selected_ids[-1], top_k=20)
            
            if not candidates:
                # 兜底：随机选择
                available = [qid for qid in self.qa_ids if qid not in selected_ids]
                if available:
                    selected_ids.append(random.choice(available))
                break
            
            # 选择桥接候选
            next_id, bridge_entity, bridge_type = random.choice(candidates)
            selected_ids.append(next_id)
        
        # 生成桥接信息
        if len(selected_ids) >= 2:
            bridge_info = self._generate_bridge_description(selected_ids)
            bridge_type = candidates[0][2] if candidates else 'inferential'
        else:
            bridge_info = "基于技术关联进行推理"
            bridge_type = 'inferential'
        
        return selected_ids, bridge_info, bridge_type
    
    def _generate_bridge_description(self, qa_ids: List[str]) -> str:
        """生成桥接描述"""
        descriptions = []
        for i in range(len(qa_ids) - 1):
            descriptions.append(f"QA-{i+1}的答案中提到的关键概念是QA-{i+2}问题的基础")
        return "；".join(descriptions)
    
    def format_single_hops_for_prompt(self, qa_ids: List[str], 
                                     include_chunk: bool = True) -> str:
        """
        格式化单跳QA用于prompt（包含chunk）
        
        Args:
            qa_ids: QA ID列表
            include_chunk: 是否包含chunk信息
        """
        formatted_qas = []
        
        for i, qa_id in enumerate(qa_ids):
            qa = self.get_qa_with_chunk(qa_id)
            
            qa_str = f"QA-{i+1} (来自论文: {qa.get('paper_name', 'unknown')}):\n"
            qa_str += f"问题: {qa['question']}\n"
            qa_str += f"答案: {qa['answer']}\n"
            
            if include_chunk and qa.get('chunk'):
                # 截断过长的chunk（保留前1000字符）
                chunk_text = qa['chunk']
                if len(chunk_text) > 1000:
                    chunk_text = chunk_text[:1000] + "..."
                qa_str += f"原始chunk（知识来源）:\n{chunk_text}\n"
            
            formatted_qas.append(qa_str)
        
        return "\n\n".join(formatted_qas)
    
    def get_chunks_text(self, qa_ids: List[str]) -> str:
        """获取所有chunk的合并文本"""
        chunks = []
        for qa_id in qa_ids:
            qa = self.get_qa_with_chunk(qa_id)
            chunk = qa.get('chunk', '')
            if chunk:
                chunks.append(f"[Chunk from QA-{qa_id}]\n{chunk}")
        
        return "\n\n".join(chunks)


# ========================================================================
# 第4部分：专家QA生成器（集成4重检查）
# ========================================================================

class ExpertQAAgent:
    """专家级QA生成器（集成8维评估+4重检查+25项验证）"""
    
    def __init__(self, kb: SemiconductorKB, llm: LLMClient, 
                 max_refine_rounds: int = 2):
        self.kb = kb
        self.llm = llm
        self.max_refine_rounds = max_refine_rounds
        self.prompts = ExpertQAPrompts()
    
    async def generate_multihop_qa(self, single_hop_ids: List[str], 
                                   bridge_info: str, bridge_type: str,
                                   num_hops: int) -> Dict:
        """生成多跳QA（基于chunk）"""
        # 格式化单跳QA（包含chunk）
        single_hops_text = self.kb.format_single_hops_for_prompt(
            single_hop_ids, include_chunk=True
        )
        
        prompt = self.prompts.compose_multihop_qa.format(
            single_hops=single_hops_text,
            bridge_info=bridge_info,
            num_hops=num_hops,
            bridge_type=bridge_type
        )
        
        response = await self.llm.generate(prompt, max_tokens=3000, temperature=0.7)
        result = self.llm.parse_json(response)
        
        return {
            'question': result.get('multihop_question', ''),
            'answer': result.get('multihop_answer', ''),
            'reasoning_steps': result.get('reasoning_steps', []),
            'key_concepts': result.get('key_concepts', []),
            'bridge_type': result.get('bridge_type', bridge_type),
            'quality_check': result.get('quality_check', {})
        }
    
    async def evaluate_quality(self, qa_data: Dict, single_hop_ids: List[str]) -> Dict:
        """8维度质量评估（包含chunk验证）"""
        # 格式化单跳QA（包含chunk）
        single_hops_text = self.kb.format_single_hops_for_prompt(
            single_hop_ids, include_chunk=True
        )
        
        prompt = self.prompts.evaluate_8dimensions.format(
            question=qa_data['question'],
            answer=qa_data['answer'],
            reasoning_steps=json.dumps(qa_data.get('reasoning_steps', []), 
                                      ensure_ascii=False, indent=2),
            single_hop_qas=single_hops_text
        )
        
        response = await self.llm.generate(prompt, max_tokens=2000, temperature=0.3)
        evaluation = self.llm.parse_json(response)
        
        return evaluation
    
    async def refine_qa(self, qa_data: Dict, evaluation: Dict, 
                       single_hop_ids: List[str]) -> Dict:
        """优化QA（保持chunk约束）"""
        # 提取改进建议
        suggestions = evaluation.get('improvement_suggestions', [])
        if not suggestions:
            return qa_data  # 无需改进
        
        # 格式化单跳QA（包含chunk）
        single_hops_text = self.kb.format_single_hops_for_prompt(
            single_hop_ids, include_chunk=True
        )
        
        feedback = "\n".join([f"- {s}" for s in suggestions])
        
        prompt = self.prompts.refine_qa.format(
            question=qa_data['question'],
            answer=qa_data['answer'],
            evaluation_feedback=feedback,
            single_hop_qas=single_hops_text
        )
        
        response = await self.llm.generate(prompt, max_tokens=3000, temperature=0.5)
        refined = self.llm.parse_json(response)
        
        # 更新QA
        qa_data['question'] = refined.get('refined_question', qa_data['question'])
        qa_data['answer'] = refined.get('refined_answer', qa_data['answer'])
        qa_data['refinement_history'] = qa_data.get('refinement_history', [])
        qa_data['refinement_history'].append({
            'round': len(qa_data['refinement_history']) + 1,
            'changes': refined.get('changes_made', [])
        })
        
        return qa_data
    
    async def final_validate(self, qa_data: Dict, single_hop_ids: List[str]) -> Dict:
        """25项最终验证"""
        # 格式化单跳QA（包含chunk）
        single_hops_text = self.kb.format_single_hops_for_prompt(
            single_hop_ids, include_chunk=True
        )
        
        prompt = self.prompts.final_validation.format(
            question=qa_data['question'],
            answer=qa_data['answer'],
            single_hop_qas=single_hops_text
        )
        
        response = await self.llm.generate(prompt, max_tokens=2000, temperature=0.2)
        validation = self.llm.parse_json(response)
        
        return validation
    
    # ===== 4重增强质量检查（来自原系统）=====
    
    async def check_qa_valid(self, question: str, answer: str, 
                            single_hop_ids: List[str]) -> Tuple[bool, str]:
        """
        检查1: QA有效性（基于chunk）
        
        返回: (is_valid, analysis)
        """
        # 格式化单跳QA（包含chunk）
        single_hops_text = self.kb.format_single_hops_for_prompt(
            single_hop_ids, include_chunk=True
        )
        
        prompt = self.prompts.qa_valid_check.format(
            question=question,
            answer=answer,
            single_hops_with_chunks=single_hops_text
        )
        
        response = await self.llm.generate(prompt, max_tokens=500, temperature=0.3)
        result = self.llm.parse_json(response)
        
        is_valid = result.get('judgement', 'no').lower() == 'yes'
        analysis = result.get('analysis', '未知')
        chunk_grounding = result.get('chunk_grounding', 'no') == 'yes'
        
        # chunk约束检查
        if not chunk_grounding:
            is_valid = False
            analysis += "（未基于chunk）"
        
        return is_valid, analysis
    
    async def direct_generate(self, question: str, single_hop_ids: List[str],
                             n_samples: int = 3) -> Tuple[List[str], float]:
        """
        检查2: 直接生成测试（带chunk参考）
        
        让LLM直接回答问题（提供chunk作为参考），生成n次，检查一致性。
        
        返回: (generated_answers, consistency_score)
        """
        # 获取chunks文本
        chunks_text = self.kb.get_chunks_text(single_hop_ids)
        
        prompt = self.prompts.direct_gen_check.format(
            question=question,
            chunks=chunks_text
        )
        
        # 并发生成多个答案
        tasks = [self.llm.generate(prompt, max_tokens=800, temperature=0.8) 
                for _ in range(n_samples)]
        responses = await asyncio.gather(*tasks)
        
        # 提取<answer>...</answer>
        answers = []
        for resp in responses:
            match = re.search(r'<answer>(.*?)</answer>', resp, re.DOTALL)
            if match:
                answers.append(match.group(1).strip())
            else:
                answers.append(resp.strip())
        
        # 计算一致性（简单：检查关键词重叠）
        if len(answers) < 2:
            return answers, 0.0
        
        # 提取所有关键词
        all_keywords = set()
        for ans in answers:
            keywords = self.kb._extract_keywords(ans, top_n=10)
            all_keywords.update(keywords)
        
        # 计算每个答案的关键词覆盖率
        coverages = []
        for ans in answers:
            ans_keywords = set(self.kb._extract_keywords(ans, top_n=10))
            if all_keywords:
                coverage = len(ans_keywords & all_keywords) / len(all_keywords)
                coverages.append(coverage)
        
        consistency = sum(coverages) / len(coverages) if coverages else 0.0
        
        return answers, consistency
    
    async def llm_judge_answer(self, question: str, gt_answer: str, 
                              pred_answer: str, single_hop_ids: List[str]) -> str:
        """
        检查3: LLM判断答案正确性（基于chunk）
        
        返回: "Correct" 或 "Incorrect"
        """
        # 获取chunks文本
        chunks_text = self.kb.get_chunks_text(single_hop_ids)
        
        prompt = self.prompts.llm_judge.format(
            question=question,
            gt_answer=gt_answer,
            pred_answer=pred_answer,
            chunks=chunks_text
        )
        
        response = await self.llm.generate(prompt, max_tokens=50, temperature=0.1)
        
        # 提取判断结果
        if 'Correct' in response:
            return 'Correct'
        elif 'Incorrect' in response:
            return 'Incorrect'
        else:
            return 'Unknown'
    
    async def check_alternative_answer(self, question: str, gt_answer: str, 
                                      pred_answer: str, single_hop_ids: List[str]) -> bool:
        """
        检查4: 替代答案检查（基于chunk）
        
        判断pred_answer是否也是正确答案。
        
        返回: True（是正确答案）/ False（不是）
        """
        # 获取chunks文本
        chunks_text = self.kb.get_chunks_text(single_hop_ids)
        
        prompt = self.prompts.check_alternative_ans.format(
            question=question,
            gt_answer=gt_answer,
            pred_answer=pred_answer,
            chunks=chunks_text
        )
        
        response = await self.llm.generate(prompt, max_tokens=300, temperature=0.3)
        result = self.llm.parse_json(response)
        
        judgement = result.get('judgement', 'no').lower()
        return judgement == 'yes'
    
    async def run_4fold_checks(self, qa_data: Dict, single_hop_ids: List[str]) -> Dict:
        """
        执行4重增强质量检查
        
        返回检查结果字典
        """
        question = qa_data['question']
        answer = qa_data['answer']
        
        print(f"    [4重检查] 开始...")
        
        # 检查1: 有效性
        is_valid, valid_analysis = await self.check_qa_valid(question, answer, single_hop_ids)
        
        # 检查2: 直接生成
        direct_answers, consistency = await self.direct_generate(question, single_hop_ids, n_samples=3)
        
        # 检查3: LLM判断（使用直接生成的第一个答案）
        if direct_answers:
            judge_result = await self.llm_judge_answer(
                question, answer, direct_answers[0], single_hop_ids
            )
        else:
            judge_result = 'Unknown'
        
        # 检查4: 替代答案（使用直接生成的第一个答案）
        if direct_answers:
            is_alternative = await self.check_alternative_answer(
                question, answer, direct_answers[0], single_hop_ids
            )
        else:
            is_alternative = False
        
        # 汇总结果
        checks = {
            'validity_check': {
                'passed': is_valid,
                'analysis': valid_analysis
            },
            'direct_generation': {
                'answers': direct_answers,
                'consistency': consistency,
                'passed': consistency >= 0.5  # 阈值：50%
            },
            'llm_judgment': {
                'result': judge_result,
                'passed': judge_result == 'Correct'
            },
            'alternative_answer': {
                'is_alternative': is_alternative,
                'passed': is_alternative
            },
            'overall_passed': (
                is_valid and 
                consistency >= 0.5 and 
                (judge_result == 'Correct' or is_alternative)
            )
        }
        
        passed_count = sum([
            checks['validity_check']['passed'],
            checks['direct_generation']['passed'],
            checks['llm_judgment']['passed'],
            checks['alternative_answer']['passed']
        ])
        
        print(f"    [4重检查] 完成 - 通过 {passed_count}/4 项")
        
        return checks
    
    async def generate_one(self, num_hops: int = 2) -> Dict:
        """
        生成一个多跳QA（完整流程）
        
        流程：
        1. 智能选择单跳QA
        2. 生成多跳QA
        3. 8维度评估
        4. 迭代优化（最多2轮）
        5. 4重增强质量检查 ⭐ 新增
        6. 25项最终验证
        """
        print(f"\n{'='*60}")
        print(f"[开始生成] {num_hops}跳问答")
        print(f"{'='*60}")
        
        # Step 1: 选择单跳QA
        single_hop_ids, bridge_info, bridge_type = self.kb.select_single_hops_smart(num_hops)
        print(f"[Step 1] 选择单跳QA: {single_hop_ids}")
        print(f"         桥接类型: {bridge_type}")
        
        # Step 2: 生成多跳QA
        print(f"[Step 2] 生成多跳QA...")
        qa_data = await self.generate_multihop_qa(single_hop_ids, bridge_info, 
                                                  bridge_type, num_hops)
        
        # Step 3: 8维度评估 + 迭代优化
        for round_idx in range(self.max_refine_rounds + 1):
            print(f"[Step 3.{round_idx+1}] 8维度质量评估...")
            evaluation = await self.evaluate_quality(qa_data, single_hop_ids)
            
            overall_quality = evaluation.get('overall_quality', 'low')
            veto_triggered = evaluation.get('veto_triggered', False)
            
            print(f"         整体质量: {overall_quality}")
            print(f"         一票否决: {veto_triggered}")
            
            # 如果质量高或已达最大优化轮次，退出循环
            if overall_quality == 'high' or round_idx >= self.max_refine_rounds:
                qa_data['quality_evaluation'] = evaluation
                break
            
            # 否则进行优化
            if overall_quality in ['medium', 'low']:
                print(f"         开始优化（第{round_idx+1}轮）...")
                qa_data = await self.refine_qa(qa_data, evaluation, single_hop_ids)
        
        # Step 4: 4重增强质量检查 ⭐ 新增
        print(f"[Step 4] 4重增强质量检查...")
        enhanced_checks = await self.run_4fold_checks(qa_data, single_hop_ids)
        qa_data['enhanced_quality_checks'] = enhanced_checks
        
        # Step 5: 25项最终验证
        print(f"[Step 5] 25项最终验证...")
        final_validation = await self.final_validate(qa_data, single_hop_ids)
        qa_data['final_validation'] = final_validation
        
        final_pass = final_validation.get('overall_pass', False)
        final_score = final_validation.get('final_score', 0)
        print(f"         验证结果: {'通过' if final_pass else '未通过'}")
        print(f"         最终得分: {final_score}/25")
        
        # 汇总单跳信息（包含chunk）
        single_hops = []
        for qa_id in single_hop_ids:
            qa = self.kb.get_qa_with_chunk(qa_id)
            single_hops.append({
                'id': qa_id,
                'question': qa['question'],
                'answer': qa['answer'],
                'chunk': qa.get('chunk', '')
            })
        
        # 构建最终输出
        result = {
            'id': f"multihop_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000,9999)}",
            'question': qa_data['question'],
            'answer': qa_data['answer'],
            'single_hops': single_hops,
            'num_hops': num_hops,
            'bridge_info': bridge_info,
            'reasoning_steps': qa_data.get('reasoning_steps', []),
            'key_concepts': qa_data.get('key_concepts', []),
            'bridge_type': qa_data.get('bridge_type', bridge_type),
            
            # 质量评估结果
            'quality_evaluation': qa_data.get('quality_evaluation', {}),
            'final_validation': final_validation,
            'enhanced_quality_checks': enhanced_checks,  # ⭐ 新增
            
            # 优化历史
            'refinement_history': qa_data.get('refinement_history', []),
            
            # 质量标签
            'overall_quality': qa_data.get('quality_evaluation', {}).get('overall_quality', 'unknown'),
            'final_score': final_score,
            'passed_final_validation': final_pass,
            'passed_enhanced_checks': enhanced_checks.get('overall_passed', False),  # ⭐ 新增
            
            # 时间戳
            'generated_at': datetime.now().isoformat()
        }
        
        print(f"{'='*60}")
        print(f"[生成完成] 质量: {result['overall_quality']} | "
              f"得分: {final_score}/25 | "
              f"增强检查: {'通过' if result['passed_enhanced_checks'] else '未通过'}")
        print(f"{'='*60}\n")
        
        return result


# ========================================================================
# 第5部分：批量生成 + 质量报告
# ========================================================================

async def generate_batch(agent: ExpertQAAgent, num_samples: int, 
                        num_hops_range: Tuple[int, int] = (2, 3),
                        quality_filter: str = 'medium+',
                        output_format: str = 'jsonl') -> List[Dict]:
    """
    批量生成多跳QA
    
    Args:
        agent: ExpertQAAgent实例
        num_samples: 生成数量
        num_hops_range: 跳数范围 (min, max)
        quality_filter: 质量过滤 ('high', 'medium+', 'all')
        output_format: 输出格式 ('jsonl', 'json', 'both')
    
    Returns:
        生成的QA列表
    """
    print(f"\n{'#'*60}")
    print(f"# 批量生成任务")
    print(f"#   目标数量: {num_samples}")
    print(f"#   跳数范围: {num_hops_range}")
    print(f"#   质量过滤: {quality_filter}")
    print(f"{'#'*60}\n")
    
    results = []
    
    for i in range(num_samples):
        print(f"\n{'='*60}")
        print(f"  进度: {i+1}/{num_samples}")
        print(f"{'='*60}")
        
        # 随机跳数
        num_hops = random.randint(num_hops_range[0], num_hops_range[1])
        
        try:
            qa = await agent.generate_one(num_hops=num_hops)
            
            # 质量过滤
            quality = qa.get('overall_quality', 'unknown')
            passed_final = qa.get('passed_final_validation', False)
            passed_enhanced = qa.get('passed_enhanced_checks', False)
            
            if quality_filter == 'high':
                if quality == 'high' and passed_final and passed_enhanced:
                    results.append(qa)
                else:
                    print(f"[过滤] 质量不符合要求（需要high + 通过所有检查）")
            elif quality_filter == 'medium+':
                if quality in ['high', 'medium'] and passed_final:
                    results.append(qa)
                else:
                    print(f"[过滤] 质量不符合要求（需要medium+且通过最终验证）")
            else:  # 'all'
                results.append(qa)
        
        except Exception as e:
            print(f"[错误] 生成失败: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print(f"\n{'#'*60}")
    print(f"# 批量生成完成")
    print(f"#   成功生成: {len(results)}/{num_samples}")
    print(f"#   成功率: {len(results)/num_samples*100:.1f}%")
    print(f"{'#'*60}\n")
    
    return results


def generate_quality_report(results: List[Dict]) -> Dict:
    """生成质量报告"""
    if not results:
        return {'error': '无数据'}
    
    # 统计
    total = len(results)
    quality_dist = defaultdict(int)
    final_pass_count = 0
    enhanced_pass_count = 0
    scores = []
    bridge_types = defaultdict(int)
    
    for qa in results:
        quality_dist[qa.get('overall_quality', 'unknown')] += 1
        if qa.get('passed_final_validation', False):
            final_pass_count += 1
        if qa.get('passed_enhanced_checks', False):
            enhanced_pass_count += 1
        scores.append(qa.get('final_score', 0))
        bridge_types[qa.get('bridge_type', 'unknown')] += 1
    
    avg_score = sum(scores) / len(scores) if scores else 0
    
    report = {
        'total': total,
        'quality_distribution': dict(quality_dist),
        'final_validation': {
            'passed': final_pass_count,
            'rate': final_pass_count / total
        },
        'enhanced_checks': {
            'passed': enhanced_pass_count,
            'rate': enhanced_pass_count / total
        },
        'average_score': avg_score,
        'bridge_type_distribution': dict(bridge_types),
        'generated_at': datetime.now().isoformat()
    }
    
    return report


# ========================================================================
# 第6部分：主程序
# ========================================================================

async def main_async(args):
    """异步主程序"""
    # 加载单跳QA数据
    print(f"[1/5] 加载单跳QA数据: {args.input_file}")
    with open(args.input_file, 'r', encoding='utf-8') as f:
        qa_data = [json.loads(line) for line in f]
    
    print(f"      加载完成: {len(qa_data)} 条")
    
    # 验证chunk字段
    missing_chunk = sum(1 for qa in qa_data if 'chunk' not in qa)
    if missing_chunk > 0:
        print(f"      [警告] {missing_chunk} 条QA缺少chunk字段")
    
    # 初始化LLM客户端
    print(f"\n[2/5] 初始化LLM客户端")
    llm = LLMClient(base_url=args.llm_url, model=args.model)
    
    # 初始化知识库
    print(f"\n[3/5] 初始化知识库")
    kb = SemiconductorKB(qa_data, llm)
    
    # 初始化Agent
    print(f"\n[4/5] 初始化Expert QA Agent")
    agent = ExpertQAAgent(kb, llm, max_refine_rounds=args.max_refine_rounds)
    
    # 批量生成
    print(f"\n[5/5] 开始批量生成")
    results = await generate_batch(
        agent, 
        num_samples=args.num_samples,
        num_hops_range=(args.min_hops, args.max_hops),
        quality_filter=args.quality_filter,
        output_format=args.output_format
    )
    
    # 保存结果
    if results:
        # JSONL格式
        if args.output_format in ['jsonl', 'both']:
            jsonl_file = args.output_file
            with open(jsonl_file, 'w', encoding='utf-8') as f:
                for qa in results:
                    f.write(json.dumps(qa, ensure_ascii=False) + '\n')
            print(f"\n[保存] JSONL格式: {jsonl_file}")
        
        # JSON格式
        if args.output_format in ['json', 'both']:
            json_file = args.output_file.replace('.jsonl', '.json')
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"[保存] JSON格式: {json_file}")
        
        # 质量报告
        report = generate_quality_report(results)
        report_file = args.output_file.replace('.jsonl', '_report.json')
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"[保存] 质量报告: {report_file}")
        
        print(f"\n{'='*60}")
        print(f"质量报告摘要:")
        print(f"  总数: {report['total']}")
        print(f"  质量分布: {report['quality_distribution']}")
        print(f"  最终验证通过率: {report['final_validation']['rate']*100:.1f}%")
        print(f"  增强检查通过率: {report['enhanced_checks']['rate']*100:.1f}%")
        print(f"  平均得分: {report['average_score']:.1f}/25")
        print(f"{'='*60}")
    else:
        print("\n[警告] 没有生成任何QA")


def main():
    """主程序入口"""
    parser = argparse.ArgumentParser(description='半导体专家级多跳QA生成器（集成4重检查+chunk）')
    
    # 输入输出
    parser.add_argument('--input_file', type=str, required=True, 
                       help='单跳QA数据文件（JSONL格式，必须包含chunk字段）')
    parser.add_argument('--output_file', type=str, required=True,
                       help='输出文件路径')
    parser.add_argument('--output_format', type=str, default='jsonl',
                       choices=['jsonl', 'json', 'both'],
                       help='输出格式')
    
    # LLM配置
    parser.add_argument('--llm_url', type=str, required=True,
                       help='LLM API地址（如http://localhost:8000/v1/completions）')
    parser.add_argument('--model', type=str, required=True,
                       help='模型名称')
    
    # 生成配置
    parser.add_argument('--num_samples', type=int, default=10,
                       help='生成数量')
    parser.add_argument('--min_hops', type=int, default=2,
                       help='最小跳数')
    parser.add_argument('--max_hops', type=int, default=3,
                       help='最大跳数')
    parser.add_argument('--max_refine_rounds', type=int, default=2,
                       help='最大优化轮数')
    parser.add_argument('--quality_filter', type=str, default='medium+',
                       choices=['high', 'medium+', 'all'],
                       help='质量过滤级别')
    
    args = parser.parse_args()
    
    # 运行异步主程序
    asyncio.run(main_async(args))


if __name__ == '__main__':
    main()
