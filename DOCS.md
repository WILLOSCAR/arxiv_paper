# arXiv Paper Bot - 完整文档

> **快速导航**
> - [快速开始](#快速开始) - 3分钟上手
> - [使用流程](#使用流程) - 日常使用指南
> - [系统架构](#系统架构) - 技术设计
> - [配置说明](#配置说明) - 详细参数
> - [开发指南](#开发指南) - 扩展开发

---

## 📋 目录

1. [快速开始](#快速开始)
2. [使用流程](#使用流程)
3. [系统架构](#系统架构)
4. [配置说明](#配置说明)
5. [技术实现](#技术实现)
6. [故障排查](#故障排查)
7. [开发指南](#开发指南)

---

## 快速开始

### 安装与配置（2分钟）

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置关键词（编辑 config/config.yaml）
vim config/config.yaml

# 核心配置：
#   categories: [cs.CV, cs.AI]     # 你关注的领域
#   search_keywords: [transformer] # 关键词
#   fetch_mode: combined           # 推荐模式

# 3. 运行
python main.py
```

### 第一次运行（1分钟）

```bash
# 抓取最近1天的论文
python main.py

# 查看结果
cat data/papers.json | jq '.[0:3]'

# 输出示例：
# Top 5 Papers:
# 1. Artificial Hippocampus Networks... (Score: 6.0)
#    Keywords: transformer, attention
#    URL: https://arxiv.org/abs/2510.07318
```

---

## 使用流程

### 日常工作流（每天5分钟）

```
配置 → 抓取 → 查看 → 反馈 → 推送 → 优化 → 循环
```

#### Step 1: 抓取论文

```bash
# 默认抓取最近1天
python main.py

# 抓取最近7天（周报场景）
python main.py --days 7
```

**执行过程：**
```
[1/5] 从 arXiv 抓取论文
  ├─ Mode: combined (cs.AI + keywords)
  ├─ (可选) fetch_full_categories=True 时额外拉取分类全量数据
  └─ 输出: ~50-100篇

[2/5] 本地关键词过滤与评分
  ├─ 多级权重计算
  └─ 输出: ~20篇

[3/5] AI总结（可选，默认关闭）

[4/5] 保存结果
  ├─ data/papers.json
  └─ data/papers.csv

[5/5] 多渠道推送（可选）
  └─ 将 Top N 论文推送到配置的渠道
```

#### Step 2: 查看结果

```bash
# JSON格式（程序化处理）
cat data/papers.json

# 只看高分论文（分数>=5）
cat data/papers.json | jq '.[] | select(.score >= 5)'

# CSV格式（Excel打开）
open data/papers.csv
```

#### Step 3: 反馈收集（核心功能）⭐

```bash
# 👍 喜欢这篇论文
python feedback.py like 2510.07318

# 👎 不喜欢
python feedback.py dislike 2501.99999

# 📊 查看统计
python feedback.py stats

# 输出：
# 📊 User Feedback Statistics
#   Total liked: 15 papers
#   Top Keywords in Liked Papers:
#   - transformer: 12 papers (80%)
#   - multimodal: 8 papers (53%)
```

```bash
# 查看已点赞的论文列表
python feedback.py list liked

# 详细模式（显示关键词、时间）
python feedback.py list liked --verbose

# 清空反馈数据
python feedback.py clear all
```

#### Step 4: 多渠道推送（可选）

```bash
# 启用推送前请在 config/config.yaml 填写 notification 配置
python main.py  # 运行后自动推送当日 Top N 论文
```

**支持渠道：**

- 飞书群机器人：配置 `notification.feishu.webhook_url`（如开启签名则填写 `secret`）。
- Telegram Bot：配置 `notification.telegram.bot_token` 与 `chat_id`。
- 微信公众号：配置 `notification.wechat`（需要已关注公众号的用户 OpenID）。

程序会在保存 `papers.json` / `papers.csv` 后调用推送模块，并将关键信息（标题、得分、关键词、链接）以文本形式发送。

#### Step 5: 优化配置（每周一次）

```bash
# 1. 查看反馈统计
python feedback.py stats

# 2. 根据统计结果调整 config.yaml
vim config/config.yaml

# 例如：如果"transformer"出现在80%的liked论文中
# → 将其提升到 high_priority
```

### 典型场景

#### 场景1：每天早上获取推荐

```bash
# Linux/Mac cron定时
crontab -e
# 添加：0 9 * * * cd /path/to/arxiv_paper && python main.py
```

#### 场景2：快速测试新关键词

```bash
# 1. 修改 config.yaml 添加新关键词
# 2. 测试模式
python main.py --test

# 3. 检查结果
cat data/papers.json | jq '.[0:3]'

# 4. 满意后正式运行
python main.py
```

#### 场景3：周报整理

```bash
python main.py --days 7
open data/papers.csv
```

---

## 系统架构

### 漏斗筛选架构

系统采用**多级漏斗架构**，从500+篇论文筛选到5-10篇：

```
┌─────────────────────────────────────┐
│  500+ Daily Papers on arXiv         │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│  Level 1: API-Level Filtering       │
│  • combined: (keywords) AND cat     │
│  • Reduce 90% papers                │
│  Output: ~50-100 papers             │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│  Level 2: Local Keyword Scoring     │
│  • Multi-tier weighting             │
│  • Top-K selection                  │
│  Output: ~20 papers                 │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│  Slot 1: Vector Similarity 🔲       │
│  • SPECTER embeddings               │
│  • Status: Reserved (Phase 1)       │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│  Slot 2: Agent Intent 🔲            │
│  • LLM pattern analysis             │
│  • Status: Reserved (Phase 2)       │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│  Final List (5-10 papers)           │
│  • User Feedback Loop               │
└─────────────────────────────────────┘
```

### 数据流

#### 输入（arXiv API）
```json
{
  "arxiv_id": "2510.07318",
  "title": "...",
  "abstract": "...",
  "categories": ["cs.AI"]
}
```

#### 输出（data/papers.json）
```json
{
  "arxiv_id": "2510.07318",
  "title": "...",
  "score": 6.0,                    // ✅ 关键词评分
  "matched_keywords": [            // ✅ 匹配的关键词
    "transformer",
    "attention"
  ],

  // 🔲 预留字段（Phase 1/2）
  "similarity_score": null,
  "personalized_score": null,
  "user_feedback": null
}
```

#### 反馈数据（data/feedback/）
```
liked_papers.json         // 点赞列表
disliked_papers.json      // 不喜欢列表
user_profile.json         // 用户画像（自动生成）
```

### 4种抓取模式对比

| 模式 | API查询 | 效率 | 适用场景 |
|------|---------|------|---------|
| `category_only` | `cat:cs.AI` | ⭐⭐⭐ | 只关心领域 |
| `keyword_only` | `"transformer"` | ⭐⭐⭐ | 跨领域搜索 |
| **`combined`** ⭐ | `("transformer") AND cat:cs.AI` | ⭐⭐⭐⭐⭐ | **推荐** |
| `category_then_filter` | `cat:cs.AI` | ⭐⭐ | 兼容模式 |

**推荐**：使用 `combined` 模式，在API级别就过滤90%无关论文！

### 实现阶段

```
✅ Phase 0 (已完成)
  • arXiv API抓取（4种模式）
  • 关键词过滤与评分
  • JSON/CSV存储

✅ Phase 0.5 (已完成) ⭐
  • FeedbackCollector模块
  • feedback.py CLI工具
  • 用户画像生成

🔲 Phase 1 (预留，1-2天工作量)
  • SPECTER论文embedding
  • ChromaDB向量数据库
  • 相似度排序

🔲 Phase 2 (预留，3-5天工作量)
  • LLM阅读模式分析
  • 动态关键词生成
  • 推荐理由解释
```

---

## 配置说明

### 核心配置文件：config/config.yaml

#### 1. arXiv抓取设置

```yaml
arxiv:
  # 关注的领域
  categories:
    - cs.CV    # 计算机视觉
    - cs.AI    # 人工智能
    - cs.LG    # 机器学习

  # 每个类别最多抓取数量
  max_results: 50

  # 抓取模式（推荐 combined）
  fetch_mode: combined

  # 当使用关键词抓取时是否额外拉取完整分类供本地过滤
  fetch_full_categories: false

  # API级关键词（用于combined模式）
  search_keywords:
    - transformer
    - diffusion
    - multimodal
```

**常用arXiv分类：**
- `cs.CV` - 计算机视觉
- `cs.AI` - 人工智能
- `cs.LG` - 机器学习
- `cs.CL` - NLP
- `cs.RO` - 机器人
- `stat.ML` - 统计机器学习

#### 2. 过滤设置

```yaml
filter:
  enabled: true

  # 关键词及权重
  keywords:
    high_priority:        # 权重 3.0
      - transformer
      - diffusion
      - multimodal

    medium_priority:      # 权重 2.0
      - detection
      - segmentation

    low_priority:         # 权重 1.0
      - deep learning

  # 最低分数阈值
  min_score: 1.0

  # 保留前K篇
  top_k: 20
```

**评分机制：**
```python
score = Σ(keyword_weight × match_count)
```

#### 3. 个性化设置（预留）

```yaml
personalization:
  enabled: false         # 🔲 暂未实现

  feedback:
    enabled: true        # ✅ 反馈收集可用
    feedback_dir: data/feedback

  vector_ranking:        # 🔲 Phase 1
    enabled: false
    model: allenai/specter
    weight: 0.4

  agent:                 # 🔲 Phase 2
    enabled: false
    provider: openai
    model: gpt-4o-mini
```

#### 4. 存储设置

```yaml
storage:
  format: both           # json/csv/both
  json_path: data/papers.json
  csv_path: data/papers.csv
  append_mode: true      # 追加模式，自动去重
```

#### 5. AI总结设置（可选）

```yaml
summarization:
  enabled: false         # 默认关闭
  provider: gemini
  api:
    base_url: "https://api.example.com/v1"
    model: "gemini-2.5-flash"
    api_key_env: "ARXIV_API_KEY"
  fields:
    - one_sentence_highlight
    - core_method
```

#### 6. 通知推送设置（可选）

```yaml
notification:
  enabled: true              # 是否开启推送
  provider: feishu           # feishu / telegram / wechat
  top_k: 5                   # 推送条数

  feishu:
    webhook_url: https://open.feishu.cn/xxx
    secret: your-secret-if-enabled

  telegram:
    bot_token: 123456:ABCDEF
    chat_id: "-100123456"

  wechat:
    app_id: wx1234567890
    app_secret: your-app-secret
    open_id: user-open-id
```

**注意事项：**
- 飞书：需提前在目标群组创建自定义机器人；若启用签名校验，请填写 `secret`。
- Telegram：获取 `chat_id` 可通过 `@userinfobot` 或调用 API `getUpdates`。
- 微信公众号：仅支持已关注公众号的用户，需具备客服消息权限。

---

## 技术实现

### 项目结构

```
arxiv_paper/
├── main.py                      # ✅ 主程序入口
├── feedback.py                  # ✅ 反馈管理CLI
├── requirements.txt             # ✅ 依赖列表
│
├── config/
│   └── config.yaml              # ✅ 配置文件
│
├── src/                         # ✅ 核心模块
│   ├── __init__.py
│   ├── fetcher.py               # arXiv抓取
│   ├── filter.py                # 关键词过滤
│   ├── storage.py               # 存储
│   ├── models.py                # 数据模型
│   ├── summarizer.py            # AI总结
│   ├── notifier.py              # 多渠道通知
│   ├── feedback.py              # 反馈收集 ⭐
│   └── personalization.py       # 个性化（预留）🔲
│
├── data/                        # ✅ 数据目录
│   ├── papers.json
│   ├── papers.csv
│   └── feedback/                # 反馈数据 ⭐
│       ├── liked_papers.json
│       ├── disliked_papers.json
│       └── user_profile.json
│
├── tests/                       # ✅ 单元测试
│   ├── test_models.py
│   ├── test_filter.py
│   ├── test_storage.py          # 存储读写
│   └── test_notifier.py         # 推送逻辑（HTTP 调用mock）
│
└── logs/
    └── arxiv_bot.log
```

### 核心模块

#### 1. fetcher.py - 论文抓取

```python
from src import ArxivFetcher, FetchConfig

config = FetchConfig(
    categories=["cs.AI"],
    max_results=50,
    fetch_mode="combined",
    search_keywords=["transformer"]
)

fetcher = ArxivFetcher(config)
papers = fetcher.fetch_latest_papers(days=1)
```

**特性：**
- ✅ 4种抓取模式
- ✅ 自动去重
- ✅ 日期过滤
- ✅ 完整元数据

#### 2. filter.py - 关键词过滤

```python
from src import PaperFilter, FilterConfig

config = FilterConfig(
    enabled=True,
    keywords={
        "high_priority": ["transformer"],
        "medium_priority": ["detection"]
    },
    min_score=1.0,
    top_k=20
)

filter = PaperFilter(config)
ranked = filter.filter_and_rank(papers)
```

**评分算法：**
- 在标题+摘要中匹配关键词
- 使用正则表达式 `\b关键词\b`
- 累加权重分数

#### 3. feedback.py - 反馈收集

```python
from src import FeedbackCollector

collector = FeedbackCollector()

# 记录反馈
collector.record_feedback("2510.07318", "like", paper_data)

# 获取统计
stats = collector.get_statistics()
# {
#   "total_liked": 15,
#   "total_disliked": 3,
#   "top_keywords": [("transformer", 12), ...],
#   "feedback_ratio": 0.833
# }

# 获取用户偏好关键词
keywords = collector.get_user_keywords()
# {"transformer": 12, "multimodal": 8, ...}
```

#### 4. storage.py - 数据存储

```python
from src import PaperStorage

storage = PaperStorage(
    json_path="data/papers.json",
    csv_path="data/papers.csv",
    append_mode=True
)

# 保存（自动去重）
storage.save(papers, format="both")
```

### 关键算法

#### 关键词匹配
```python
def _score_paper(paper: Paper) -> tuple[float, List[str]]:
    text = f"{paper.title} {paper.abstract}".lower()
    score = 0.0
    matched = []

    for keyword, weight in keywords.items():
        pattern = r"\b" + re.escape(keyword) + r"\b"
        if re.search(pattern, text):
            score += weight
            matched.append(keyword)

    return score, matched
```

#### 去重逻辑
```python
def _deduplicate_papers(papers: List[Paper]) -> List[Paper]:
    seen_ids = set()
    unique = []

    for paper in papers:
        if paper.arxiv_id not in seen_ids:
            seen_ids.add(paper.arxiv_id)
            unique.append(paper)

    return unique
```

---

## 故障排查

### 问题1：无法抓取论文（Fetched 0 papers）

**可能原因：**
1. days参数太小，最近没有新论文
2. 关键词太严格
3. 网络问题

**解决方案：**
```bash
# 增加天数
python main.py --days 7

# 降低min_score
# config.yaml: min_score: 0.5

# 测试网络
curl https://export.arxiv.org/api/query
```

### 问题2：分数都很低

**解决方案：**
```yaml
# 1. 增加关键词
keywords:
  low_priority:
    - deep learning
    - neural network
    - machine learning

# 2. 降低阈值
min_score: 0.5

# 3. 使用combined模式
fetch_mode: combined
```

### 问题3：反馈统计为空

**检查：**
```bash
# 查看反馈文件
ls -la data/feedback/

# 查看liked论文
cat data/feedback/liked_papers.json

# 重新记录反馈
python feedback.py like <paper_id>
```

### 问题4：Timezone错误

**已修复**（src/fetcher.py）：
```python
# 修改前：
cutoff_date = datetime.now() - timedelta(days=days)

# 修改后：
cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
```

---

## 开发指南

### 扩展Phase 1：向量相似度

**步骤：**

1. **安装依赖**
```bash
# 取消注释 requirements.txt
pip install sentence-transformers chromadb
```

2. **启用配置**
```yaml
# config.yaml
personalization:
  vector_ranking:
    enabled: true
    model: allenai/specter
```

3. **实现方法**（src/personalization.py）
```python
def compute_embedding(self, paper: Paper) -> np.ndarray:
    """实现论文embedding计算"""
    text = f"{paper.title} {paper.abstract}"
    return self.model.encode(text)

def rank_by_similarity(
    self,
    papers: List[Paper],
    liked_papers: List[Paper]
) -> List[Paper]:
    """实现相似度排序"""
    # 1. 计算所有论文的embedding
    # 2. 计算liked论文的平均embedding
    # 3. 计算cosine相似度
    # 4. 结合keyword score重排序
    pass
```

### 扩展Phase 2：Agent意图识别

**步骤：**

1. **配置LLM**
```yaml
personalization:
  agent:
    enabled: true
    provider: openai
    model: gpt-4o-mini
```

2. **实现方法**（src/personalization.py）
```python
def analyze_reading_pattern(
    self,
    liked_papers: List[Paper]
) -> dict:
    """实现阅读模式分析"""
    # 1. 提取liked论文的标题和摘要
    # 2. 调用LLM分析
    # 3. 返回结构化结果
    return {
        "main_interests": ["multimodal", "transformer"],
        "suggested_keywords": ["CLIP", "vision-language"]
    }
```

### 添加新的数据源

**示例：从会议网站抓取**
```python
# src/conference_fetcher.py
class ConferenceFetcher:
    def fetch_papers(self, conference: str) -> List[Paper]:
        # 实现从会议网站抓取
        pass

# main.py
arxiv_papers = arxiv_fetcher.fetch()
conf_papers = conference_fetcher.fetch("CVPR")
all_papers = arxiv_papers + conf_papers
```

### 单元测试

**运行测试：**
```bash
python run_tests.py

# 或使用pytest
pytest tests/ -v
```

**添加新测试：**
```python
# tests/test_feedback.py
import unittest
from src import FeedbackCollector

class TestFeedback(unittest.TestCase):
    def test_record_feedback(self):
        collector = FeedbackCollector()
        collector.record_feedback("2510.07318", "like")
        liked = collector.get_liked_papers()
        self.assertEqual(len(liked), 1)
```

---

## 附录

### A. 完整命令参考

```bash
# 主程序
python main.py                    # 抓取最近1天
python main.py --days 7           # 抓取最近7天
python main.py --test             # 测试模式
python main.py --config custom.yaml  # 自定义配置

# 反馈管理
python feedback.py like <id>      # 点赞
python feedback.py dislike <id>   # 不喜欢
python feedback.py stats          # 统计
python feedback.py list liked     # 列表
python feedback.py list liked -v  # 详细列表
python feedback.py clear all      # 清空

# 测试
python run_tests.py               # 运行所有测试
```

### B. 文件格式示例

**papers.json 完整格式：**
```json
[
  {
    "arxiv_id": "2510.07318v1",
    "title": "Artificial Hippocampus Networks...",
    "abstract": "Full abstract text...",
    "authors": ["Author 1", "Author 2"],
    "primary_category": "cs.AI",
    "categories": ["cs.AI", "cs.LG"],
    "pdf_url": "https://arxiv.org/pdf/2510.07318",
    "entry_url": "https://arxiv.org/abs/2510.07318",
    "published": "2025-10-05T12:00:00Z",
    "updated": "2025-10-05T12:00:00Z",
    "score": 6.0,
    "matched_keywords": ["transformer", "attention"],
    "summary": null,
    "fetched_at": "2025-10-09T10:30:00Z"
  }
]
```

**user_profile.json 格式：**
```json
{
  "updated_at": "2025-10-09T12:00:00",
  "statistics": {
    "total_liked": 15,
    "total_disliked": 3,
    "feedback_ratio": 0.833
  },
  "preferred_keywords": {
    "transformer": 12,
    "multimodal": 8,
    "vision-language": 6
  }
}
```

### C. 性能优化建议

1. **减少API调用**
   - 使用 `combined` 模式
   - 合理设置 `max_results`

2. **本地缓存**
   - 使用 `append_mode: true`
   - 定期清理旧数据

3. **并行处理**（未来）
   - Phase 1: 批量embedding计算
   - 使用GPU加速

### D. 相关资源

- [arXiv API文档](https://arxiv.org/help/api)
- [arXiv Python库](https://github.com/lukasschwab/arxiv.py)
- [arXiv分类列表](https://arxiv.org/category_taxonomy)
- [SPECTER模型](https://github.com/allenai/specter)

---

## 版本历史

**v0.1.0** (2025-10-09)
- ✅ Phase 0: 基础功能（抓取、过滤、存储）
- ✅ Phase 0.5: 反馈系统
- 🔲 Phase 1: 向量相似度（预留）
- 🔲 Phase 2: Agent意图（预留）

---

**文档版本**: v0.1.0
**最后更新**: 2025-10-09
**状态**: ✅ 生产可用 | 🔲 预留槽位已就绪
