# arXiv Paper Bot - 精简文档

> 拉取 arXiv 最新论文 → 关键词评分 → （可选）LLM 摘要 → 保存/推送 → 收集反馈

## 流程一览
1. 读取配置与日志（`main.py`、`config/config.yaml`）。
2. 抓取：`ArxivFetcher.fetch_latest_papers(days)` 按 `fetch_mode` 执行：`category_only` / `keyword_only` / `combined` / `category_then_filter`。`search_keywords` 用于 API 查询，`fetch_full_categories` 为 True 时再拉整类并去重，只保留最近 `days` 天、遵循 `max_results` 与排序。
3. 过滤：`PaperFilter` 在标题+摘要整词匹配关键词（高/中/低权重 3.0/2.0/1.0），过滤掉 `score < min_score`，按分数排序后取 `top_k`，同时输出 `top_keywords` 统计。
4. 摘要（可选）：`PaperSummarizer` 通过 OpenAI 兼容接口生成字段（默认 `one_sentence_highlight`、`core_method` 等），由 `provider/model/base_url/api_key_env` 决定。
5. 存储：`PaperStorage` 输出 JSON/CSV，`append_mode` 下先读旧文件并按 `arxiv_id` 去重。
6. 推送（可选）：`build_notifier` 构建 Feishu / Telegram / WeChat 推送，发送前 `top_k` 条文本 digest。
7. 反馈：`feedback.py` CLI 调 `FeedbackCollector` 记录 like/dislike 至 `data/feedback/*`，生成偏好关键词与统计。

## 快速开始
```bash
pip install -r requirements.txt
python main.py --config config/config.yaml --days 1
cat data/papers.json | head
```
可选：
```bash
python feedback.py like <paper_id>
python feedback.py stats
```

## 配置速查（config/config.yaml）
- `arxiv`: `categories`, `max_results`, `fetch_mode`, `search_keywords`, `fetch_full_categories`, `sort_by`, `sort_order`
- `filter`: `keywords` (high/medium/low), `min_score`, `top_k`, `enabled`
- `summarization`: `enabled`, `provider`, `api.base_url`, `api.model`, `api_key_env`, `fields`
- `storage`: `format`, `json_path`, `csv_path`, `append_mode`
- `notification`: `enabled`, `provider`, `top_k`, 渠道凭据（feishu/telegram/wechat）
- `personalization`: 预留接口（向量/agent），默认关闭
- `logging`: `level`, `log_file`, `console_output`

## 模块对照
- `main.py`: 串联全流程；CLI 参数 `--config`、`--days`、`--test`
- `src/fetcher.py`: arXiv 抓取与去重
- `src/filter.py`: 关键词评分与统计
- `src/summarizer.py`: LLM 摘要
- `src/storage.py`: JSON/CSV 保存与加载
- `src/notifier.py`: 飞书/Telegram/微信推送
- `src/feedback.py` + `feedback.py`: 反馈记录与统计 CLI
- `src/personalization.py`: 个性化排序/意图识别占位

## 常用命令
```bash
python main.py --days 7                 # 最近 7 天
python main.py --test                   # 测试模式（减少抓取量）
python feedback.py list liked --verbose # 查看反馈
python run_tests.py                     # 运行单测
```

## 常见问题
- 抓不到论文：增大 `--days`，或降低 `filter.min_score`，检查 `search_keywords` 是否过窄。
- 推送失败：确认 provider 对应凭据齐全；Feishu 需 webhook（如启用签名则填 secret），WeChat 需 app_id/app_secret/open_id。
- 摘要报错：确保 `summarization.enabled=true` 且 `api_key_env`/`api_key` 生效，网络可访问 `base_url`。
