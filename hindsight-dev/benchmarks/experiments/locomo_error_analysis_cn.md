# LoCoMo 89.1% 基线 — 168 个错题深度分析报告

> 基线文件: locomo_minimax_m27_eval_baseline.json
> LLM: MiniMax M2.7（记忆提取 + 答题 + 评审三端同模型）
> 总题数: 1540（排除 Category 5 Yes/No 题后）
> 正确: 1372（89.1%），错误: 168（10.9%）
> 分析日期: 2026-04-12

---

## 一、执行摘要

本报告对 LoCoMo 基线中 168 个错误答案进行了系统性根因分析，关键发现:

1. **69% 的错误（116 题）不是记忆体的问题** — 正确证据已检索到 top-10，失败在 LLM 答题环节
2. **最集中的可修复问题是 Cat 2 时间推理**（34 题日期差 ±1 周）— post-extraction enrichment 已验证可修正
3. **Cat 3 多跳推理是模型能力天花板**（65.6% 准确率）— 需要更强 LLM 或 agentic 架构
4. **fact extraction 的概括化倾向**导致 17 个提取遗漏（hoodie -> clothing line 等）

---

## 二、分析方法论

### 2.1 验证链

对每个错题执行 5 步精确归因:

1. 从正确答案提取关键词（>=3 字符，过滤停用词）
2. 在**全部**检索到的记忆中搜索关键词（不限 top-10，覆盖全部 100+ 条）
3. 确定证据位置: top-10 内 / top-10 外 / 完全不存在
4. 结合 LLM 实际回答和评审理由分类失败模式
5. 与 LoCoMo 题目类别交叉分析

### 2.2 局限性

- 关键词匹配是近似方法，部分情况（答案是数字如 "3"）无法检测
- LLM 的 "无信息" 判断可能是对 fact 文本措辞不匹配的合理反应
- 评审（judge）本身使用同一模型 MiniMax M2.7，存在 ~2pp 的随机噪声

---

## 三、168 题全景归因

### 3.1 三大失败分组

| 分组 | 含义 | 题数 | 占比 | 核心问题 |
|------|------|------|------|---------|
| GROUP A | 证据在 top-10，LLM 仍答错 | 116 | 69% | 答题环节失败 |
| GROUP B | 证据在记忆库但排在 top-10 外 | 24 | 14% | 检索排序不足 |
| GROUP C | 证据不在任何记忆中 | 28 | 17% | 事实提取遗漏 |

### 3.2 细分失败模式

| 模式 | 题数 | 占比 | 描述 |
|------|------|------|------|
| A1: 证据在场，LLM 说「无信息」| 37 | 22% | LLM 扫描 100+ 条 facts 时未能关联查询与证据 |
| A2: 证据在场，LLM 答错 | 79 | 47% | LLM 选了错误的 fact 或提取了错误的细节 |
| B1: 证据在 top-10 外，LLM 说「无信息」| 6 | 4% | 证据排在 rank 11-20，刚好出局 |
| B2: 证据在 top-10 外，LLM 答错 | 18 | 11% | 证据排名低，LLM 用了 top 中的错误 fact |
| C0: 答案过短无法检测 | 3 | 2% | 正确答案为数字（如 "3"），无法关键词匹配 |
| C1: 无证据，LLM 正确说「无信息」| 7 | 4% | 真正的提取缺失，LLM 判断正确 |
| C2: 无证据，LLM 编造答案 | 18 | 11% | 提取遗漏 + hallucination |

### 3.3 关键洞察

**69% 的错误（GROUP A）是答题环节的问题，不是记忆体的问题。** 检索管线已成功将正确证据排到 top-10，但 MiniMax M2.7 在 answer generation 阶段未能正确使用。

这意味着:
- **即使检索完美（100% 正确证据在 top-1），仍有 69% 的当前错误无法通过改善检索来解决**
- 改善答题质量（更好的 prompt 或更强的 LLM）的理论天花板为 +7.5pp（89.1% -> 96.6%）
- 改善检索排序（GROUP B）的天花板为 +1.6pp
- 改善事实提取（GROUP C）的天花板为 +1.8pp

---

## 四、按 LoCoMo 类别深度分析

### 4.1 类别总览

| 类别 | 总题 | 正确 | 错题 | 准确率 | 最突出问题 |
|------|------|------|------|--------|-----------|
| Single-hop（单跳事实） | 282 | 258 | 24 | 91.5% | A2(8题) |
| Temporal（时间推理） | 321 | 274 | 47 | 85.4% | A2(34题) |
| Multi-hop（多跳推理） | 96 | 63 | 33 | 65.6% | A1(11题) |
| Descriptive（开放描述） | 841 | 777 | 64 | 92.4% | A2(27题) |

### 4.2 Cat 2 时间推理（85.4%）— 最大可修复弱点

47 个错题中 **34 个是 A2**（证据在 top-10 但提取/选择的日期有误）。

**系统性模式**: LLM 在 fact extraction 时将相对日期（"last Friday"）转为绝对日期，频繁出现 **整整 1 周的偏差**:

| 原文表达 | LLM 计算 | 正确日期 | 误差 | session 日期 |
|---------|---------|---------|------|-------------|
| "last Friday" | July 14 | July 21 | -7 天 | July 23 |
| "Last Wednesday" | Feb 1 | Feb 8 | -7 天 | Feb 9 |
| "last Friday" | Oct 13 | Oct 20 | -7 天 | Oct 22 |
| "last weekend" | Jul 8 | Jul 15 | -7 天 | Jul 17 |
| "last Friday" | May 20 | May 21 | -1 天 | May 25 |

**根因**: concise 模式的 extraction prompt 要求 LLM 做日期算术（"相对 session 日期计算绝对日期"），但 LLM 的算术不准确。所有错误案例的 session 日期（mentioned_at）都是正确的参考点，只是 LLM 从这个参考点做减法时出错。

**修复方案**: post-extraction date_validation 模块使用 dateparser（确定性日期解析库）独立计算，在 38 个 facts 上验证成功修正。

### 4.3 Cat 3 多跳推理（65.6%）— 模型能力天花板

33 个错题中 **11 个是 A1**（证据在但 LLM 说「无信息」）。

这些题需要推理而非直接查找:

| 问题 | 正确答案 | 推理链 |
|------|---------|--------|
| "Jolene 多大?" | "不超过 30" | 从 "她在上学" 推断年龄 |
| "James 孤独吗?" | "是的" | 从 "只有猫迎接他" 推断心理状态 |
| "为什么 Jolene 不做瑜伽?" | "更喜欢打游戏" | 从活动偏好推断原因 |
| "Melanie 还会去 roadtrip 吗?" | "可能不会" | 从 "这次很糟糕" 推断意愿 |

**根因**: MiniMax M2.7 倾向保守回答，面对需要推理的问题选择说 "没有明确信息" 而非做推断。这是模型推理能力的限制，不是记忆体能解决的问题。

### 4.4 Cat 1 单跳事实（91.5%）和 Cat 4 开放描述（92.4%）

这两个类别准确率较高，错误分布分散，无集中模式。Cat 4 的 19 个 A1 错误（LLM 说「无信息」但证据在场）值得关注——这些可能通过优化 answer generation prompt 改善。

---

## 五、按对话分布分析

| 对话 | 准确率 | 正确/总计 | 主要错误类型 |
|------|--------|---------|-------------|
| conv-26 | 88.8% | 135/152 | A2(9) |
| conv-30 | 87.7% | 71/81 | A2(7) |
| conv-41 | 92.1% | 140/152 | A2(7) |
| conv-42 | 86.4% | 172/199 | A2(9) |
| conv-43 | 86.0% | 153/178 | A2(11) |
| conv-44 | 89.4% | 110/123 | A2(6) |
| conv-47 | 90.0% | 135/150 | A2(5) |
| conv-48 | 87.4% | 167/191 | A2(14) |
| conv-49 | 91.0% | 142/156 | B2(7) |
| conv-50 | 93.0% | 147/158 | A2(5) |

10 个对话的准确率范围为 86.0%（conv-43）到 93.0%（conv-50），差异在合理波动范围内（无严重异常值）。

---

## 六、GROUP A 逐题分析

### 6.1 A1: 证据在 top-10，LLM 说「无信息」（37 题）

| 对话 | 类别 | 问题 | 正确答案 | 证据排名 |
|------|------|------|---------|--------|
| conv-48 | Descript | What projects is Jolene planning fo... | developing renewable ener... | #1 |
| conv-48 | Temporal | When did Jolene do yoga at Talkeetn... | on 5 June, 2023... | #1 |
| conv-48 | Descript | What did Jolene and Anna discuss wh... | They realized they inspir... | #1 |
| conv-48 | Single-h | Where did Jolene and her partner fi... | Phuket... | #3 |
| conv-26 | Descript | What precautionary sign did Melanie... | A sign stating that someo... | #1 |
| conv-26 | Multi-ho | Would Melanie go on another roadtri... | Likely no; since this one... | #1 |
| conv-26 | Single-h | What book did Melanie read from Car... | "Becoming Nicole"... | #7 |
| conv-47 | Multi-ho | Why didn't John want to go to Starb... | Possibly because he likes... | #8 |
| conv-47 | Descript | What game was James playing in the ... | Apex Legends... | #7 |
| conv-47 | Multi-ho | Was James feeling lonely before mee... | Most likely yes, because ... | #8 |
| conv-47 | Temporal | When did John spend time with his s... | July 21, 2022... | #1 |
| conv-44 | Multi-ho | Which national park could Audrey an... | Voyageurs National Park... | #1 |
| conv-44 | Temporal | When did Andrew make his dogs a fun... | few days before November ... | #1 |
| conv-44 | Descript | What did Andrew and his GF do on th... | volunteered at a pet shel... | #1 |
| conv-43 | Multi-ho | Which Star Wars-related locations w... | Skellig Michael, Malin He... | #5 |
| conv-43 | Multi-ho | What is a prominent charity organiz... | Good Sports, because they... | #1 |
| conv-43 | Descript | What did John share with the person... | Characters from Harry Pot... | #2 |
| conv-43 | Temporal | Which city was John in before trave... | Seattle... | #8 |
| conv-43 | Multi-ho | Based on Tim's collections, what is... | House of MinaLima... | #3 |
| conv-43 | Multi-ho | What is a Star Wars book that Tim m... | Star Wars: Jedi Apprentic... | #4 |
| conv-43 | Descript | Which basketball team does Tim supp... | The Wolves... | #2 |
| conv-43 | Multi-ho | Which outdoor gear company likely s... | Under Armour... | #5 |
| conv-42 | Descript | What dish did Nate make on 9 Novemb... | Homemade coconut ice crea... | #1 |
| conv-42 | Descript | How did Nate celebrate winning the ... | Taking time off to chill ... | #5 |
| conv-42 | Descript | What did Joanna just finish last Fr... | screenplay... | #1 |
| conv-42 | Descript | What does Nate want to do when he g... | Watch one of Joanna's mov... | #1 |
| conv-42 | Descript | What kind of lighting does Nate's g... | red and purple lighting... | #9 |
| conv-42 | Multi-ho | What alternative career might Nate ... | an animalkeeper at a loca... | #1 |
| conv-50 | Descript | What did Calvin and his friends arr... | regular walks together... | #1 |
| conv-50 | Descript | What hobby did Calvin take up recen... | Photography... | #1 |
| conv-50 | Descript | When did Calvin first get intereste... | at an early age... | #5 |
| conv-50 | Descript | What realization did the nightclub ... | how much music means to h... | #3 |
| conv-41 | Descript | What type of workout class did Mari... | aerial yoga... | #1 |
| conv-41 | Descript | What did Maria plan to do later on ... | have dinner with friends ... | #1 |
| conv-41 | Descript | What did Maria donate to a homeless... | old car... | #3 |
| conv-41 | Multi-ho | What job might Maria pursue in the ... | Shelter coordinator, Coun... | #9 |
| conv-49 | Single-h | What is Sam's persistent problem wi... | His new phone malfunction... | #4 |


### 6.2 A2: 证据在 top-10，LLM 答错（79 题，仅列前 20）

| 对话 | 类别 | 问题 | 正确答案 | LLM 回答 | 证据 |
|------|------|------|---------|---------|-----|
| conv-30 | Descript | What did Gina find for her clo... | The perfect spot for... | On February 1, 2023,... | #1 |
| conv-30 | Descript | What did Jon and Gina compare ... | dancing together and... | Gina compared her en... | #1 |
| conv-30 | Descript | What does Jon tell Gina he won... | quit... | Jon tells Gina he wo... | #5 |
| conv-30 | Temporal | When did Gina go to a dance cl... | 21 July 2023... | July 14, 2023... | #1 |
| conv-30 | Temporal | When did Gina open her online ... | 16 March, 2023... | Gina opened her onli... | #7 |
| conv-30 | Descript | What do the dancers in the pho... | They are performing ... | Jon shared a photo o... | #10 |
| conv-30 | Temporal | When did Jon visit networking ... | 20 June, 2023... | Jon attended network... | #2 |
| conv-48 | Descript | What did Jolene recently play ... | a card game about ca... | Monster Hunter: Worl... | #1 |
| conv-48 | Descript | What did Deb share a photo of,... | a yellow coffee cup ... | A handwritten note f... | #2 |
| conv-48 | Descript | Why did Jolene have to resched... | Jolene already had p... | According to the con... | #1 |
| conv-48 | Descript | What activity did Jolene and h... | play the console... | camping trip... | #4 |
| conv-48 | Temporal | When did Jolene have a mini-re... | Wednesday before 9 F... | Jolene had a mini re... | #1 |
| conv-48 | Descript | What do Deborah and her husban... | play detective games... | Deborah and her husb... | #1 |
| conv-48 | Descript | What activity does Deborah inc... | spending time with l... | Deborah incorporates... | #4 |
| conv-48 | Descript | Which new yoga pose did Debora... | tree pose... | Dancer Pose (Nataraj... | #2 |
| conv-48 | Temporal | When did Deborah go to a commu... | last week of August ... | Friday, September 1,... | #1 |
| conv-48 | Multi-ho | Why did Jolene sometimes put o... | She's more intereste... | Jolene sometimes put... | #9 |
| conv-48 | Temporal | When did Deborah meet Anna?... | 31 January, 2023... | Deborah met Anna on ... | #1 |
| conv-48 | Descript | According to Jolene, what does... | connected to her bod... | According to Jolene,... | #1 |
| conv-48 | Temporal | When do Jolene and her partner... | Saturday after 27 Ja... | Saturday, February 4... | #1 |
| ... | ... | *余 59 题* | ... | ... | ... |


---

## 七、GROUP B 逐题分析（24 题）

| 对话 | 类别 | 问题 | 正确答案 | 证据排名 | LLM 行为 |
|------|------|------|---------|--------|--------|
| conv-30 | Single-h | What Jon thinks the ideal danc... | By the water, with nat... | #13 | 答错 |
| conv-48 | Multi-ho | How old is Jolene?... | likely no more than 30... | #20 | 说无信息 |
| conv-48 | Descript | What games does Jolene recomme... | Zelda BOTW for Switch ... | #16 | 答错 |
| conv-48 | Descript | What game did Jolene recommend... | Animal Crossing: New H... | #11 | 说无信息 |
| conv-48 | Descript | What did Jolene participate in... | presenting at a virtua... | #24 | 答错 |
| conv-26 | Descript | What do sunflowers represent a... | warmth and happiness... | #13 | 说无信息 |
| conv-26 | Temporal | When did Melanie read the book... | 2022... | #29 | 说无信息 |
| conv-47 | Temporal | How long did James and Samanth... | nearly three months... | #11 | 答错 |
| conv-44 | Temporal | When did Audrey make muffins f... | The week of April 3rd ... | #12 | 说无信息 |
| conv-44 | Single-h | How many times did Audrey and ... | three times... | #25 | 答错 |
| conv-44 | Descript | What did Audrey share to show ... | photography of a baske... | #80 | 答错 |
| conv-43 | Multi-ho | What other exercises can help ... | Sprinting, long-distan... | #109 | 答错 |
| conv-43 | Descript | Which book did Tim recommend t... | "A Dance with Dragons"... | #86 | 答错 |
| conv-42 | Single-h | How many of Joanna's writing h... | two... | #60 | 答错 |
| conv-42 | Descript | What is Nate's favorite video ... | Xenoblade Chronicles... | #14 | 答错 |
| conv-42 | Descript | What does Nate feel he could d... | write a whole movie... | #12 | 答错 |
| conv-50 | Temporal | How long was the car modificat... | two weeks... | #109 | 说无信息 |
| conv-49 | Descript | What electronics issue has bee... | malfunctioning navigat... | #11 | 答错 |
| conv-49 | Descript | Why had Evan been going throug... | Lost their job due to ... | #14 | 答错 |
| conv-49 | Multi-ho | How often does Sam get health ... | every three months... | #44 | 答错 |
| conv-49 | Single-h | How many roadtrips did Evan ta... | two... | #51 | 答错 |
| conv-49 | Descript | What did Evan start painting y... | forest scene... | #57 | 答错 |
| conv-49 | Descript | What type of landscapes does E... | sunsets over the ocean... | #31 | 答错 |
| conv-49 | Descript | What food did Sam share a phot... | bowl of spinach, avoca... | #12 | 答错 |


---

## 八、GROUP C 逐题分析（28 题）

### 8.1 C1: 真正的提取缺失（7 题）

- **conv-48**: How long did Jolene work on the robotics project g... -> 正确: four months
- **conv-47**: What are John's suspected health problems?... -> 正确: Obesity
- **conv-47**: How was John feeling on April 10, 2022?... -> 正确: seeking solitude
- **conv-44**: Which US state do Audrey and Andrew potentially li... -> 正确: Minnesota
- **conv-43**: After how many weeks did Tim reconnect with the fe... -> 正确: three weeks
- **conv-43**: What sports does John like besides basketball?... -> 正确: surfing
- **conv-42**: What state did Joanna visit in summer 2021?... -> 正确: Indiana


### 8.2 C2: 提取遗漏 + LLM 编造（18 题）

- **conv-30**: What did Gina make a limited edition lin... -> 正确: Hoodies / LLM: Gina created a limited
- **conv-30**: How long did it take for Jon to open his... -> 正确: six months / LLM: It took approximately 
- **conv-48**: Which US state did Jolene visit during h... -> 正确: Alaska / LLM: No US state visit is m
- **conv-26**: What items has Melanie bought?... -> 正确: Figurines, shoes / LLM: Based on the memories 
- **conv-26**: Did Melanie make the black and white bow... -> 正确: Yes / LLM: No, Melanie did not ma
- **conv-47**: Did John and James study together?... -> 正确: Yes / LLM: No, John and James hav
- **conv-47**: How does James plan to make his dog-sitt... -> 正确: By allowing users to c / LLM: James planned to devel
- **conv-47**: What is the board game where you have to... -> 正确: Mafia / LLM: John doesn't explicitl
- **conv-43**: What map does Tim show to his friend Joh... -> 正确: a map of Middle-earth  / LLM: Tim does not show John
- **conv-42**: How many letters has Joanna recieved?... -> 正确: Two / LLM: 1
- **conv-42**: What underlying condition might Joanna h... -> 正确: asthma / LLM: An autoimmune disorder
- **conv-42**: How many video game tournaments has Nate... -> 正确: nine / LLM: 11 tournaments
- **conv-42**: How many times has Nate taken his turtle... -> 正确: Twice. / LLM: At least once - on Oct
- **conv-42**: How many times has Joanna found new hiki... -> 正确: twice / LLM: Joanna has found new h
- **conv-42**: How long did it take for Joanna to finis... -> 正确: four months / LLM: Based on the memories,
- **conv-42**: What is Nate's favorite book series abou... -> 正确: dragons / LLM: Nate has recommended t
- **conv-50**: How long did Dave's work on the Ford Mus... -> 正确: nearly two months / LLM: Dave's work on the For
- **conv-41**: What might John's financial status be?... -> 正确: Middle-class or wealth / LLM: John's financial statu


**C2 根因分类**:

| 子根因 | 数量（估） | 描述 | 典型案例 |
|--------|----------|------|---------|
| 概括化 | ~10 | 原文具体名词被泛化 | "hoodie" -> "clothing line" |
| 完全遗漏 | ~4 | 原文有但 fact 中完全没提 | "mount Talkeetna" 未提取 |
| 世界知识 | ~3 | 正确答案需要外部知识 | Talkeetna -> Alaska |

---

## 九、改善天花板与已实施方案

### 9.1 理论天花板

| 根因 | 题数 | 天花板 | 当前状态 |
|------|------|--------|---------|
| 答题环节（A1+A2）| 116 | +7.5pp | 需 answer prompt 优化或更强 LLM |
| 检索排序（B）| 24 | +1.6pp | 可通过提高 max_tokens 缓解 |
| 提取遗漏（C）| 28 | +1.8pp | post-extraction enrichment 已实施 |

### 9.2 已实施: post-extraction enrichment

| 模块 | 检查 facts | 修正数 | 目标错题 |
|------|-----------|--------|---------|
| date_validation | 102 个含相对日期 | 38 修正 | Cat 2 的 34 个日期错误 |
| detail_preservation | 149 个含通用词 | 80 恢复 | C2 的 17 个提取遗漏 |

**验证的修复案例**:

| 错题 | 原始 fact | 修正后 | 状态 |
|------|----------|--------|------|
| "limited edition of?" -> Hoodies | "clothing line" | "clothing line (specifically: Hoodie)" | 细节恢复 |
| "dance class when?" -> July 21 | occurred: July 14 | occurred: July 21 | 日期修正 |
| "games for Deborah?" -> Zelda | "video games" | "video games (specifically: Zelda, Animal Crossing)" | 细节恢复 |
| "mini retreat when?" -> Feb 8 | occurred: Feb 1 | occurred: Feb 8 | 日期修正 |
| "yoga at Talkeetna?" | "beautiful location" | "location (specifically: Talkeetna)" | 细节恢复 |

---

## 十、下一步行动建议

| 优先级 | 方向 | 预期收益 | 工作量 | 依赖 |
|--------|------|---------|--------|------|
| P0 | 开启 enrichment 重新 ingest + eval 验证 | +1-2pp | 4-5h（ingest 时间） | MiniMax API 稳定 |
| P1 | 扩展 detail_preservation 词典 | +0.3-0.5pp | 0.5 天 | 分析更多 C2 案例 |
| P2 | 提高 max_tokens（4096 -> 8192） | +0.5-1pp | 配置调整 | 验证 LLM 上下文能力 |
| P3 | 更换/增强 LLM（answer generation）| +2-4pp | 依赖模型 | 需要可用的更强模型 |
| P4 | Agentic 多轮检索（Cat 3 推理）| +1-2pp | 1-2 周 | 架构改造 |

**最高 ROI**: P0 — 已实施的 enrichment 模块在 38 个日期 + 80 个细节上验证有效，只需重新 ingest 即可验证端到端效果。
