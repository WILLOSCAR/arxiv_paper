import os
import datetime
import requests

BASE_URL = "https://openrouter.ai/api/v1"
MODELS_API_URL = f"{BASE_URL}/models"

# 浏览器 Models 页： https://openrouter.ai/models?q=free
# 对应的前端 API（默认按调用量/Token 排序）：
FRONTEND_FIND_API_URL = "https://openrouter.ai/api/frontend/models/find"
FRONTEND_FIND_PARAMS = {"fmt": "cards", "q": "free"}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://openrouter.ai/models?q=free",
    "Origin": "https://openrouter.ai",
}

OPENROUTER_API_KEY = os.getenv(
    "OPENROUTER_API_KEY",
    "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",
)


def fetch_frontend_models(sort: str | None = None) -> list[dict]:
    """
    访问前端专用接口 /api/frontend/models/find，返回网页使用的模型列表。
    默认排序就是网页展示的调用量/Token 顺序。
    """
    params = dict(FRONTEND_FIND_PARAMS)
    if sort:
        params["sort"] = sort

    resp = requests.get(
        FRONTEND_FIND_API_URL, params=params, headers=HEADERS, timeout=10
    )
    resp.raise_for_status()
    data = resp.json()

    models = data.get("data", {}).get("models")
    if models is None:
        models = data.get("data", [])

    if not isinstance(models, list):
        raise RuntimeError("没能在响应中拿到 models 列表，结构可能已变")

    return models


def is_free_model_v1(model: dict) -> bool:
    """针对 /api/v1/models 的结构判断是否免费。"""
    pricing = model.get("pricing") or {}
    try:
        return (
            float(pricing.get("prompt", 1)) == 0
            and float(pricing.get("completion", 1)) == 0
        )
    except (TypeError, ValueError):
        return False


def get_free_models_sorted_by_date(limit: int | None = None) -> list[dict]:
    """从 /api/v1/models 拉取免费模型，按创建时间倒序。"""
    print("正在通过 /api/v1/models 获取模型列表...")
    resp = requests.get(MODELS_API_URL, timeout=10)
    resp.raise_for_status()
    all_models = resp.json().get("data", [])

    free_models = [
        {
            "id": m.get("id"),
            "name": m.get("name"),
            "created": m.get("created", 0),
            "context": m.get("context_length"),
        }
        for m in all_models
        if is_free_model_v1(m)
    ]

    free_models.sort(key=lambda x: x["created"], reverse=True)
    if limit is not None:
        free_models = free_models[:limit]

    print(f"\n成功找到 {len(free_models)} 个免费模型（按创建时间倒序）：\n")
    print(f"{'发布日期':<12} | {'模型 ID (Model ID)':<45} | {'上下文 (Context)'}")
    print("-" * 80)

    for m in free_models:
        date_str = (
            datetime.datetime.fromtimestamp(m["created"]).strftime("%Y-%m-%d")
            if m["created"]
            else "未知"
        )
        print(f"{date_str:<12} | {m['id']:<45} | {m['context']}")

    return free_models


def get_free_models_hot(top_k: int = 20) -> list[dict]:
    """
    从前端接口 /api/frontend/models/find 拿到网页默认顺序（基于调用量）
    的免费模型。
    """
    models = fetch_frontend_models()
    result: list[dict] = []

    for m in models:
        endpoint = m.get("endpoint") or {}
        pricing = endpoint.get("pricing") or {}

        # 前端结构里“免费”主要看 endpoint
        is_free = endpoint.get("is_free") or (
            pricing.get("prompt") == "0" and pricing.get("completion") == "0"
        )
        if not is_free:
            continue

        model_id = (
            endpoint.get("model_variant_slug")
            or endpoint.get("model_variant_permaslug")
            or endpoint.get("preferred_model_provider_slug")
            or m.get("slug")
            or m.get("id")
        )
        ctx = endpoint.get("context_length") or m.get("context_length")

        result.append(
            {
                "name": m.get("name"),
                "id": model_id,
                "context": ctx,
            }
        )

        if len(result) >= top_k:
            break

    return result



def get_web_sorted_models(limit: int = 15, sort: str | None = None) -> list[dict]:
    """
    请求网页默认排序（调用量/Token）的免费模型列表，并打印前 N 个。
    可通过 sort 显式指定排序策略（如 popularity/usage），不指定则用网页默认。
    """
    models = fetch_frontend_models(sort=sort)

    print("\n======== 网页版默认排序（调用量顺序） ========")
    print(f"获取到 {len(models)} 个模型，展示前 {limit} 个\n")

    for i, model in enumerate(models[:limit]):
        endpoint = model.get("endpoint") or {}
        slug = (
            endpoint.get("model_variant_slug")
            or endpoint.get("model_variant_permaslug")
            or endpoint.get("preferred_model_provider_slug")
            or model.get("slug")
            or model.get("id")
        )
        name = model.get("name", slug)

        stats = model.get("stats") or endpoint.get("stats") or {}
        calls_30d = stats.get("calls_30d") if isinstance(stats, dict) else None
        tokens_30d = stats.get("tokens_30d") if isinstance(stats, dict) else None

        usage_parts = []
        if calls_30d is not None:
            usage_parts.append(f"calls_30d={calls_30d}")
        if tokens_30d is not None:
            usage_parts.append(f"tokens_30d={tokens_30d}")

        usage_str = f" | {'; '.join(usage_parts)}" if usage_parts else ""
        print(f"#{i+1:<2} | {name} ({slug}){usage_str}")

    return models

if __name__ == "__main__":
    models = get_web_sorted_models()
    
    # 生成最热模型的调用代码
    if models:
        top_endpoint = models[0].get("endpoint") or {}
        top_model_slug = (
            top_endpoint.get("model_variant_slug")
            or top_endpoint.get("model_variant_permaslug")
            or top_endpoint.get("preferred_model_provider_slug")
            or models[0].get("slug")
            or models[0].get("id")
        )
        print(f"\n\n>>> 推荐调用最热免费模型: {top_model_slug}")
