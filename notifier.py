"""
CS2 Update Notifier -> Discord webhook (one-shot version for GitHub Actions)
Checks Steam news for CS2 (appid 730) once, posts anything new to Discord,
updates last_seen_gid.json, then exits. Scheduling is handled by the
GitHub Actions workflow.
"""

import os
import re
import json
import time
import requests

WEBHOOK_URL = os.environ["DISCORD_WEBHOOK_URL"]
STEAM_NEWS_URL = (
    "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
    "?appid=730&count=10&maxlength=0&feeds=steam_community_announcements"
)
STATE_FILE = "last_seen_gid.json"


def load_last_gid():
    try:
        with open(STATE_FILE) as f:
            return json.load(f).get("gid")
    except FileNotFoundError:
        return None


def save_last_gid(gid):
    with open(STATE_FILE, "w") as f:
        json.dump({"gid": gid}, f)


def clean_bbcode(text):
    text = re.sub(r"\[list\]|\[/list\]", "", text)
    text = re.sub(r"\[\*\]", "• ", text)
    text = re.sub(r"\[url=(.*?)\](.*?)\[/url\]", r"\2 (\1)", text)
    text = re.sub(r"\[/?\w+.*?\]", "", text)
    return text.strip()


def fetch_news():
    resp = requests.get(STEAM_NEWS_URL, timeout=15)
    resp.raise_for_status()
    return resp.json()["appnews"]["newsitems"]


def is_update_post(item):
    tags = item.get("tags", [])
    title = item.get("title", "").lower()
    return "patchnotes" in tags or "release notes" in title or "update" in title


def post_to_discord(item):
    body = clean_bbcode(item.get("contents", ""))
    if len(body) > 3500:
        body = body[:3500] + "\n… (truncated, see full notes via the link)"

    embed = {
        "title": item["title"],
        "url": item["url"],
        "description": body,
        "color": 0xDE9B35,
        "timestamp": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(item["date"])
        ),
        "footer": {"text": "Counter-Strike 2 • Steam News"},
    }
    payload = {"username": "CS2 Updates", "embeds": [embed]}
    resp = requests.post(WEBHOOK_URL, json=payload, timeout=15)
    resp.raise_for_status()


def main():
    last_gid = load_last_gid()
    items = [i for i in fetch_news() if is_update_post(i)]
    if not items:
        print("No update posts found in feed.")
        return

    newest = items[0]
    if newest["gid"] == last_gid:
        print("No new updates.")
        return

    if last_gid is None:
        # First ever run: don't spam history, just record where we are
        print("First run - recording current state, not posting old updates.")
    else:
        new_items = []
        for it in items:
            if it["gid"] == last_gid:
                break
            new_items.append(it)
        for it in reversed(new_items):
            post_to_discord(it)
            print(f"Posted: {it['title']}")

    save_last_gid(newest["gid"])


if __name__ == "__main__":
    main()
