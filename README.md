# arXiv Paper Bot - 智能论文推荐系统

> 从每天500+篇arXiv论文中，自动筛选出你最感兴趣的5-10篇

**快速导航**: [快速开始](#快速开始) | [使用流程](#使用流程) | [完整文档](DOCS.md)

---

## ✨ 核心特性

- **🎯 高效筛选**: 漏斗架构，从500+篇缩减到5-10篇精准推荐
- **🔍 多模式抓取**: 支持4种抓取模式，combined模式效率提升80%
- **⚖️ 智能评分**: 多级关键词权重系统（high: 3.0, medium: 2.0, low: 1.0）
- **👍 反馈学习**: 完整的Like/Dislike收集系统，持续优化推荐
- **📨 多渠道推送**: 支持飞书、Telegram、微信公众号自动推送精选摘要
- **🔌 预留扩展**: 向量相似度和Agent意图识别接口已就绪
- **📊 双格式存储**: JSON（程序化）+ CSV（Excel）同时输出

---

## 🚀 快速开始

### 安装（1分钟）

```bash
# 克隆仓库
git clone <your-repo-url>
cd arxiv_paper

# 安装依赖
pip install -r requirements.txt
```

### 配置（2分钟）

编辑 `config/config.yaml`：

```yaml
arxiv:
  categories: [cs.CV, cs.AI]       # 你关注的领域
  fetch_mode: combined              # 推荐：最高效模式
  fetch_full_categories: false      # 需要兜底拉全量时改为 true
  search_keywords:                  # API级关键词
    - transformer
    - diffusion

filter:
  keywords:
    high_priority: [transformer]    # 权重3.0
    medium_priority: [detection]    # 权重2.0
  min_score: 1.0
  top_k: 20

notification:
  enabled: true
  provider: feishu
  top_k: 5
  feishu:
    webhook_url: https://open.feishu.cn/xxx
    secret: your-secret-if-enabled
```

### 运行（1分钟）

```bash
# 抓取最近1天的论文
python main.py

# 查看结果
cat data/papers.json | jq '.[0:3]'
```

**输出示例：**
```
[1/5] Fetching papers from arXiv... ✓ Fetched 85 papers
[2/5] Filtering and ranking...      ✓ Filtered to 18 papers
[3/5] Generating summaries...       ✓ Skipped
[4/5] Saving results...             ✓ Saved 18 papers
[5/5] Sending notifications...      ✓ Sent via Feishu

Top 5 Papers:
1. Artificial Hippocampus Networks... (Score: 6.0)
   Keywords: transformer, attention
   URL: https://arxiv.org/abs/2510.07318
```

---

## 📖 使用流程

### 日常工作流（每天5分钟）

```
配置 → 抓取 → 查看 → 反馈 → 推送 → 优化
```

#### 1. 抓取论文

```bash
python main.py              # 默认1天
python main.py --days 7     # 最近7天
```

#### 2. 查看结果

```bash
cat data/papers.json                            # JSON格式
cat data/papers.json | jq '.[] | select(.score >= 5)'  # 只看高分
open data/papers.csv                            # CSV格式（Excel）
```

#### 3. 反馈收集（核心）⭐

```bash
python feedback.py like 2510.07318    # 👍 喜欢
python feedback.py dislike 2501.99999 # 👎 不喜欢
python feedback.py stats              # 📊 查看统计
```

**统计输出示例：**
```
📊 User Feedback Statistics
  Total liked: 15 papers
  Total disliked: 3 papers

🔑 Top Keywords in Liked Papers:
  - transformer: 12 papers (80%)
  - multimodal: 8 papers (53%)
```

#### 4. 优化配置（每周）

根据统计结果调整 `config.yaml` 中的关键词权重

#### 5. 多渠道推送（可选）

在 `notification` 模块填写飞书 / Telegram / 微信公众号的凭据，运行完成后自动推送 Top N 推荐摘要。

---

## 🏗️ 系统架构

### 漏斗筛选流程

```
500+ arXiv论文
    ↓
【Level 1】API过滤 (combined模式)
  → 减少90%无关论文
    ↓
50-100篇候选
    ↓
【Level 2】本地关键词评分
 → 多级权重 + Top-K
    ↓
20篇高质量论文
    ↓
【槽位1】向量相似度 🔲 预留
    ↓
【槽位2】Agent意图 🔲 预留
    ↓
5-10篇个性化推荐
    ↓
📨 多渠道推送（可选）
    ↓
👍👎 反馈循环
```

### 4种抓取模式对比

| 模式 | 效率 | 适用场景 |
|------|------|---------|
| `category_only` | ⭐⭐⭐ | 只关心领域 |
| `keyword_only` | ⭐⭐⭐ | 跨领域搜索 |
| **`combined`** ⭐ | ⭐⭐⭐⭐⭐ | **推荐**：领域+关键词 |
| `category_then_filter` | ⭐⭐ | 兼容模式 |

---

## 📂 项目结构

```
arxiv_paper/
├── main.py                  # ✅ 主程序
├── feedback.py              # ✅ 反馈CLI
├── config/config.yaml       # ✅ 配置文件
├── src/                     # ✅ 核心模块
│   ├── fetcher.py           #   arXiv抓取
│   ├── filter.py            #   关键词过滤
│   ├── storage.py           #   JSON/CSV存储
│   ├── notifier.py          #   多渠道推送
│   ├── feedback.py          #   反馈收集 ⭐
│   └── personalization.py   #   个性化（预留）🔲
├── data/                    # ✅ 数据输出
│   ├── papers.json
│   ├── papers.csv
│   └── feedback/            #   反馈数据 ⭐
├── tests/                   # ✅ 单元测试（27个全通过）
└── DOCS.md                  # 📖 完整文档
```

---

## 🎯 实现阶段

```
✅ Phase 0: 基础功能
  • 4种抓取模式
  • 关键词过滤与评分
  • JSON/CSV存储
  • 19个单元测试全通过

✅ Phase 0.5: 反馈系统 ⭐
  • FeedbackCollector模块
  • feedback.py CLI工具
  • 用户画像生成
  • 关键词偏好统计

🔲 Phase 1: 向量相似度（预留）
  • SPECTER embeddings
  • ChromaDB向量数据库
  • 基于liked论文的相似度排序

🔲 Phase 2: Agent意图识别（预留）
  • LLM阅读模式分析
  • 动态关键词生成
  • 推荐理由解释
```

---

## 📊 数据格式

### papers.json
```json
{
  "arxiv_id": "2510.07318",
  "title": "...",
  "score": 6.0,
  "matched_keywords": ["transformer", "attention"],
  "similarity_score": null,        // 🔲 Phase 1
  "personalized_score": null,      // 🔲 Phase 1
  "user_feedback": null            // ✅ 反馈收集
}
```

### user_profile.json
```json
{
  "statistics": {
    "total_liked": 15,
    "total_disliked": 3
  },
  "preferred_keywords": {
    "transformer": 12,
    "multimodal": 8
  }
}
```

---

## ⚙️ 常用命令

```bash
# 主程序
python main.py                     # 抓取论文
python main.py --days 7            # 最近7天
python main.py --test              # 测试模式

# 反馈管理
python feedback.py like <id>       # 点赞
python feedback.py dislike <id>    # 不喜欢
python feedback.py stats           # 统计
python feedback.py list liked      # 列表
python feedback.py clear all       # 清空

# 测试
python run_tests.py                # 运行测试
```

---

## 🐛 故障排查

**问题1：Fetched 0 papers**
```bash
# 解决方案：
python main.py --days 7            # 增加天数
# 或降低 config.yaml 中的 min_score
```

**问题2：分数都很低**
```yaml
# config.yaml
filter:
  min_score: 0.5                   # 降低阈值
  keywords:
    low_priority:                  # 增加通用关键词
      - deep learning
```

更多故障排查请参考 [完整文档](DOCS.md#故障排查)

---

## 📚 文档

- **[DOCS.md](DOCS.md)** - 完整技术文档（架构、配置、开发指南）
- **[WORKFLOW.md](WORKFLOW.md)** - 详细使用流程（场景、示例、最佳实践）
- **tests/README.md** - 测试说明
- **examples/** - 示例脚本

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

### 开发路线图

- [ ] Phase 1: 实现向量相似度排序
- [ ] Phase 2: 实现Agent意图识别
- [ ] Web UI界面
- [ ] 多平台推送（Telegram, 飞书）

---

## 📄 License

MIT License

---

## 🎉 快速参考

**3步上手：**
```bash
pip install -r requirements.txt   # 1. 安装
vim config/config.yaml             # 2. 配置
python main.py                     # 3. 运行
```

**日常使用：**
```bash
python main.py                     # 抓取
python feedback.py like <id>       # 反馈
python feedback.py stats           # 统计
```

**详细文档**: [DOCS.md](DOCS.md)

---

**版本**: v0.1.0 (Phase 0.5)
**状态**: ✅ 生产可用 | 🔲 预留槽位已就绪
**最后更新**: 2025-10-09
