# MemSense Feature Development & Validation Workflow

本文档规范新能力开发的完整流程，包括Feature Flag机制、记忆库复用、测试验证和质量控制。
所有agent在开发新功能时必须遵循此流程。

---

## 1. 核心原则

1. **Feature Flag控制一切** — 新功能默认关闭，代码可随时commit，不影响现有行为
2. **记忆库只读** — 已ingested的benchmark记忆库永远不被修改，evaluation只做recall+answer+judge
3. **基线对比** — 每次验证必须有flag OFF(基线)和flag ON(新功能)的对比数据
4. **分层验证** — 快速检查(秒级) → 端到端验证(小时级)，不跳级

---

## 2. 现有基础设施

### 2.1 持久化记忆库

已ingested的benchmark记忆库存在`~/.pg0/instances/`中，随时可用：

| 实例名 | Benchmark | LLM模型 | Facts | 状态 |
|--------|-----------|---------|-------|------|
| `bench-locomo-minimax` | LoCoMo 10conv | MiniMax-M2.7 | 2,040 | 就绪 |
| `bench-locomo-kimi` | LoCoMo 10conv | kimi-latest | 2,020 | 就绪 |
| `bench-longmemeval-minimax` | LongMemEval | MiniMax-M2.7 | 进行中 | 部分 |
| `bench-longmemeval-kimi2` | LongMemEval | kimi-latest | 进行中 | 部分 |

### 2.2 基线数据

存放在`hindsight-dev/benchmarks/baselines/`：

| 文件 | 内容 |
|------|------|
| `locomo_minimax_m27_eval_baseline.json` | MiniMax全量eval: **89.1%**, 4077 tok/query |
| `locomo_kimi_baseline.json` | Kimi全量eval: **85.7%**(排除限流), 4076 tok/query |

### 2.3 工具脚本

| 脚本 | 用途 |
|------|------|
| `scripts/benchmarks/eval-locomo.sh` | 一键运行LoCoMo evaluation |
| `scripts/benchmarks/recall_replay.py` | 秒级token效率模拟(不调LLM) |
| `scripts/benchmarks/check_regression.py` | 精度回归检测 |
| `scripts/benchmarks/ingest-benchmark-db.py` | 构建/管理记忆库 |

### 2.4 pgweb数据查看

记忆库可通过pgweb在浏览器中查看（需pg0实例处于运行状态）：

```bash
# 启动pgweb查看某个记忆库
~/.local/bin/pgweb \
  --host localhost --port <pg_port> \
  --user hindsight --pass hindsight --db hindsight \
  --listen <web_port> --bind 127.0.0.1
```

pg0端口查看：`cat ~/.pg0/instances/<实例名>/instance.json`

---

## 3. Feature Flag规范

### 3.1 添加新Feature Flag

每个新功能对应一个环境变量开关，在`config.py`中添加：

```python
# 1. 环境变量名
ENV_MY_FEATURE_ENABLED = "HINDSIGHT_API_MY_FEATURE_ENABLED"
DEFAULT_MY_FEATURE_ENABLED = False  # 默认关闭

# 2. HindsightConfig dataclass中添加字段
my_feature_enabled: bool

# 3. from_env()中添加解析
my_feature_enabled=os.getenv(ENV_MY_FEATURE_ENABLED, str(DEFAULT_MY_FEATURE_ENABLED)).lower() == "true",

# 4. 如需per-bank可配，加入_CONFIGURABLE_FIELDS
_CONFIGURABLE_FIELDS = {
    ...,
    "my_feature_enabled",
}
```

### 3.2 代码中使用Flag

```python
# 在功能分叉处使用if判断
config = get_config()
if config.my_feature_enabled:
    result = new_logic(...)      # 新功能
else:
    result = existing_logic(...)  # 现有行为，完全不变
```

### 3.3 Flag命名规范

- 格式: `HINDSIGHT_API_<FEATURE_NAME>_ENABLED`
- 默认值: `False`（新功能默认关闭）
- 类型: `bool`

---

## 4. 开发验证流程

### 4.1 流程总览

```
开发代码(flag默认OFF)
    │
    ├─ commit到main（现有行为不受影响）
    │
    ├─ Step 1: recall_replay快速检查 (3秒, 不调LLM)
    │    └─ 方向性确认: token变化趋势 + coverage估算
    │
    ├─ Step 2: 端到端eval(flag ON vs OFF对比)
    │    └─ 真实精度 + token stats
    │
    └─ Step 3: 判定
         ├─ 精度不退步 + token显著下降 → 保留，更新基线
         └─ 精度退步 → flag保持OFF，排查优化
```

### 4.2 Step 1: recall_replay快速检查（3秒）

**用途**: 不调LLM，用缓存的recall结果模拟不同配置的token/coverage效果。
**适用场景**: 调整max_results、token budget等输出层参数时的快速方向性检查。

```bash
# 对比不同配置
uv run python scripts/benchmarks/recall_replay.py \
  --results hindsight-dev/benchmarks/baselines/locomo_minimax_m27_eval_baseline.json \
  --compare

# 自定义配置
uv run python scripts/benchmarks/recall_replay.py \
  --results hindsight-dev/benchmarks/baselines/locomo_minimax_m27_eval_baseline.json \
  --max-results 15 --max-tokens 2000
```

**判定标准**: coverage > 95% 才值得进入Step 2。

### 4.3 Step 2: 端到端eval（30min - 2h）

**用途**: 真实recall → LLM answer → LLM judge的完整验证。
**关键**: 使用已ingested的记忆库，`--skip-ingestion`确保不污染。

#### 4.3.1 环境隔离

使用`HINDSIGHT_DOTENV_PATH`指定LLM配置，避免.env互相覆盖：

```bash
# MiniMax评测（推荐，稳定无限流）
HINDSIGHT_API_DATABASE_URL="pg0://bench-locomo-minimax" \
  ./scripts/benchmarks/eval-locomo.sh minimax full

# Kimi评测
HINDSIGHT_DOTENV_PATH=.env.kimi \
  HINDSIGHT_API_DATABASE_URL="pg0://bench-locomo-kimi" \
  ./scripts/benchmarks/eval-locomo.sh kimi full
```

同时跑两个不同模型时，必须用`HINDSIGHT_DOTENV_PATH`隔离，否则config.py的
`load_dotenv(override=True)`会导致后启动的进程覆盖前一个的LLM配置。

#### 4.3.2 对比方式

同一个记忆库跑两次，一次flag OFF一次flag ON：

```bash
# 基线（flag OFF）
HINDSIGHT_API_DATABASE_URL="pg0://bench-locomo-minimax" \
  HF_HUB_OFFLINE=1 \
  ./scripts/benchmarks/eval-locomo.sh minimax full
# 保存基线结果
cp hindsight-dev/benchmarks/locomo/results/benchmark_results.json /tmp/baseline.json

# 新功能（flag ON）
HINDSIGHT_API_DATABASE_URL="pg0://bench-locomo-minimax" \
  HINDSIGHT_API_MY_FEATURE_ENABLED=true \
  HF_HUB_OFFLINE=1 \
  ./scripts/benchmarks/eval-locomo.sh minimax full
# 保存新功能结果
cp hindsight-dev/benchmarks/locomo/results/benchmark_results.json /tmp/feature.json
```

#### 4.3.3 快速验证（3 conv子集，~30min）

开发迭代中先用3个conversation快速验证，确认方向后再跑全量：

```bash
HINDSIGHT_API_DATABASE_URL="pg0://bench-locomo-minimax" \
  HINDSIGHT_API_MY_FEATURE_ENABLED=true \
  HF_HUB_OFFLINE=1 \
  ./scripts/benchmarks/eval-locomo.sh minimax quick
```

`quick`模式跑conv-49/conv-44/conv-48（470题，覆盖不同难度）。

### 4.4 Step 3: 判定标准

| 指标 | 通过条件 | 说明 |
|------|---------|------|
| 精度 | flag ON精度 ≥ flag OFF精度 - 2pp | 允许2pp波动(LLM judge噪声) |
| Token | avg_context_tokens显著下降 | 至少降20%才有意义 |
| P95 Token | 无极端退化 | P95不应比基线高 |

---

## 5. 记忆库管理

### 5.1 不可污染规则

**以下操作会污染记忆库，严禁在benchmark库上执行**：
- 不带`--skip-ingestion`运行benchmark（会delete_bank + 重新ingestion）
- 直接调用retain/retain_batch API写入新数据
- 调用delete_bank/delete API删除数据
- 运行consolidation（会创建新的observation记录）← 除非是有意为之的实验

**安全操作（只读）**：
- `--skip-ingestion`运行evaluation ✅
- recall API查询 ✅
- pgweb浏览 ✅
- `--list-banks`查看统计 ✅
- token_usage表写入 ✅（独立表，不影响记忆数据）

### 5.2 创建新记忆库

如需修改ingestion逻辑后测试，创建新的pg0实例，不要动现有库：

```bash
# 创建新实例（使用新名字）
HINDSIGHT_API_DATABASE_URL="pg0://bench-locomo-minimax-v2" \
  uv run python scripts/benchmarks/ingest-benchmark-db.py locomo
```

### 5.3 记忆库上跑consolidation（生成observation层）

这是一种特殊操作——会往memory_units写入新记录（fact_type='observation'），
属于有意的记忆库升级而非污染。操作前备份：

```bash
# 备份
cp -r ~/.pg0/instances/bench-locomo-minimax ~/.pg0/instances/bench-locomo-minimax-backup

# 跑consolidation（后续补充具体命令）
# ...

# 如果效果不好，恢复
rm -rf ~/.pg0/instances/bench-locomo-minimax
mv ~/.pg0/instances/bench-locomo-minimax-backup ~/.pg0/instances/bench-locomo-minimax
```

### 5.4 查看记忆库内容

```bash
# 命令行查看banks
HINDSIGHT_API_DATABASE_URL="pg0://bench-locomo-minimax" \
  uv run python scripts/benchmarks/ingest-benchmark-db.py --list-banks

# pgweb浏览器查看（需pg0实例运行中）
~/.local/bin/pgweb --host localhost --port 5437 \
  --user hindsight --pass hindsight --db hindsight \
  --listen 8085 --bind 127.0.0.1
# 浏览器打开 http://localhost:8085
```

---

## 6. Git提交规范

### 6.1 Commit规范

- 新功能代码（含flag）正常commit到main
- Commit message使用conventional commit格式：`feat:`, `fix:`, `refactor:`
- 不包含AI生成标记（Co-Authored-By等）
- 不提交docs/目录下的内部设计文档（竞品分析等）

### 6.2 PR Quality Checklist

每个PR必须满足`.github/pull_request_template.md`中的检查清单：

- [ ] 新函数有类型注解
- [ ] 新文件有对应test_*.py
- [ ] ruff lint/format通过
- [ ] pytest通过
- [ ] 如改recall路径：eval-locomo.sh quick无精度回退
- [ ] 如改API：OpenAPI spec更新
- [ ] 如改schema：migration有upgrade+downgrade

### 6.3 基线更新

当新feature验证通过并决定保留时：

```bash
# 用flag ON的结果更新基线
cp hindsight-dev/benchmarks/locomo/results/benchmark_results.json \
   hindsight-dev/benchmarks/baselines/locomo_minimax_m27_eval_baseline.json
git add hindsight-dev/benchmarks/baselines/
git commit -m "bench: update baseline after <feature_name> (XX.X% → XX.X%, XXXX→XXXX tok)"
```

---

## 7. 典型开发示例：添加Observation-Preferred Recall

以下展示一个完整的feature开发验证周期：

### 7.1 开发

```python
# config.py — 添加flag
ENV_OBSERVATION_PREFERRED_RECALL = "HINDSIGHT_API_OBSERVATION_PREFERRED_RECALL"
DEFAULT_OBSERVATION_PREFERRED_RECALL = False

# memory_engine.py — recall逻辑
if config.observation_preferred_recall:
    # 优先返回observations，不够再补raw facts
    ...
else:
    # 现有逻辑不变
    ...
```

### 7.2 验证

```bash
# Step 1: 先对记忆库跑consolidation生成observations
cp -r ~/.pg0/instances/bench-locomo-minimax ~/.pg0/instances/bench-locomo-minimax-with-obs
HINDSIGHT_API_DATABASE_URL="pg0://bench-locomo-minimax-with-obs" \
  uv run python -m hindsight_api.admin run-consolidation  # 具体命令待确认

# Step 2: flag OFF基线
HINDSIGHT_API_DATABASE_URL="pg0://bench-locomo-minimax-with-obs" \
  HF_HUB_OFFLINE=1 \
  ./scripts/benchmarks/eval-locomo.sh minimax quick

# Step 3: flag ON验证
HINDSIGHT_API_DATABASE_URL="pg0://bench-locomo-minimax-with-obs" \
  HINDSIGHT_API_OBSERVATION_PREFERRED_RECALL=true \
  HF_HUB_OFFLINE=1 \
  ./scripts/benchmarks/eval-locomo.sh minimax quick

# Step 4: 对比结果
python scripts/benchmarks/check_regression.py \
  --results hindsight-dev/benchmarks/locomo/results/benchmark_results.json \
  --baseline-accuracy 89.0 --max-regression 2.0
```

### 7.3 判定

```
基线(flag OFF): 89.1%, avg 4077 tok
新功能(flag ON): 87.5%, avg 1200 tok

精度退步1.6pp < 2pp阈值 → 通过
Token下降70% → 显著
结论: 保留，更新基线
```

---

## 8. 常见问题

### Q: 两个不同模型的eval能同时跑吗？

可以，但必须用`HINDSIGHT_DOTENV_PATH`隔离LLM配置：
```bash
# 进程1
HINDSIGHT_DOTENV_PATH=.env.kimi HINDSIGHT_API_DATABASE_URL="pg0://bench-locomo-kimi" ... &
# 进程2
HINDSIGHT_API_DATABASE_URL="pg0://bench-locomo-minimax" ... &
```

不设`HINDSIGHT_DOTENV_PATH`时，`config.py`会加载`.env`文件并`override=True`覆盖所有环境变量。

### Q: eval跑完后记忆库真的没被改吗？

`--skip-ingestion`跳过delete_bank和retain_batch。recall是纯读操作。唯一的写入是`token_usage`表（独立表，不影响memory_units/entities/memory_links）。

### Q: HuggingFace模型加载报错怎么办？

设置离线模式避免网络请求：
```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 ./scripts/benchmarks/eval-locomo.sh ...
```
前提是模型已缓存在`~/.cache/huggingface/hub/`（首次运行需要联网下载）。

### Q: 如何只跑特定conversation？

```bash
./scripts/benchmarks/eval-locomo.sh minimax conv-49
```

### Q: pg0实例没启动怎么连接？

pg0实例在MemoryEngine初始化时自动启动。直接跑任何benchmark或ingest脚本就会启动对应实例。也可以用`--list-banks`触发启动：
```bash
HINDSIGHT_API_DATABASE_URL="pg0://bench-locomo-minimax" \
  uv run python scripts/benchmarks/ingest-benchmark-db.py --list-banks
```
