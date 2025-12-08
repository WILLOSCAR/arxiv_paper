# arXiv Paper Bot

自动抓取最新 arXiv 论文，按关键词打分，可选生成摘要，保存/推送结果，并收集用户反馈。

## 核心流程
- 配置与日志：读取 `config/config.yaml`，按 `logging` 输出到文件/控制台。
- 抓取：`ArxivFetcher.fetch_latest_papers(days)` 支持 `category_only` / `keyword_only` / `combined` / `category_then_filter`；`search_keywords` 直接用于 API 查询，`fetch_full_categories` 为 True 时再拉整类并去重；仅保留最近 `days` 天。
- 过滤：`PaperFilter` 在标题+摘要整词匹配，权重高/中/低=3.0/2.0/1.0；丢弃 `score < min_score`，按分数排序取 `top_k`，生成 `top_keywords` 统计。
- 摘要（可选）：`PaperSummarizer` 使用 OpenAI 兼容接口（`provider/model/base_url/api_key_env`），逐篇生成字段（默认 `one_sentence_highlight`、`core_method` 等）。
- 存储：`PaperStorage` 输出 JSON/CSV，`append_mode` 下读旧文件并按 `arxiv_id` 去重。
- 推送（可选）：`build_notifier` 构建 Feishu / Telegram / WeChat 推送，发送前 `top_k` 条文本 digest。
- 反馈：`feedback.py` CLI 调 `FeedbackCollector` 记录 like/dislike 至 `data/feedback/*`，产出偏好统计。

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

## 配置速览（config/config.yaml）
- `arxiv`: `categories`, `max_results`, `fetch_mode`, `search_keywords`, `fetch_full_categories`, `sort_by`, `sort_order`
- `filter`: `keywords` (high/medium/low), `min_score`, `top_k`, `enabled`
- `summarization`: `enabled`, `provider`, `api.base_url`, `api.model`, `api_key_env`, `fields`
- `storage`: `format`, `json_path`, `csv_path`, `append_mode`
- `notification`: `enabled`, `provider`, `top_k`, 渠道凭据（feishu/telegram/wechat）
- `personalization`: 预留的向量/Agent 槽位，默认关闭
- `logging`: `level`, `log_file`, `console_output`

## 常用命令
```bash
python main.py --days 7                 # 最近 7 天
python main.py --test                   # 测试模式（减少抓取量）
python feedback.py list liked --verbose # 查看反馈
python run_tests.py                     # 运行单测
```

## 项目结构
```
main.py                 # 入口，串联流程
feedback.py             # 反馈 CLI
config/config.yaml      # 配置
src/
  fetcher.py            # 抓取
  filter.py             # 过滤/统计
  summarizer.py         # 摘要
  storage.py            # JSON/CSV
  notifier.py           # 推送
  feedback.py           # 反馈存储
  personalization.py    # 个性化占位
tests/                  # 单元测试
examples/               # 使用示例
```

## 小贴士
- 抓不到论文：增大 `--days` 或降低 `filter.min_score`，检查 `search_keywords` 是否过窄。
- 推送失败：确认渠道凭据齐全；Feishu 需 webhook（如启用签名则填 secret），WeChat 需 app_id/app_secret/open_id。
- 摘要报错：确保 `summarization.enabled=true` 且 `api_key_env`/`api_key` 生效，网络可访问 `base_url`。
