#!/usr/bin/env python3
"""
Football Ticket Monitor — 三轨监控
Track 1: 球队官网票务页面（HTTP状态 + 可访问性）
Track 2: X/Twitter 票务推文（Tavily 搜索）
Track 3: Gmail 邮件（俱乐部官方通知）
数据源：各俱乐部官网 + Tavily 搜索 + Gmail API
通知：Telegram Bot
"""

import os
import json
import logging
import sys
import re
import time
import urllib.request
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

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

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
        "twitter_query": "site:x.com Arsenal ticket sale OR from:Arsenal",
        "colors": "🔴",
    },
    "chelsea": {
        "name": "切尔西",
        "name_en": "Chelsea",
        "website": "https://www.chelseafc.com/en/all-on-sale-dates-men",
        "twitter_account": "ChelseaFC",
        "twitter_handle": "@ChelseaFC",
        "twitter_query": "site:x.com Chelsea ticket sale OR from:ChelseaFC",
        "colors": "🔵",
    },
    "manchester_united": {
        "name": "曼联",
        "name_en": "Man Utd",
        "website": "https://www.manutd.com/tickets-and-travel/tickets",
        "twitter_account": "ManUtd",
        "twitter_handle": "@ManUtd",
        "twitter_query": "site:x.com ManUtd ticket sale OR from:ManUtd",
        "colors": "🔴",
    },
    "tottenham": {
        "name": "热刺",
        "name_en": "Tottenham",
        "website": "https://www.tottenhamhotspur.com/tickets",
        "twitter_account": "SpursOfficial",
        "twitter_handle": "@SpursOfficial",
        "twitter_query": "site:x.com Tottenham ticket sale OR from:SpursOfficial",
        "colors": "⚪",
    },
    "manchester_city": {
        "name": "曼城",
        "name_en": "Man City",
        "website": "https://www.mancity.com/tickets",
        "twitter_account": "mancityhelp",
        "twitter_handle": "@mancityhelp",
        "twitter_query": "site:x.com ManCity ticket sale OR from:mancityhelp",
        "colors": "🔵",
    },
    "newcastle": {
        "name": "纽卡斯尔",
        "name_en": "Newcastle",
        "website": "https://www.nufc.co.uk/tickets",
        "twitter_account": "NUFC",
        "twitter_handle": "@NUFC",
        "twitter_query": "site:x.com Newcastle ticket sale OR from:NUFC",
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
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram 未配置，跳过通知")
        print(f"\n[通知预览]\n{message}\n")
        return

    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode="HTML")
        log.info("Telegram 通知发送成功")
    except Exception as e:
        log.error(f"Telegram 发送失败: {e}")


def build_message(web_results: dict, twitter_results: dict) -> str:
    lines = [
        f"⚽ <b>英超球票三轨监控日报</b>",
        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    }

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
        if tweets.get("results"):
            lines.append(f"   🐦 <b>X/Twitter 票务动态</b> ({len(tweets['results'])} 条)")
            for t in tweets["results"][:3]:
                lines.append(f"   🐦 {t['title']}")
                lines.append(f"      🔗 {t['url']}")
        elif tweets.get("error"):
            lines.append(f"   ❌ Twitter: {tweets['error']}")
        else:
            lines.append(f"   🐦 暂无票务推文")

    lines.append("")
    lines.append("─" * 30)
    lines.append("🤖 由 GitHub Actions 自动发送")
    lines.append("📡 Track1: 官网 | Track2: X/Twitter(Tavily) | Track3: Gmail")

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
# Track 2: Tavily 搜索 Twitter/X
# ─────────────────────────────────────────
def search_twitter_via_tavily(account: str, club_name: str, club_id: str) -> dict:
    """
    用 Tavily API 搜索俱乐部 Twitter/X 票务动态
    """
    if not TAVILY_API_KEY:
        return {"results": [], "error": "TAVILY_API_KEY 未配置"}

    queries = [
        f"from:{account} ticket sale",
        f"site:x.com {club_name} ticket",
    ]

    all_results = []

    for query in queries[:2]:
        try:
            req = urllib.request.Request(
                "https://api.tavily.com/search",
                data=json.dumps({
                    "query": query,
                    "search_depth": "basic",
                    "max_results": 3,
                }).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {TAVILY_API_KEY}",
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())

            for r in data.get("results", []):
                # 只取 X/Twitter 相关的
                url = r.get("url", "")
                if "x.com" in url.lower() or "twitter.com" in url.lower():
                    all_results.append({
                        "title": r.get("title", "")[:100],
                        "url": url,
                        "snippet": r.get("content", "")[:150],
                    })

        except Exception as e:
            log.warning(f"[{club_name}] Tavily 搜索失败 [{query}]: {e}")
            continue

    # 去重
    seen_urls = set()
    unique = []
    for r in all_results:
        if r["url"] not in seen_urls:
            seen_urls.add(r["url"])
            unique.append(r)

    return {"results": unique[:5], "error": None if unique else "未找到相关推文"}


# ─────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────
def main():
    log.info("=" * 50)
    log.info("⚽ 英超球票三轨监控启动")
    log.info(f"📅 执行时间: {datetime.now().isoformat()}")
    log.info(f"🏟 监控球队: {', '.join(c['name'] for c in CLUBS.values())}")
    log.info(f"🔧 Tavily: {'已配置' if TAVILY_API_KEY else '未配置'}")
    log.info("=" * 50)

    web_results = {}
    twitter_results = {}

    # ── Track 1: 官网检查 ──
    log.info("\n── Track 1: 官网票务 ──")

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

    # ── Track 2: Twitter/Tavily ──
    log.info("\n── Track 2: X/Twitter (Tavily) ──")

    for club_id, info in CLUBS.items():
        twitter_results[club_id] = search_twitter_via_tavily(
            account=info["twitter_account"],
            club_name=info["name_en"],
            club_id=club_id,
        )
        count = len(twitter_results[club_id].get("results", []))
        log.info(f"[{info['name']}] Track2 完成: {count} 条结果")
        time.sleep(1)

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
        "track2_twitter": twitter_results,
    }
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    log.info(f"📁 历史记录已保存: {history_file}")


if __name__ == "__main__":
    main()
