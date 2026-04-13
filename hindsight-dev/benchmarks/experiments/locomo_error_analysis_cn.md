# LoCoMo 89.1% 基线 — 168 个错题深度分析报告

> 基线: `locomo_minimax_m27_eval_baseline.json`（MiniMax M2.7, 1372/1540 正确, 89.1%）
> 分析日期: 2026-04-12
> 分析对象: 168 个错误答案

---

## 一、分析方法论

对每个错题执行以下验证链:

1. 从正确答案（gold answer）提取关键词（≥3 字符，过滤英文停用词）
2. 在该题**全部**检索到的记忆中搜索关键词（不限于 top-10，而是全部 100+ 条）
3. 确定证据位置: **top-10 内** / **top-10 外** / **完全不存在**
4. 结合 LLM 的实际回答（predicted_answer）和评审理由（correctness_reasoning）分类失败模式
5. 与 LoCoMo 4 个题目类别交叉分析

这套方法能精确区分「记忆体的问题」和「LLM 的问题」。

---

## 二、三大失败分组

```
168 个错题
│
├── GROUP A: 证据在 top-10，LLM 仍答错 ─── 116 题（69%）
│   ├── A1: LLM 说「没有相关信息」── 37 题
│   │   证据就在 #1-10 位，LLM 扫了 100+ 条 fact 却说找不到
│   └── A2: LLM 给了错误答案 ────── 79 题
│       证据在场，但 LLM 选了旁边的错误 fact 或提取了错误细节
│
├── GROUP B: 证据在记忆库但排在 top-10 外 ─ 24 题（14%）
│   ├── B1: LLM 说「没有相关信息」── 6 题
│   └── B2: LLM 给了错误答案 ────── 18 题
│
└── GROUP C: 证据不在任何记忆中 ────────── 28 题（17%）
    ├── C0: 答案过短无法检测 ─────── 3 题
    ├── C1: LLM 正确表示无信息 ──── 7 题（真正的提取缺失）
    └── C2: LLM 编造了答案 ─────── 18 题（hallucination）
```

**核心结论**: **69% 的错误（GROUP A）不是记忆体检索的问题——证据已经排在 top-10 送到了 LLM 面前，是 LLM 没有正确使用。**

---

## 三、GROUP A 详细分析（116 题）

### A1: 证据在 top-10，LLM 却说「无信息」（37 题）

| 对话 | 类别 | 问题 | 正确答案 | 证据排名 |
|------|------|------|---------|--------|
| conv-48 | Descript | What projects is Jolene planning for nex... | developing renewable energy fi... | #1 |
| conv-48 | Temporal | When did Jolene do yoga at Talkeetna?... | on 5 June, 2023... | #1 |
| conv-48 | Descript | What did Jolene and Anna discuss while w... | They realized they inspire eac... | #1 |
| conv-48 | Single-h | Where did Jolene and her partner find a ... | Phuket... | #3 |
| conv-26 | Descript | What precautionary sign did Melanie see ... | A sign stating that someone is... | #1 |
| conv-26 | Multi-ho | Would Melanie go on another roadtrip soo... | Likely no; since this one went... | #1 |
| conv-26 | Single-h | What book did Melanie read from Caroline... | "Becoming Nicole"... | #7 |
| conv-47 | Multi-ho | Why didn't John want to go to Starbucks?... | Possibly because he likes to d... | #8 |
| conv-47 | Descript | What game was James playing in the onlin... | Apex Legends... | #7 |
| conv-47 | Multi-ho | Was James feeling lonely before meeting ... | Most likely yes, because he me... | #8 |
| conv-47 | Temporal | When did John spend time with his sister... | July 21, 2022... | #1 |
| conv-44 | Multi-ho | Which national park could Audrey and And... | Voyageurs National Park... | #1 |
| conv-44 | Temporal | When did Andrew make his dogs a fun indo... | few days before November 22, 2... | #1 |
| conv-44 | Descript | What did Andrew and his GF do on the Mon... | volunteered at a pet shelter... | #1 |
| conv-43 | Multi-ho | Which Star Wars-related locations would ... | Skellig Michael, Malin Head, L... | #5 |
| conv-43 | Multi-ho | What is a prominent charity organization... | Good Sports, because they work... | #1 |
| conv-43 | Descript | What did John share with the person he s... | Characters from Harry Potter... | #2 |
| conv-43 | Temporal | Which city was John in before traveling ... | Seattle... | #8 |
| conv-43 | Multi-ho | Based on Tim's collections, what is a sh... | House of MinaLima... | #3 |
| conv-43 | Multi-ho | What is a Star Wars book that Tim might ... | Star Wars: Jedi Apprentice by ... | #4 |
| conv-43 | Descript | Which basketball team does Tim support?... | The Wolves... | #2 |
| conv-43 | Multi-ho | Which outdoor gear company likely signed... | Under Armour... | #5 |
| conv-42 | Descript | What dish did Nate make on 9 November, 2... | Homemade coconut ice cream... | #1 |
| conv-42 | Descript | How did Nate celebrate winning the inter... | Taking time off to chill with ... | #5 |
| conv-42 | Descript | What did Joanna just finish last Friday ... | screenplay... | #1 |
| conv-42 | Descript | What does Nate want to do when he goes o... | Watch one of Joanna's movies t... | #1 |
| conv-42 | Descript | What kind of lighting does Nate's gaming... | red and purple lighting... | #9 |
| conv-42 | Multi-ho | What alternative career might Nate consi... | an animalkeeper at a localzoo ... | #1 |
| conv-50 | Descript | What did Calvin and his friends arrange ... | regular walks together... | #1 |
| conv-50 | Descript | What hobby did Calvin take up recently?... | Photography... | #1 |
| conv-50 | Descript | When did Calvin first get interested in ... | at an early age... | #5 |
| conv-50 | Descript | What realization did the nightclub exper... | how much music means to him, i... | #3 |
| conv-41 | Descript | What type of workout class did Maria sta... | aerial yoga... | #1 |
| conv-41 | Descript | What did Maria plan to do later on the e... | have dinner with friends from ... | #1 |
| conv-41 | Descript | What did Maria donate to a homeless shel... | old car... | #3 |
| conv-41 | Multi-ho | What job might Maria pursue in the futur... | Shelter coordinator, Counselor... | #9 |
| conv-49 | Single-h | What is Sam's persistent problem with hi... | His new phone malfunctioning, ... | #4 |

**A1 典型案例**:

1. **conv-48**: 证据 #1 提到 "renewable energy"，LLM 回答 "no explicit information about projects"
2. **conv-48**: 证据 #1 有 Talkeetna 的日期，LLM 说 "no information about Talkeetna"
3. **conv-48**: 证据 #1 描述了 sunset 场景，LLM 说 "no record of watching sunset"

**根因分析**: MiniMax M2.7 面对 100+ 条 facts 的 JSON 上下文时，无法有效关联查询中的关键词与 fact 文本中的描述。尤其在 Cat 3（多跳推理）中 11 题属于此类——这些题需要推理（如从 "她在上学" 推断 "不超过 30 岁"），但模型保守地选择了 "没有明确信息"。

### A2: 证据在 top-10，LLM 给了错误答案（79 题）

| 对话 | 类别 | 问题 | 正确答案 | LLM 回答 | 证据排名 |
|------|------|------|---------|---------|--------|
| conv-30 | Descript | What did Gina find for her clothing... | The perfect spot for h... | On February 1, 2023, G... | #1 |
| conv-30 | Descript | What did Jon and Gina compare their... | dancing together and s... | Gina compared her entr... | #1 |
| conv-30 | Descript | What does Jon tell Gina he won't do... | quit... | Jon tells Gina he won'... | #5 |
| conv-30 | Temporal | When did Gina go to a dance class w... | 21 July 2023... | July 14, 2023... | #1 |
| conv-30 | Temporal | When did Gina open her online cloth... | 16 March, 2023... | Gina opened her online... | #7 |
| conv-30 | Descript | What do the dancers in the photo re... | They are performing at... | Jon shared a photo of ... | #10 |
| conv-30 | Temporal | When did Jon visit networking event... | 20 June, 2023... | Jon attended networkin... | #2 |
| conv-48 | Descript | What did Jolene recently play that ... | a card game about cats... | Monster Hunter: World... | #1 |
| conv-48 | Descript | What did Deb share a photo of, whic... | a yellow coffee cup wi... | A handwritten note fro... | #2 |
| conv-48 | Descript | Why did Jolene have to reschedule t... | Jolene already had pla... | According to the conve... | #1 |
| conv-48 | Descript | What activity did Jolene and her pa... | play the console... | camping trip... | #4 |
| conv-48 | Temporal | When did Jolene have a mini-retreat... | Wednesday before 9 Feb... | Jolene had a mini retr... | #1 |
| conv-48 | Descript | What do Deborah and her husband do ... | play detective games t... | Deborah and her husban... | #1 |
| conv-48 | Descript | What activity does Deborah incorpor... | spending time with lov... | Deborah incorporates m... | #4 |
| conv-48 | Descript | Which new yoga pose did Deborah sha... | tree pose... | Dancer Pose (Natarajas... | #2 |
| ... | ... | *余 64 题省略* | ... | ... | ... |

**A2 细分模式**:

| 子模式 | 数量 | 描述 | 典型例子 |
|--------|------|------|---------|
| 日期差 1-2 天/周 | ~34 | 证据有正确事件但日期计算错误 | "July 21" → LLM 答 "July 14"（差 1 周）|
| 选错 fact | ~20 | 多条相似 fact 竞争，选了错的 | 正确 "Chicken Pot Pie"，LLM 选了 "Mediterranean chicken" |
| 精度不足 | ~15 | 答案方向对但不够精确 | 正确 "quit"，LLM 答 "won't let anything hold him back" |
| judge 严格 | ~9 | LLM 答案可接受但 judge 判错 | 正确 "companions and family"，LLM 答 "companions"（少了 family） |

---

## 四、GROUP B 详细分析（24 题）

证据被正确提取到记忆库，但检索排序不够高（rank 11-51），LLM 在 top-10 中看不到。

| 对话 | 类别 | 问题 | 正确答案 | 证据实际排名 |
|------|------|------|---------|------------|
| conv-30 | Single-h | What Jon thinks the ideal dance studio s... | By the water, with natural l... | #13 |
| conv-48 | Multi-ho | How old is Jolene?... | likely no more than 30; sinc... | #20 |
| conv-48 | Descript | What games does Jolene recommend for Deb... | Zelda BOTW for Switch , Anim... | #16 |
| conv-48 | Descript | What game did Jolene recommend for being... | Animal Crossing: New Horizon... | #11 |
| conv-48 | Descript | What did Jolene participate in recently ... | presenting at a virtual conf... | #24 |
| conv-26 | Descript | What do sunflowers represent according t... | warmth and happiness... | #13 |
| conv-26 | Temporal | When did Melanie read the book "nothing ... | 2022... | #29 |
| conv-47 | Temporal | How long did James and Samantha date for... | nearly three months... | #11 |
| conv-44 | Temporal | When did Audrey make muffins for herself... | The week of April 3rd to 9th... | #12 |
| conv-44 | Single-h | How many times did Audrey and Andew plan... | three times... | #25 |
| conv-44 | Descript | What did Audrey share to show ways to ke... | photography of a basket full... | #80 |
| conv-43 | Multi-ho | What other exercises can help John with ... | Sprinting, long-distance run... | #109 |
| conv-43 | Descript | Which book did Tim recommend to John as ... | "A Dance with Dragons"... | #86 |
| conv-42 | Single-h | How many of Joanna's writing have made i... | two... | #60 |
| conv-42 | Descript | What is Nate's favorite video game?... | Xenoblade Chronicles... | #14 |
| conv-42 | Descript | What does Nate feel he could do when out... | write a whole movie... | #12 |
| conv-50 | Temporal | How long was the car modification worksh... | two weeks... | #109 |
| conv-49 | Descript | What electronics issue has been frustrat... | malfunctioning navigation ap... | #11 |
| conv-49 | Descript | Why had Evan been going through a tough ... | Lost their job due to downsi... | #14 |
| conv-49 | Multi-ho | How often does Sam get health checkups?... | every three months... | #44 |
| conv-49 | Single-h | How many roadtrips did Evan take in May ... | two... | #51 |
| conv-49 | Descript | What did Evan start painting years ago d... | forest scene... | #57 |
| conv-49 | Descript | What type of landscapes does Evan love p... | sunsets over the ocean... | #31 |
| conv-49 | Descript | What food did Sam share a photo of on 19... | bowl of spinach, avocado, an... | #12 |

**改善路径**: 扩大 max_tokens（从 4096 到 16384）可让更多 facts 进入 LLM 视野。
实验数据: conv-48 在 max_tokens=16384 时从 87.4% 提升到 89.0%（+1.6pp）。

---

## 五、GROUP C 详细分析（28 题）

### C1: 真正的提取缺失（7 题）

这些信息确实不在记忆库中，LLM 正确判断为无信息。

- **conv-48**: Q: How long did Jolene work on the robotics project g... → 正确: four months
- **conv-47**: Q: What are John's suspected health problems?... → 正确: Obesity
- **conv-47**: Q: How was John feeling on April 10, 2022?... → 正确: seeking solitude
- **conv-44**: Q: Which US state do Audrey and Andrew potentially li... → 正确: Minnesota
- **conv-43**: Q: After how many weeks did Tim reconnect with the fe... → 正确: three weeks
- **conv-43**: Q: What sports does John like besides basketball?... → 正确: surfing
- **conv-42**: Q: What state did Joanna visit in summer 2021?... → 正确: Indiana

### C2: LLM 编造答案（18 题）

没有证据，但 LLM 给了一个（错误的）回答，属于 hallucination。

- **conv-30**: Q: What did Gina make a limited edition line of?... → 正确: Hoodies / LLM: Gina created a limited ed
- **conv-30**: Q: How long did it take for Jon to open his stud... → 正确: six months / LLM: It took approximately 5 m
- **conv-48**: Q: Which US state did Jolene visit during her in... → 正确: Alaska / LLM: No US state visit is ment
- **conv-26**: Q: What items has Melanie bought?... → 正确: Figurines, shoes / LLM: Based on the memories pro
- **conv-26**: Q: Did Melanie make the black and white bowl in ... → 正确: Yes / LLM: No, Melanie did not make 
- **conv-47**: Q: Did John and James study together?... → 正确: Yes / LLM: No, John and James have n
- **conv-47**: Q: How does James plan to make his dog-sitting a... → 正确: By allowing users to cust / LLM: James planned to develop 
- **conv-47**: Q: What is the board game where you have to find... → 正确: Mafia / LLM: John doesn't explicitly n
- **conv-43**: Q: What map does Tim show to his friend John?... → 正确: a map of Middle-earth fro / LLM: Tim does not show John a 
- **conv-42**: Q: How many letters has Joanna recieved?... → 正确: Two / LLM: 1
- **conv-42**: Q: What underlying condition might Joanna have b... → 正确: asthma / LLM: An autoimmune disorder or
- **conv-42**: Q: How many video game tournaments has Nate part... → 正确: nine / LLM: 11 tournaments
- **conv-42**: Q: How many times has Nate taken his turtles on ... → 正确: Twice. / LLM: At least once - on Octobe
- **conv-42**: Q: How many times has Joanna found new hiking tr... → 正确: twice / LLM: Joanna has found new hiki
- **conv-42**: Q: How long did it take for Joanna to finish wri... → 正确: four months / LLM: Based on the memories, Jo
- **conv-42**: Q: What is Nate's favorite book series about?... → 正确: dragons / LLM: Nate has recommended two 
- **conv-50**: Q: How long did Dave's work on the Ford Mustang ... → 正确: nearly two months / LLM: Dave's work on the Ford M
- **conv-41**: Q: What might John's financial status be?... → 正确: Middle-class or wealthy / LLM: John's financial status a

**C2 根因**:
- **概括化**（最常见）: 原文 "hoodie" → fact 提取为 "clothing line"，具体名词被泛化
- **遗漏**: 原文 "mount Talkeetna" 完全未提取，地名丢失
- **世界知识**: 正确答案 "Alaska" 需要知道 Talkeetna 在 Alaska（超出记忆范围）
- **数量模糊**: 原文 "three times" → fact 提取时丢了精确数字

---

## 六、按 LoCoMo 类别交叉分析

| 类别 | 总题 | 正确 | 错题 | 准确率 | 与其他系统对比 |
|------|------|------|------|--------|------------|
| Single-hop（单跳事实） | 282 | 258 | 24 | 91.5% | Hindsight 官方 92.0%（整体） |
| Temporal（时间推理） | 321 | 274 | 47 | 85.4% | Hindsight 官方 92.0%（整体） |
| Multi-hop（多跳推理） | 96 | 63 | 33 | 65.6% | Hindsight 官方 92.0%（整体） |
| Descriptive（开放描述） | 841 | 777 | 64 | 92.4% | Hindsight 官方 92.0%（整体） |

### Cat 2（时间推理，85.4%）深度分析

47 个错题中 **34 个是 A2**——证据在 top-10 但日期错误。

典型模式: LLM 在 fact extraction 阶段将 "last Friday" 等相对日期表达转为绝对日期时计算错误。

| 原文表达 | LLM 计算 | 正确日期 | 误差 | session 日期 |
|---------|---------|---------|------|-------------|
| "last Friday" | July 14 | July 21 | -7 天 | July 23 |
| "Last Wednesday" | Feb 1 | Feb 8 | -7 天 | Feb 9 |
| "last Friday" | Oct 13 | Oct 20 | -7 天 | Oct 22 |
| "last weekend" | Jul 8 | Jul 15-16 | -7 天 | Jul 17 |

**模式**: 几乎所有错误都是 **差整整 1 周**，说明 LLM 在计算 "last X" 时系统性地多减了 7 天。

**post-extraction enrichment 验证**: date_validation 模块用 dateparser 交叉验证，在 102 个含相对日期的 facts 中修正了 38 个。

### Cat 3（多跳推理，65.6%）深度分析

33 个错题中 **11 个是 A1**（证据在但 LLM 说无信息）。

这些题需要**推理**而非直接查找:
- "Jolene 多大?" → 需从 "她在上学" 推断 "不超过 30"
- "James 孤独吗?" → 需从 "只有猫迎接他" 推断 "是的"
- "为什么 Jolene 不做瑜伽?" → 需从 "她更喜欢打游戏" 推断

**根因**: MiniMax M2.7 的推理能力限制。不是记忆体能解决的问题，需要更强的 LLM 或 agentic 多轮检索。

---

## 七、改善天花板与 post-extraction enrichment 效果

### 理论天花板

| 根因 | 题数 | 天花板 | 改善路径 |
|------|------|--------|---------|
| 答题环节 A1+A2 | 116 | +7.5pp（89→96.5%） | answer prompt / 更强 LLM |
| 检索排序 B | 24 | +1.6pp | 提高 max_tokens / 优化排序 |
| 提取遗漏 C | 28 | +1.8pp | post-extraction enrichment |
| **合计** | **168** | **+10.9pp（→100%）** | **全部修复** |

### post-extraction enrichment 实际验证

基于 168 个错题的 DB 数据运行 enrichment 模块:

| 模块 | 检查 facts | 修正数 | 说明 |
|------|-----------|--------|------|
| **date_validation** | 102 | **38 修正** | 用 dateparser 交叉验证 "last Friday" 等相对日期 |
| **detail_preservation** | 149 | **80 恢复** | 从 chunk 原文回补 hoodie/Zelda/Talkeetna 等细节 |

**具体修复案例**:

| 错题 | 原始 fact | 修正后 |
|------|----------|--------|
| "limited edition line of?" → Hoodies | "clothing line" | "clothing line (specifically: Hoodie)" |
| "dance class when?" → July 21 | occurred: July 14 | occurred: **July 21** |
| "games for Deborah?" → Zelda etc | "video games" | "video games (specifically: Zelda, Animal Crossing, Botw)" |
| "mini retreat when?" → Feb 8 | occurred: Feb 1 | occurred: **Feb 8** |
| "yoga at Talkeetna?" | "beautiful location" | "location (specifically: Talkeetna)" |

---

## 八、下一步建议

| 优先级 | 方向 | 预期收益 | 当前状态 |
|--------|------|---------|---------|
| **P0** | re-ingest with enrichment 开启 | +1-2pp | enrichment 已实现，待验证 |
| P1 | 扩展 detail_preservation 词典 | +0.5pp | 当前词典覆盖主要类别 |
| P2 | 提高 max_tokens (4096→8192) | +0.5-1pp | 需验证 LLM 处理能力 |
| P3 | 更强 LLM (answer generation) | +2-4pp | 依赖可用模型 |
| P4 | Agentic 多轮检索 (Cat 3) | +1-2pp | 架构改造 |
