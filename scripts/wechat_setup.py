#!/usr/bin/env python3
"""微信公众号配置辅助脚本 - 获取 access_token 和 OpenID"""

import os
import sys
import requests

def get_access_token(app_id: str, app_secret: str) -> str:
    """获取 access_token"""
    url = (
        "https://api.weixin.qq.com/cgi-bin/token"
        f"?grant_type=client_credential&appid={app_id}&secret={app_secret}"
    )
    resp = requests.get(url, timeout=10)
    data = resp.json()

    if "access_token" in data:
        return data["access_token"]
    else:
        print(f"错误: {data}")
        sys.exit(1)


def get_followers(access_token: str) -> list:
    """获取关注者列表"""
    url = f"https://api.weixin.qq.com/cgi-bin/user/get?access_token={access_token}"
    resp = requests.get(url, timeout=10)
    data = resp.json()

    if "data" in data and "openid" in data["data"]:
        return data["data"]["openid"]
    else:
        print(f"错误: {data}")
        return []


def get_user_info(access_token: str, openid: str) -> dict:
    """获取用户信息"""
    url = (
        f"https://api.weixin.qq.com/cgi-bin/user/info"
        f"?access_token={access_token}&openid={openid}&lang=zh_CN"
    )
    resp = requests.get(url, timeout=10)
    return resp.json()


def main():
    print("=" * 50)
    print("微信公众号配置辅助工具")
    print("=" * 50)

    # 获取配置
    app_id = os.getenv("WECHAT_APP_ID") or input("请输入 AppID: ").strip()
    app_secret = os.getenv("WECHAT_APP_SECRET") or input("请输入 AppSecret: ").strip()

    if not app_id or not app_secret:
        print("错误: AppID 和 AppSecret 不能为空")
        sys.exit(1)

    # 获取 access_token
    print("\n[1/3] 获取 access_token...")
    token = get_access_token(app_id, app_secret)
    print(f"✅ access_token: {token[:20]}...")

    # 获取关注者列表
    print("\n[2/3] 获取关注者列表...")
    followers = get_followers(token)
    print(f"✅ 共有 {len(followers)} 个关注者")

    if not followers:
        print("\n⚠️ 没有关注者，请先关注公众号")
        sys.exit(0)

    # 显示关注者信息
    print("\n[3/3] 关注者信息:")
    print("-" * 50)

    for i, openid in enumerate(followers[:10], 1):  # 最多显示10个
        info = get_user_info(token, openid)
        nickname = info.get("nickname", "未知")
        subscribe_time = info.get("subscribe_time", 0)

        print(f"{i}. {nickname}")
        print(f"   OpenID: {openid}")
        print()

    # 生成配置
    print("=" * 50)
    print("复制以下配置到 config/config.yaml:")
    print("=" * 50)
    print(f"""
notification:
  enabled: true
  provider: wechat
  top_k: 5
  use_rich_format: true
  include_abstract: false

  wechat:
    app_id: "{app_id}"
    app_secret: "{app_secret}"
    open_id: "{followers[0]}"  # 第一个关注者
""")


if __name__ == "__main__":
    main()
