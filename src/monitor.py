#!/usr/bin/env python3
"""
Football Ticket Monitor — 双轨监控
Track 1: 球队官网票务页面（HTTP状态 + 可访问性）
Track 2: X/Twitter 官方账号票务推文
数据源：各俱乐部官网 + X (@AgentReach)
通知：Telegram Bot
"""

import os
import json
import logging
import sys
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List

import requests
from bs4 import BeautifulSoup
from telegram import Bot

# ─────────────────────────────────────────
# 配置
# ─────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────
# 俱乐部配置
# ─────────────────────────────────────────
CLUBS = {
    "arsenal": {
        "name": "阿森纳",
        "name_en": "Arsenal",
        "website": "https://www.arsenal.com/tickets",
        "twitter_account": "Arsenal",
        "twitter_handle": "@Arsenal",
        "ticket_keywords": ["ticket", "sale", "on sale", "ballot", "membership", "available", "buy ticket"],
        "colors": "🔴",
    },
    "chelsea": {
        "name": "切尔西",
        "name_en": "Chelsea",
        "website": "https://www.chelseafc.com/en/all-on-sale-dates-men",
        "twitter_account": "ChelseaFC",
        "twitter_handle": "@ChelseaFC",
        "ticket_keywords": ["ticket", "sale", "on sale", "ballot", "membership", "available", "buy ticket"],
        "colors": "🔵",
    },
    "manchester_united": {
        "name": "曼联",
        "name_en": "Man Utd",
        "website": "https://www.manutd.com/tickets-and-travel/tickets",
        "twitter_account": "ManUtd",
        "twitter_handle": "@ManUtd",
        "ticket_keywords": ["ticket", "sale", "on sale", "ballot", "membership", "available", "buy ticket"],
        "colors": "🔴",
    },
    "tottenham": {
        "name": "热刺",
        "name_en": "Tottenham",
        "website": "https://www.tottenhamhotspur.com/tickets",
        "twitter_account": "SpursOfficial",
        "twitter_handle": "@SpursOfficial",
        "ticket_keywords": ["ticket", "sale", "on sale", "ballot", "membership", "available", "buy ticket"],
        "colors": "⚪",
    },
    "manchester_city": {
        "name": "曼城",
        "name_en": "Man City",
        "website": "https://www.mancity.com/tickets",
        "twitter_account": "mancityhelp",
        "twitter_handle": "@mancityhelp",
        "ticket_url": "https://x.com/mancityhelp",
        "ticket_keywords": ["ticket", "sale", "on sale", "ballot", "membership", "available", "buy ticket"],
        "colors": "🔵",
    },
    "newcastle": {
        "name": "纽卡斯尔",
        "name_en": "Newcastle",
        "website": "https://www.nufc.co.uk/tickets",
        "twitter_account": "NUFC",
        "twitter_handle": "@NUFC",
        "ticket_keywords": ["ticket", "sale", "on sale", "ballot", "membership", "available", "buy ticket"],
        "colors": "⚫⚪",
    },
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Cache-Control": "no-cache",
}
TIMEOUT = 15


# ─────────────────────────────────────────
# 通知模块
# ─────────────────────────────────────────
def send_telegram(message: str):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        log.warning("Telegram 未配置，跳过通知")
        print(f"\n[通知预览]\n{message}\n")
        return

    bot = Bot(token=bot_token)
    try:
        bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
        log.info("Telegram 通知发送成功")
    except Exception as e:
        log.error(f"Telegram 发送失败: {e}")


def build_message(web_results: dict, twitter_results: dict) -> str:
    lines = [
        f"⚽ <b>英超球票双轨监控日报</b>",
        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    for club_id, info in CLUBS.items():
        web = web_results.get(club_id, {})
        tweets = twitter_results.get(club_id, {})

        lines.append(f"\n{info['colors']} <b>{info['name']}</b> ({info['name_en']})")
        lines.append(f"   🌐 {info['website']}")

        # 官网状态
        web_status = web.get("status", "unknown")
        if web_status == "accessible":
            lines.append(f"   ✅ 官网可访问")
            if web.get("note"):
                lines.append(f"   📝 {web['note']}")
        elif web_status == "blocked":
            lines.append(f"   🔒 官网需登录/有防护")
            if web.get("note"):
                lines.append(f"   📝 {web['note']}")
        else:
            lines.append(f"   ⚠️ {web.get('note', '官网状态未知')}")

        # Twitter 票务推文
        if tweets.get("tweets"):
            lines.append(f"   🐦 <b>X/Twitter 票务动态</b>")
            for tweet in tweets["tweets"][:3]:
                lines.append(f"   🐦 {tweet['text'][:120]}")
                lines.append(f"      🔗 {tweet['url']}")
        elif tweets.get("error"):
            lines.append(f"   ❌ Twitter: {tweets['error']}")
        else:
            lines.append(f"   🐦 暂无票务推文")

    lines.append("")
    lines.append("─" * 30)
    lines.append("🤖 由 GitHub Actions 自动发送")
    lines.append("📡 Track1: 官网 | Track2: X/Twitter")

    return "\n".join(lines)


# ─────────────────────────────────────────
# Track 1: 官网票务抓取
# ─────────────────────────────────────────
def fetch_page(url: str) -> Optional[BeautifulSoup]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        return BeautifulSoup(resp.text, "lxml") if resp.status_code == 200 else None
    except requests.RequestException:
        return None


def check_arsenal() -> dict:
    url = CLUBS["arsenal"]["website"]
    log.info(f"[Arsenal] 检查官网: {url}")
    soup = fetch_page(url)
    if soup:
        return {"status": "accessible", "note": "票务页面可访问，请手动查看具体场次"}
    return {"status": "unknown", "note": "无法访问 Arsenal 官网"}


def check_chelsea() -> dict:
    url = CLUBS["chelsea"]["website"]
    log.info(f"[Chelsea] 检查官网: {url}")
    soup = fetch_page(url)
    if soup:
        page_text = soup.get_text()
        page_text_lower = page_text.lower()
        # JS渲染页面内容极少（<500字符），视为需要浏览器
        if len(page_text.strip()) < 500:
            return {
                "status": "blocked",
                "note": "Chelsea 官网为 JS 渲染，需浏览器加载。请访问 x.com/ChelseaFC 查票务动态。"
            }
        if "403" in page_text_lower or "forbidden" in page_text_lower:
            return {"status": "blocked", "note": "Chelsea 官网有 Akamai 防护，建议查看 X 票务动态"}
        return {"status": "accessible", "note": "票务页面可访问"}
    return {"status": "blocked", "note": "无法访问 Chelsea 官网，请访问 x.com/ChelseaFC"}


def check_manchester_united() -> dict:
    url = CLUBS["manchester_united"]["website"]
    log.info(f"[Man Utd] 检查官网: {url}")
    soup = fetch_page(url)
    if soup:
        page_text = soup.get_text()
        page_text_lower = page_text.lower()
        if len(page_text.strip()) < 500:
            return {
                "status": "blocked",
                "note": "Man Utd 官网为 JS 渲染，需浏览器加载。请访问 x.com/ManUtd 查票务动态。"
            }
        if "cloudflare" in page_text_lower or "turnstile" in page_text_lower:
            return {"status": "blocked", "note": "Man Utd 官网有 Cloudflare，建议查看 X 票务动态"}
        return {"status": "accessible", "note": "票务页面可访问"}
    return {"status": "blocked", "note": "无法访问 Man Utd 官网，请访问 x.com/ManUtd"}


def check_tottenham() -> dict:
    url = CLUBS["tottenham"]["website"]
    log.info(f"[Tottenham] 检查官网: {url}")
    soup = fetch_page(url)
    if soup:
        return {"status": "accessible", "note": "票务页面可访问，请手动查看具体场次"}
    return {"status": "unknown", "note": "无法访问 Tottenham 官网"}


def check_manchester_city() -> dict:
    url = CLUBS["manchester_city"]["website"]
    log.info(f"[Man City] 检查官网: {url}")
    soup = fetch_page(url)
    if soup:
        page_text = soup.get_text()
        page_text_lower = page_text.lower()
        if len(page_text.strip()) < 500:
            return {
                "status": "blocked",
                "note": "Man City 官网为 JS 渲染，需浏览器加载。请访问 x.com/mancityhelp 查票务动态。"
            }
        if "cloudflare" in page_text_lower or "403" in page_text_lower:
            return {"status": "blocked", "note": "Man City 官网有 Cloudflare，建议查看 X 票务动态"}
        return {"status": "accessible", "note": "票务页面可访问"}
    return {"status": "blocked", "note": "无法访问 Man City 官网，请访问 x.com/mancityhelp"}


def check_newcastle() -> dict:
    url = CLUBS["newcastle"]["website"]
    log.info(f"[Newcastle] 检查官网: {url}")
    soup = fetch_page(url)
    if soup:
        return {"status": "accessible", "note": "票务页面可访问，请手动查看具体场次"}
    return {"status": "unknown", "note": "无法访问 Newcastle 官网"}


# ─────────────────────────────────────────
# Track 2: X/Twitter 票务推文抓取
# ─────────────────────────────────────────
def xreach_available() -> bool:
    """检查 xreach 是否可用"""
    try:
        result = subprocess.run(
            ["xreach", "--version"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def search_twitter(account: str, keywords: list[str], club_name: str) -> dict:
    """
    用 xreach 搜索俱乐部 X 票务推文
    返回 {"tweets": [...], "error": "..."}
    """
    log.info(f"[{club_name}] 搜索 Twitter: from:{account}")

    if not xreach_available():
        return {"tweets": [], "error": "xreach 未安装或不可用"}

    all_tweets = []

    for kw in keywords[:3]:  # 每个俱乐部最多搜索3个关键词
        query = f"from:{account} {kw}"
        try:
            result = subprocess.run(
                ["xreach", "search", query, "--json"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode != 0:
                log.warning(f"[{club_name}] xreach 搜索失败 [{kw}]: {result.stderr[:100]}")
                continue

            output = result.stdout.strip()
            if not output:
                continue

            # 解析 JSONL 输出
            for line in output.split("\n"):
                if not line.strip():
                    continue
                try:
                    tweet = json.loads(line)
                    # 提取关键字段
                    tweet_text = tweet.get("text", "") or tweet.get("full_text", "")
                    if not tweet_text:
                        continue
                    tweet_id = tweet.get("id_str", tweet.get("id", ""))
                    created_at = tweet.get("created_at", "")
                    url = f"https://x.com/{account}/status/{tweet_id}" if tweet_id else ""

                    # 简单去重（按推文ID）
                    if any(t["url"] == url for t in all_tweets):
                        continue

                    all_tweets.append({
                        "text": tweet_text,
                        "url": url,
                        "created_at": created_at,
                        "keyword_used": kw,
                    })
                except (json.JSONDecodeError, KeyError) as e:
                    log.warning(f"[{club_name}] 解析推文失败: {e}")
                    continue

        except subprocess.TimeoutExpired:
            log.warning(f"[{club_name}] xreach 超时 [{kw}]")
            continue
        except Exception as e:
            log.warning(f"[{club_name}] xreach 异常 [{kw}]: {e}")
            continue

    # 按时间排序（最新优先）
    all_tweets.sort(key=lambda t: t.get("created_at", ""), reverse=True)

    # 去重（按文本内容）
    seen = set()
    unique = []
    for t in all_tweets:
        key = t["text"][:80]
        if key not in seen:
            seen.add(key)
            unique.append(t)

    return {"tweets": unique[:5], "error": None}


def search_twitter_fallback(account: str, club_name: str, info: dict) -> dict:
    """
    xreach 不可用时的降级方案：
    直接请求 X.com 页面的移动版或非 JS 版
    """
    log.info(f"[{club_name}] xreach 不可用，尝试直接抓取 X 页面")

    # 尝试抓取 X.com 的非 JS 版本
    x_urls = [
        f"https://x.com/{account}",
        f"https://x.com/{account}/with_replies",
    ]

    for x_url in x_urls:
        try:
            headers = {
                **HEADERS,
                "Accept": "text/html",
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
            }
            resp = requests.get(x_url, headers=headers, timeout=TIMEOUT, allow_redirects=True)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "lxml")
                # 尝试提取推文文本
                tweets = []
                for article in soup.select("article"):
                    text = article.get_text(strip=True)
                    if text and len(text) > 20:
                        tweets.append(text[:200])
                if tweets:
                    return {
                        "tweets": [{"text": t, "url": x_url, "created_at": "", "keyword_used": "fallback"}
                                   for t in tweets[:3]],
                        "error": None,
                    }
        except Exception:
            continue

    return {
        "tweets": [],
        "error": f"请安装 agent-reach: pipx install https://github.com/Panniantong/agent-reach/archive/main.zip"
    }


# ─────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────
def main():
    log.info("=" * 50)
    log.info("⚽ 英超球票双轨监控启动")
    log.info(f"📅 执行时间: {datetime.now().isoformat()}")
    log.info(f"🏟 监控球队: {', '.join(c['name'] for c in CLUBS.values())}")
    log.info(f"🔧 xreach 可用: {xreach_available()}")
    log.info("=" * 50)

    web_results = {}
    twitter_results = {}

    # ── Track 1: 官网检查（并行） ──
    log.info("\n── Track 1: 官网票务 ──")

    def check_all_webs():
        checkers = {
            "arsenal": check_arsenal,
            "chelsea": check_chelsea,
            "manchester_united": check_manchester_united,
            "tottenham": check_tottenham,
            "manchester_city": check_manchester_city,
            "newcastle": check_newcastle,
        }
        for club_id, checker in checkers.items():
            try:
                web_results[club_id] = checker()
                log.info(f"[{CLUBS[club_id]['name']}] Track1 完成: {web_results[club_id]['status']}")
            except Exception as e:
                log.error(f"[{CLUBS[club_id]['name']}] Track1 异常: {e}")
                web_results[club_id] = {"status": "error", "note": str(e)}

    check_all_webs()

    # ── Track 2: X/Twitter ──
    log.info("\n── Track 2: X/Twitter 票务动态 ──")

    if xreach_available():
        for club_id, info in CLUBS.items():
            twitter_results[club_id] = search_twitter(
                account=info["twitter_account"],
                keywords=info["ticket_keywords"],
                club_name=info["name"],
            )
            tweet_count = len(twitter_results[club_id].get("tweets", []))
            log.info(f"[{info['name']}] Track2 完成: {tweet_count} 条推文")
            time.sleep(2)  # 避免请求过快
    else:
        log.warning("xreach 不可用，尝试降级方案...")
        for club_id, info in CLUBS.items():
            twitter_results[club_id] = search_twitter_fallback(
                account=info["twitter_account"],
                club_name=info["name"],
                info=info,
            )

    # ── 生成通知 ──
    message = build_message(web_results, twitter_results)
    print("\n" + message + "\n")
    send_telegram(message)

    # 保存历史
    save_history(web_results, twitter_results)

    log.info("✅ 监控完成")


def save_history(web_results: dict, twitter_results: dict):
    history_dir = Path("data")
    history_dir.mkdir(exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    history_file = history_dir / f"{today}.json"
    record = {
        "date": today,
        "timestamp": datetime.now().isoformat(),
        "track1_websites": web_results,
        "track2_twitter": {
            club_id: {
                "account": CLUBS[club_id]["twitter_handle"],
                "tweets": twitter_results.get(club_id, {}).get("tweets", []),
                "error": twitter_results.get(club_id, {}).get("error"),
            }
            for club_id in CLUBS
        },
    }
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    log.info(f"📁 历史记录已保存: {history_file}")


if __name__ == "__main__":
    main()
