# arXiv Paper Bot 设计文档（草案）

目标：实现“当天全量检索 → 元信息补全/结构化 → 基于 meta 的关键词筛选 → LangGraph 二次筛选/重排 → 保存/推送/反馈闭环”的可落地流水线，并满足 **敏感信息不落盘/不出日志** 的约束。

## 1. 背景与需求

你希望的前置流程是：
1) 检索“当天所有论文”（通常可理解为：当天在你关注的“类别集合”里的全量新提交/更新）
2) 补全所有 meta 信息（对齐字段、规范化、派生结构化 meta）
3) 基于 meta 信息筛选相关关键词（用于第一阶段快速过滤与降噪）
4) 再用 LangGraph 做二次筛选（LLM/Agent 重排、解释、必要时迭代）

约束：
- webhook / OpenRouter key 等敏感信息可以从本地路径读取，但 **任何输出/日志/落盘都不能包含明文**。

## 2. 当前项目现状（可复用资产）

已具备：
- arXiv 抓取：`src/fetcher.py`（按 category/keyword/combined 抓取，含去重）
- 关键词过滤：`src/filter.py`（标题+摘要整词匹配，加权计分）
- LangGraph 代理筛选（基础）：`src/agents/*` + `src/integration/agent_filter.py`
- 存储与推送：`src/storage.py`、`src/notifier.py`
- 反馈：`src/feedback.py` + `feedback.py`
- 敏感信息解析（新增）：`src/secrets.py`（支持 env / file）
  - 飞书 webhook 支持 `webhook_file`：`src/notifier.py`
  - Agent 支持 `api_key_file`：`src/agents/config.py`

现阶段缺口（围绕你的新流程）：
- “当天全量”抓取策略与持久化索引（raw index）
- “meta 补全/结构化”模块（规则/LLM 可选）
- “基于 meta 的关键词筛选”策略（不仅仅 title+abstract）
- LangGraph 二次筛选：从“只是重排”升级为“基于结构化 meta + 解释/校验 + 可迭代”

## 3. 总体架构（推荐）

建议拆成 2 层编排：

1) **外层：日更流水线（Pipeline Graph）**  
   负责：抓取当天全集 → meta 补全 → 基于 meta 的关键词过滤 → 调用二次 Agent Graph → 落盘 → 推送。

2) **内层：二次筛选/重排（Agent Graph）**  
   负责：针对已降噪后的候选集，做 LLM/规则混合打分、解释、校验、必要时迭代。

关键原则：
- 外层图负责“数据准备 + 降噪”，内层图负责“高精度排序 + 解释”。
- **secret 只在节点内部 resolve**（env/file），state 里只放 “env 名称/路径/开关”，禁止放明文。

## 4. 数据与存储设计

### 4.1 数据对象

建议引入“原始记录 + 富化记录”的概念（不一定要改 `Paper` dataclass，先以 dict/sidecar 形式落地）：

- RawPaper（抓取后）：
  - arXiv 原生字段：`arxiv_id/title/abstract/authors/categories/primary_category/published/updated/comment/journal_ref/doi/pdf_url/entry_url`

- EnrichedPaper（meta 补全后）：
  - `raw`：保留 RawPaper
  - `meta`：结构化派生字段（规则/LLM）
    - 例：`has_code`、`has_dataset`、`tasks`、`modalities`、`methods`、`datasets`、`institutions`（可选）
  - `keyword_stage`：基于 meta 的第一阶段打分/命中详情
    - 例：`matched_keywords_meta`、`meta_score`
  - `agent_stage`：二次筛选输出
    - 例：`agent_score/combined_score/explanations`

### 4.2 落盘布局（建议）

- `data/index/YYYY-MM-DD/raw.jsonl`：当天全量 raw 记录（jsonl 便于增量写入）
- `data/index/YYYY-MM-DD/enriched.jsonl`：富化后的记录（可重跑覆盖）
- `data/papers.json` / `data/papers.csv`：最终推荐结果（现有）
- `data/feedback/*`：反馈（现有）

说明：
- 任何落盘文件都不得包含 webhook / api key 明文。
- 对“当天全量”强烈建议独立存储，避免 `data/papers.json` 被 append 混入历史而难以追踪。

## 5. 当天全量抓取策略

现实约束：arXiv 全站“当天所有论文”量很大，通常建议定义 **“当天 + 类别集合”** 的全量。

建议：
- 配置 `arxiv.categories_universe`（你要关注的类别集合）
- 抓取方式：对每个 category 拉取 `submittedDate` 最新，取足够大的 `max_results`，然后按“当天窗口”过滤（UTC 或指定时区）

当天窗口定义（需配置）：
- `day_window.timezone`：默认 `Asia/Shanghai`
- `day_window.mode`：
  - `calendar_day`：按 00:00~23:59（更符合“当天”直觉）
  - `rolling_24h`：按 now-24h（实现简单）

实现点：
- fetcher 保留“粗召回”能力：拉到足够多后本地按时间截断。
- 去重策略建议基于 “base arxiv_id（去掉 v1/v2）+ entry_url” 做稳定 dedupe（后续可做）。

## 6. Meta 补全/结构化（关键新增）

目标：让后续“关键词筛选”不只依赖 title/abstract，而是利用更丰富的 meta 信号。

分两档（可配置开关）：

### 6.1 规则补全（默认开启，成本低）
- 字段规范化：作者列表、分类、日期、arxiv_id 版本、url 校验等
- 派生 meta（regex/词表）：
  - `has_code`: comment/abstract 是否包含 "code", "github", "released"
  - `has_dataset`: 是否包含 "dataset", "benchmark"
  - `tasks/methods`: 基于可维护词表（如 transformer/diffusion/rl/segmentation…）
  - `modalities`: vision/language/audio/multimodal

### 6.2 LLM 补全（可选，成本高）
输入：title + abstract + comment + categories（限制长度）  
输出：结构化 JSON（tasks/methods/datasets/novelty/quality flags…）

注意：
- LLM 只处理第一阶段过滤后的子集，或对全量做“轻量模型 + topN”。
- LLM key 通过 `api_key_env`/`api_key_file` resolve，禁止写回 state/落盘。

## 7. 基于 meta 的关键词筛选（第一阶段）

目标：从“当天全量”快速筛出“可能相关”的候选集合，控制进入 LangGraph 的规模（例如 50~300）。

策略建议（可组合）：
- Text fields 扩展：匹配文本从 `title+abstract` 扩展到 `comment/categories/primary_category` 等
- Meta-aware weighting：
  - title 命中权重高
  - abstract 次之
  - comment/categories 命中较低，但可作为加成或硬过滤
- 分类 gating（硬规则）：仅保留目标 primary_category / cross-list 白名单
- 规则特征 gating（可选）：比如必须 `has_code=true` 才保留

输出：
- `meta_score`、`matched_keywords_meta`、`gating_reasons`

## 8. LangGraph 二次筛选（第二阶段）

目标：对第一阶段候选集做更高精度的筛选、重排与解释。

建议将“二次筛选”建模为一个 LangGraph：

### 8.1 Agent Graph（推荐形态）

```
START
  -> build_interest_profile        (config keywords + 反馈 + 画像；已有 build_profile_node)
  -> enrich_keywords_optional      (LLM: 从候选集 meta 里扩展/收缩关键词；可复用 query_gen 思路)
  -> score_candidates              (规则分 + LLM 分融合；可复用 score_papers_node 并扩展)
  -> validate_and_explain          (LLM: 输出 top explanations + optional reorder；已有 validation_node)
  -> END
```

可选迭代：
- 若 `validate` 输出 `should_rerank=true`，回到 `score_candidates`（已有框架支持 iteration）

注意点：
- 这里的“LLM 调用”建议只针对 topN（如 30~80）做，避免成本与限流。
- OpenRouter 调用需要 `base_url=https://openrouter.ai/api/v1` 且 headers 带 `HTTP-Referer/X-Title`（已在节点里处理）。

### 8.2 输出
- `combined_score`（最终排序依据）
- `explanations`（paper_id -> reason）
- 可选：`detected_interests`、`avoid_topics`、`confidence`

## 9. 配置与敏感信息管理

### 9.1 配置建议（只放路径/ENV，不放明文）

- webhook（飞书）：
  - `notification.feishu.webhook_file: /path/to/webhook.txt`
- OpenRouter key：
  - `personalization.agent.api.api_key_file: /path/to/openrouter_key.txt`（建议新建）
  - 或继续使用 `api_key_env: OPENROUTER_API_KEY`

### 9.2 安全约束落地
- 任何日志都只能打印 masked 信息（如必要）
- LangGraph state 禁止塞明文 secret；只塞 env 名称/路径
- checkpointer 若从 `MemorySaver` 升级为持久化（SQLite/Redis），必须先做 state “脱敏/不携带 secret”

## 10. 错误处理与降级策略

建议的降级顺序：
1) LLM/Agent 失败（网络/限流/解析失败）→ 直接输出第一阶段（meta 关键词筛选）结果
2) meta LLM 补全失败 → 回退到规则 meta
3) 抓取失败/为空 → 写空结果 + 不推送（或推送“今日暂无”）

## 11. 实施计划（建议分期）

Phase 1（最小可用）：
- 当天全量抓取（按 categories_universe）
- 规则 meta 补全
- meta-aware 关键词过滤（扩展 fields + gating）
- LangGraph 二次筛选：复用现有 cold-start agent graph（score + validate）
- raw/enriched/最终结果落盘

Phase 2（增强）：
- LLM meta 补全（仅对候选集）
- keyword_enrichment 节点（LLM 扩展关键词）
- 二次筛选支持可迭代 rerank

Phase 3（闭环）：
- 将反馈/点击/阅读时长等写入 profile
- 用历史反馈驱动 query generation（用于第二天的检索策略优化）

## 12. 测试策略

- 单元测试：
  - meta 规则补全：输入/输出稳定
  - meta 关键词计分：字段覆盖（title/abstract/comment/categories）
  - secret resolver：只验证“能读到值”，不打印值（已加 `tests/test_secrets.py`）
- 集成测试：
  - Mock arxiv results → 跑完整 pipeline graph
  - Mock LLM（patch ChatOpenAI.invoke）→ 验证 rerank/解释解析与降级
