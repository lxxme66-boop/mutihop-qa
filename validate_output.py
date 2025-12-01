#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
输出数据验证脚本 - 验证集成版生成的多跳QA完整性
"""

import json
import sys
from typing import List, Dict


def validate_multihop_qa(qa: Dict, idx: int) -> List[str]:
    """
    验证单个多跳QA的完整性
    
    返回: 错误列表（空列表表示验证通过）
    """
    errors = []
    qa_id = qa.get('id', f'QA-{idx}')
    
    # 1. 基础字段
    required_basic = ['id', 'question', 'answer', 'single_hops', 'num_hops']
    for field in required_basic:
        if field not in qa:
            errors.append(f"[{qa_id}] 缺少必需字段: {field}")
    
    # 2. 单跳QA字段（包含chunk）⭐
    if 'single_hops' in qa:
        for i, single_hop in enumerate(qa['single_hops']):
            required_single = ['id', 'question', 'answer', 'chunk']
            for field in required_single:
                if field not in single_hop:
                    errors.append(f"[{qa_id}] single_hops[{i}] 缺少字段: {field}")
            
            # 验证chunk不为空
            if 'chunk' in single_hop and not single_hop['chunk']:
                errors.append(f"[{qa_id}] single_hops[{i}] chunk为空")
    
    # 3. 推理步骤（包含chunk引用）⭐
    if 'reasoning_steps' in qa:
        for i, step in enumerate(qa['reasoning_steps']):
            required_step = ['step', 'content', 'based_on']
            for field in required_step:
                if field not in step:
                    errors.append(f"[{qa_id}] reasoning_steps[{i}] 缺少字段: {field}")
            
            # 检查chunk引用（可选但推荐）
            if 'chunk_reference' not in step:
                errors.append(f"[{qa_id}] reasoning_steps[{i}] 缺少chunk_reference（推荐）")
    
    # 4. 质量评估字段
    if 'quality_evaluation' not in qa:
        errors.append(f"[{qa_id}] 缺少quality_evaluation")
    else:
        eval_data = qa['quality_evaluation']
        
        # 检查chunk验证字段 ⭐
        if 'chunk_grounding_check' not in eval_data:
            errors.append(f"[{qa_id}] quality_evaluation 缺少chunk_grounding_check")
        
        if 'dimension_scores' not in eval_data:
            errors.append(f"[{qa_id}] quality_evaluation 缺少dimension_scores")
    
    # 5. 4重增强质量检查 ⭐⭐⭐
    if 'enhanced_quality_checks' not in qa:
        errors.append(f"[{qa_id}] 缺少enhanced_quality_checks（4重检查）")
    else:
        checks = qa['enhanced_quality_checks']
        required_checks = [
            'validity_check',
            'direct_generation',
            'llm_judgment',
            'alternative_answer',
            'overall_passed'
        ]
        for field in required_checks:
            if field not in checks:
                errors.append(f"[{qa_id}] enhanced_quality_checks 缺少字段: {field}")
    
    # 6. 25项最终验证
    if 'final_validation' not in qa:
        errors.append(f"[{qa_id}] 缺少final_validation")
    else:
        validation = qa['final_validation']
        if 'validation_results' not in validation:
            errors.append(f"[{qa_id}] final_validation 缺少validation_results")
        if 'final_score' not in validation:
            errors.append(f"[{qa_id}] final_validation 缺少final_score")
    
    # 7. 质量标签
    required_labels = [
        'overall_quality',
        'passed_final_validation',
        'passed_enhanced_checks'  # ⭐ 新增标识
    ]
    for field in required_labels:
        if field not in qa:
            errors.append(f"[{qa_id}] 缺少质量标签: {field}")
    
    return errors


def validate_jsonl_file(filepath: str) -> Dict:
    """
    验证JSONL文件
    
    返回: 验证报告
    """
    print(f"正在验证文件: {filepath}\n")
    
    all_errors = []
    total_count = 0
    valid_count = 0
    
    stats = {
        'has_chunk': 0,
        'has_chunk_reference': 0,
        'has_enhanced_checks': 0,
        'passed_enhanced_checks': 0,
        'passed_final_validation': 0,
        'quality_distribution': {'high': 0, 'medium': 0, 'low': 0, 'unknown': 0}
    }
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_idx, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    qa = json.loads(line)
                    total_count += 1
                    
                    # 验证QA
                    errors = validate_multihop_qa(qa, line_idx)
                    
                    if errors:
                        all_errors.extend(errors)
                    else:
                        valid_count += 1
                    
                    # 统计
                    if 'single_hops' in qa:
                        has_all_chunks = all(
                            sh.get('chunk') for sh in qa['single_hops']
                        )
                        if has_all_chunks:
                            stats['has_chunk'] += 1
                    
                    if 'reasoning_steps' in qa:
                        has_all_refs = all(
                            'chunk_reference' in step for step in qa['reasoning_steps']
                        )
                        if has_all_refs:
                            stats['has_chunk_reference'] += 1
                    
                    if 'enhanced_quality_checks' in qa:
                        stats['has_enhanced_checks'] += 1
                        if qa['enhanced_quality_checks'].get('overall_passed'):
                            stats['passed_enhanced_checks'] += 1
                    
                    if qa.get('passed_final_validation'):
                        stats['passed_final_validation'] += 1
                    
                    quality = qa.get('overall_quality', 'unknown')
                    stats['quality_distribution'][quality] = stats['quality_distribution'].get(quality, 0) + 1
                
                except json.JSONDecodeError as e:
                    all_errors.append(f"[第{line_idx}行] JSON解析错误: {e}")
    
    except FileNotFoundError:
        print(f"❌ 错误: 文件不存在 - {filepath}")
        sys.exit(1)
    
    # 生成报告
    print("="*60)
    print("验证报告")
    print("="*60)
    print(f"\n📊 基本统计:")
    print(f"  总数: {total_count}")
    print(f"  完整: {valid_count} ({valid_count/total_count*100:.1f}%)" if total_count > 0 else "  完整: 0")
    print(f"  错误: {len(all_errors)}")
    
    print(f"\n⭐ 集成功能统计:")
    print(f"  包含chunk: {stats['has_chunk']}/{total_count} ({stats['has_chunk']/total_count*100:.1f}%)" if total_count > 0 else "")
    print(f"  包含chunk引用: {stats['has_chunk_reference']}/{total_count} ({stats['has_chunk_reference']/total_count*100:.1f}%)" if total_count > 0 else "")
    print(f"  包含4重检查: {stats['has_enhanced_checks']}/{total_count} ({stats['has_enhanced_checks']/total_count*100:.1f}%)" if total_count > 0 else "")
    
    print(f"\n✅ 质量指标:")
    print(f"  4重检查通过: {stats['passed_enhanced_checks']}/{total_count} ({stats['passed_enhanced_checks']/total_count*100:.1f}%)" if total_count > 0 else "")
    print(f"  最终验证通过: {stats['passed_final_validation']}/{total_count} ({stats['passed_final_validation']/total_count*100:.1f}%)" if total_count > 0 else "")
    
    print(f"\n📈 质量分布:")
    for quality, count in stats['quality_distribution'].items():
        print(f"  {quality}: {count} ({count/total_count*100:.1f}%)" if total_count > 0 else f"  {quality}: {count}")
    
    if all_errors:
        print(f"\n❌ 发现 {len(all_errors)} 个问题:")
        for i, error in enumerate(all_errors[:20], start=1):  # 只显示前20个
            print(f"  {i}. {error}")
        if len(all_errors) > 20:
            print(f"  ... 还有 {len(all_errors)-20} 个问题未显示")
    else:
        print("\n✅ 所有QA验证通过！")
    
    print("\n" + "="*60)
    
    return {
        'total': total_count,
        'valid': valid_count,
        'errors': all_errors,
        'stats': stats
    }


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python validate_output.py <output_file.jsonl>")
        print("\n示例:")
        print("  python validate_output.py test_output.jsonl")
        print("  python validate_output.py multihop_qa.jsonl")
        sys.exit(1)
    
    filepath = sys.argv[1]
    report = validate_jsonl_file(filepath)
    
    # 返回退出码
    if report['valid'] == report['total'] and report['total'] > 0:
        sys.exit(0)  # 成功
    else:
        sys.exit(1)  # 失败


if __name__ == '__main__':
    main()
