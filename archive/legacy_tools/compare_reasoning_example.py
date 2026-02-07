"""[Archived] Legacy experiment utility. Not part of the supported workflow."""

"""
GPT-4 (120B) vs DeepSeek R1 思维链对比测试

使用方法:
1. 配置 .env 文件: OPENROUTER_API_KEY=your_key
2. 配置 OpenRouter 隐私设置: https://openrouter.ai/settings/privacy
   - 选择 "Allow free models to be trained on my data"
3. 运行: python compare_reasoning_example.py

支持两种调用方式:
- USE_OPENAI_CLIENT = True: 使用 OpenAI SDK (推荐)
- USE_OPENAI_CLIENT = False: 使用 requests 直接调用

注意: 如果遇到 404 错误 "No endpoints found matching your data policy"，
请访问 https://openrouter.ai/settings/privacy 配置隐私策略。
"""

import json
import time

import requests

from api_request import BASE_URL, OPENROUTER_API_KEY

# 选择调用方式
USE_OPENAI_CLIENT = True  # 改为 False 使用 requests 方式

# 尝试导入 OpenAI SDK
if USE_OPENAI_CLIENT:
    try:
        from openai import OpenAI
    except ImportError:
        print("⚠️  未安装 openai 库，将使用 requests 方式")
        print("   安装命令: pip install openai")
        USE_OPENAI_CLIENT = False

# 测试问题集
PROBLEMS = [
    {
        "name": "递推序列与极限",
        "problem": """Consider a sequence {a_n} defined by:
- a_1 = 1, a_2 = 2
- For n ≥ 3: a_n = a_{n-1} + a_{n-2} + n

Find a_{10} and determine if lim_{n→∞} (a_n / a_{n-1}) exists.""",
    },
    {
        "name": "组合概率",
        "problem": """A fair die is rolled repeatedly. Let X be the number of rolls until the sum first exceeds 20.
(a) What is E[X]?
(b) What is P(X = 6)?""",
    },
    {
        "name": "数论方程",
        "problem": """Find all positive integer solutions (x, y, z) to: x³ + y³ + z³ = 42
Explain your approach.""",
    },
    {
        "name": "几何优化",
        "problem": """A rectangle has perimeter 100 cm. If length increases by 20% and width decreases by 10%, area increases by 8 cm².
Find the original dimensions.""",
    },
    {
        "name": "复数方程",
        "problem": """Solve for all complex numbers z: z⁴ + 4z³ + 6z² + 4z + 5 = 0
Express solutions in a + bi form.""",
    },
    {
        "name": "微积分应用",
        "problem": """Find the volume of the solid formed by rotating the region bounded by y = x², y = 0, and x = 2 around the y-axis.
Show all steps.""",
    },
    {
        "name": "线性代数",
        "problem": """Given matrix A = [[2, 1], [1, 2]], find A^10 without direct multiplication.
Use eigenvalue decomposition.""",
    },
    {
        "name": "图论",
        "problem": """A complete graph K_n has n vertices where every pair is connected. How many spanning trees does K_5 have?
Use Cayley's formula or matrix-tree theorem.""",
    },
]


def call_model_openai_sdk(model_id: str, problem: str) -> dict:
    """使用 OpenAI SDK 调用 (推荐方式)"""
    client = OpenAI(
        base_url=BASE_URL,
        api_key=OPENROUTER_API_KEY,
        default_headers={
            "HTTP-Referer": "https://github.com",  # 必需，用于隐私策略
            "X-Title": "Math Reasoning Test",  # 可选，用于标识
        },
    )

    try:
        completion = client.chat.completions.create(
            model=model_id,
            messages=[
                {"role": "system", "content": "You are a mathematician. Solve step by step."},
                {"role": "user", "content": problem},
            ],
            max_tokens=16384,
            temperature=0.3,
        )

        message = completion.choices[0].message

        return {
            "content": message.content or "",
            "reasoning": getattr(message, "reasoning_content", "") or "",
            "usage": {
                "prompt_tokens": completion.usage.prompt_tokens,
                "completion_tokens": completion.usage.completion_tokens,
                "total_tokens": completion.usage.total_tokens,
            },
            "model": completion.model,
        }

    except Exception as e:
        return {"error": f"OpenAI SDK Error: {str(e)}"}


def call_model_requests(model_id: str, problem: str) -> dict:
    """使用 requests 直接调用"""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com",  # 必需，用于隐私策略
        "X-Title": "Math Reasoning Test",  # 可选，用于标识
    }

    payload = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": "You are a mathematician. Solve step by step."},
            {"role": "user", "content": problem},
        ],
        "max_tokens": 16384,
        "temperature": 0.3,
    }

    try:
        response = requests.post(
            f"{BASE_URL}/chat/completions", headers=headers, json=payload, timeout=180
        )

        if response.status_code != 200:
            return {"error": f"HTTP {response.status_code}: {response.text}"}

        result = response.json()
        message = result["choices"][0]["message"]

        return {
            "content": message.get("content", ""),
            "reasoning": message.get("reasoning_content", ""),
            "usage": result.get("usage", {}),
            "model": result.get("model", model_id),
        }

    except Exception as e:
        return {"error": f"Requests Error: {str(e)}"}


def call_model(model_id: str, problem: str) -> dict:
    """调用模型 (自动选择调用方式)"""
    if not OPENROUTER_API_KEY:
        raise ValueError("请设置 OPENROUTER_API_KEY")

    if USE_OPENAI_CLIENT:
        return call_model_openai_sdk(model_id, problem)
    else:
        return call_model_requests(model_id, problem)


def test_single_problem(problem_data: dict, models: list[str]):
    """测试单个问题"""
    print("\n" + "=" * 100)
    print(f"问题: {problem_data['name']}")
    print("=" * 100)
    print(f"\n{problem_data['problem']}\n")

    results = {}

    for model_id in models:
        model_name = "GPT-4 (120B)" if "gpt" in model_id else "DeepSeek R1"
        print(f"\n{'─' * 100}")
        print(f"模型: {model_name} ({model_id})")
        print("─" * 100)

        start = time.time()
        response = call_model(model_id, problem_data["problem"])
        elapsed = time.time() - start

        if "error" in response:
            print(f"\n❌ 错误: {response['error']}")
            continue

        results[model_id] = {"response": response, "time": elapsed}

        # 打印完整输出
        print(f"\n⏱️  耗时: {elapsed:.2f}秒")
        print(f"📊 Token: {response['usage']}")

        if response["reasoning"]:
            print(f"\n🧠 思维链 ({len(response['reasoning'])} 字符):")
            print("─" * 100)
            print(response["reasoning"])

        print(f"\n💬 最终回复 ({len(response['content'])} 字符):")
        print("─" * 100)
        print(response["content"])

        time.sleep(2)  # 避免频繁调用

    return results


def batch_test(problems: list[dict], models: list[str], output_file: str = "results.json"):
    """批量测试所有问题"""
    all_results = []

    for i, problem_data in enumerate(problems, 1):
        print(f"\n\n{'#' * 100}")
        print(f"# 测试 {i}/{len(problems)}")
        print(f"{'#' * 100}")

        results = test_single_problem(problem_data, models)

        all_results.append(
            {
                "problem": problem_data["name"],
                "question": problem_data["problem"],
                "results": {
                    model_id: {
                        "time": data["time"],
                        "content": data["response"]["content"],
                        "reasoning": data["response"]["reasoning"],
                        "usage": data["response"]["usage"],
                    }
                    for model_id, data in results.items()
                },
            }
        )

    # 保存结果
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print(f"\n\n{'=' * 100}")
    print(f"✅ 所有测试完成！结果已保存到: {output_file}")
    print("=" * 100)

    # 打印统计
    print("\n📊 统计摘要:")
    for model_id in models:
        model_name = "GPT-4 (120B)" if "gpt" in model_id else "DeepSeek R1"
        total_time = sum(
            r["results"].get(model_id, {}).get("time", 0) for r in all_results
        )
        total_tokens = sum(
            r["results"].get(model_id, {}).get("usage", {}).get("total_tokens", 0)
            for r in all_results
        )
        print(f"\n{model_name}:")
        print(f"  总耗时: {total_time:.2f}秒")
        print(f"  总Token: {total_tokens}")
        print(f"  平均耗时: {total_time / len(problems):.2f}秒/题")


def main():
    """主函数"""
    print("=" * 100)
    print("GPT-4 (120B) vs DeepSeek R1 - 思维链对比测试")
    print("=" * 100)

    # 显示调用方式
    call_method = "OpenAI SDK" if USE_OPENAI_CLIENT else "Requests"
    print(f"\n📡 调用方式: {call_method}")
    print(f"🔑 API Key: {'已配置' if OPENROUTER_API_KEY else '❌ 未配置'}")

    # 可用的免费模型
    models = [
        "openai/gpt-oss-120b:free",  # GPT-4 120B
        "tngtech/deepseek-r1t2-chimera:free",
        "nex-agi/deepseek-v3.1-nex-n1:free", 
        "tngtech/deepseek-r1t-chimera:free",
        "z-ai/glm-4.5-air:free", # DeepSeek V3.1 (支持思维链)
    ]

    print(f"\n📋 使用模型:")
    print(f"  1. {models[0]} (GPT-4 120B)")
    print(f"  2. {models[1]} (DeepSeek R1 - 支持思维链)")
    print(f"\n⚠️  如果遇到 404 错误，请访问:")
    print(f"     https://openrouter.ai/settings/privacy")
    print(f"     选择 'Allow free models to be trained on my data'")

    print(f"\n共有 {len(PROBLEMS)} 个测试问题")
    print("\n选项:")
    print("  1. 测试单个问题")
    print("  2. 批量测试所有问题")
    print("  3. 测试前 N 个问题")
    print("  4. 快速示例 (对比两种调用方式)")

    try:
        choice = input("\n请选择 (1/2/3/4): ").strip()

        if choice == "1":
            print("\n可用问题:")
            for i, p in enumerate(PROBLEMS, 1):
                print(f"  {i}. {p['name']}")
            idx = int(input(f"\n选择问题 (1-{len(PROBLEMS)}): ")) - 1
            test_single_problem(PROBLEMS[idx], models)

        elif choice == "2":
            batch_test(PROBLEMS, models)

        elif choice == "3":
            n = int(input(f"测试前几个问题 (1-{len(PROBLEMS)}): "))
            batch_test(PROBLEMS[:n], models, f"results_top{n}.json")

        elif choice == "4":
            demo_api_methods()

        else:
            print("无效选择")

    except (ValueError, KeyboardInterrupt, IndexError) as e:
        print(f"\n操作取消或出错: {e}")


def demo_api_methods():
    """演示不同的 API 调用方式"""
    print("\n" + "=" * 100)
    print("API 调用方式演示")
    print("=" * 100)

    test_problem = "Solve: x^2 + 5x + 6 = 0"
    print(f"\n测试问题: {test_problem}\n")

    # 方法1: OpenAI SDK 调用 GPT-4
    if USE_OPENAI_CLIENT:
        print("\n" + "─" * 100)
        print("方法1: OpenAI SDK 调用 GPT-4 (120B)")
        print("─" * 100)

        try:
            client = OpenAI(
                base_url=BASE_URL,
                api_key=OPENROUTER_API_KEY,
                default_headers={
                    "HTTP-Referer": "https://github.com",
                    "X-Title": "Math Reasoning Test",
                },
            )

            completion = client.chat.completions.create(
                model="openai/gpt-oss-120b:free",
                messages=[
                    {"role": "system", "content": "You are a helpful math tutor."},
                    {"role": "user", "content": test_problem},
                ],
                max_tokens=500,
                temperature=0.3,
            )

            message = completion.choices[0].message
            print(f"\n💬 回复:\n{message.content}")
            print(f"\n📊 Token: {completion.usage.total_tokens}")
            print(f"🔧 模型: {completion.model}")

        except Exception as e:
            print(f"❌ 错误: {e}")

    # 方法2: requests 调用 GPT-4
    print("\n" + "─" * 100)
    print("方法2: requests 调用 GPT-4 (120B)")
    print("─" * 100)

    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com",
            "X-Title": "Math Reasoning Test",
        }

        payload = {
            "model": "openai/gpt-oss-120b:free",
            "messages": [
                {"role": "system", "content": "You are a helpful math tutor."},
                {"role": "user", "content": test_problem},
            ],
            "max_tokens": 500,
            "temperature": 0.3,
        }

        response = requests.post(
            f"{BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )

        result = response.json()
        message = result["choices"][0]["message"]

        print(f"\n💬 回复:\n{message['content']}")
        print(f"\n📊 Token: {result['usage']['total_tokens']}")
        print(f"🔧 模型: {result['model']}")

    except Exception as e:
        print(f"❌ 错误: {e}")

    # 方法3: OpenAI SDK 调用 DeepSeek R1 (带思维链)
    if USE_OPENAI_CLIENT:
        print("\n" + "─" * 100)
        print("方法3: OpenAI SDK 调用 DeepSeek R1 (带思维链)")
        print("─" * 100)

        try:
            client = OpenAI(base_url=BASE_URL, api_key=OPENROUTER_API_KEY)

            completion = client.chat.completions.create(
                model="deepseek/deepseek-r1-0528:free",
                messages=[
                    {"role": "system", "content": "You are a helpful math tutor."},
                    {"role": "user", "content": test_problem},
                ],
                max_tokens=1000,
                temperature=0.3,
            )

            message = completion.choices[0].message

            # 获取思维链
            reasoning = getattr(message, "reasoning_content", None)
            if reasoning:
                print(f"\n🧠 思维链 ({len(reasoning)} 字符):\n{reasoning}")

            print(f"\n💬 最终回复:\n{message.content}")
            print(f"\n📊 Token: {completion.usage.total_tokens}")

        except Exception as e:
            print(f"❌ 错误: {e}")

    print("\n" + "=" * 100)
    print("✅ 演示完成")
    print("=" * 100)
    print("\n提示:")
    print("  - OpenAI SDK 方式代码更简洁，推荐使用")
    print("  - requests 方式无需额外依赖")
    print("  - DeepSeek R1 支持查看完整思维链")
    print(f"  - 当前使用: {'OpenAI SDK' if USE_OPENAI_CLIENT else 'requests'}")
    print(f"  - 切换方式: 编辑文件第 23 行 USE_OPENAI_CLIENT")


if __name__ == "__main__":
    main()
