# MemSense Benchmark Baselines

基线数据用于后续优化迭代的对比参考。每次优化后重跑benchmark，与这些基线对比准确率变化。

## 基线汇总

### LoComo（多轮对话记忆准确率）

| 模型 | 测试范围 | 准确率 | 问题数 | 日期 | 文件 |
|------|---------|--------|--------|------|------|
| MiniMax M2.7 | 全量10对话 | **76.6%** | 1540 | 2026-04-07 | `locomo_minimax_m27_baseline.json` |

### LongMemEval（长期记忆精准检索）

| 模型 | 测试范围 | 准确率 | 问题数 | 日期 | 文件 |
|------|---------|--------|--------|------|------|
| MiniMax M2.7 | 50题 | **88.0%** | 50 | 2026-04-09 | `longmemeval_minimax_m27_baseline.json` |

### 参考值

| 系统 | LoComo | LongMemEval | 来源 |
|------|--------|-------------|------|
| Hindsight官方 (v0.4.19) | 92.0% | 94.6% | Hindsight blog (2026-03-23) |

## 注意事项

- LoComo的category=5（Yes/No题）被benchmark自动跳过，实际测试1540/1986题
- MiniMax M2.7的conv-26(42.8%)和conv-47(23.3%)为异常值，去除后8个对话均值87.2%
- LongMemEval数据集中13/500题有重复session_id，已在代码中修复去重
- 不同模型的分数不能直接横向对比（answer generation和judge都用同一模型，模型能力影响全链路）

## 快速迭代对照集

优化时不需要每次跑全量，用以下命令快速A/B对比：

```bash
# LoComo 2对话（~15分钟）
./scripts/benchmarks/run-locomo.sh --max-conversations 2

# LongMemEval 20题（~30分钟）
./scripts/benchmarks/run-longmemeval.sh --max-instances 20 --parallel 2
```
