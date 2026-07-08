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


def load_webhook_urls():
    raw = os.environ.get("DISCORD_WEBHOOK_URL", "")
    # Split on newlines, commas, or pipes; drop empties and stray whitespace
    return [u.strip() for u in re.split(r"[\n,|]+", raw) if u.strip()]


def build_payload(item):
    body = clean_bbcode(item.get("contents", ""))
    if len(body) > 3500:  # Discord embed description limit is 4096
        body = body[:3500] + "\n… (truncated, see full notes via the link)"
 
    embed = {
        "title": item["title"],
        "url": item["url"],
        "description": body,
        "color": 0xDE9B35,  # CS orange
        "timestamp": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(item["date"])
        ),
        "footer": {"text": "Counter-Strike 2 • Steam News"},
    }

    return {"username": "CS2 Updates", "embeds": [embed]}


def post_to_discord(item, webhook_urls):
    """Post one item to every webhook. Returns True if at least one succeeded."""
    payload = build_payload(item)
    any_success = False
    for url in webhook_urls:
        try:
            resp = requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            any_success = True
        except Exception as e:
            print(f"Failed to post to one webhook: {e}")
    return any_success


def collect_new_items(items, last_gid):
    """
    Return the items newer than last_gid, oldest-first (ready to post in order).
 
    If last_gid isn't found in the current feed window (e.g. Actions was paused
    long enough that >10 updates shipped, or the state file is stale), we don't
    dump the whole window — we post only the single newest item and re-baseline
    from there.
    """
    new_items = []
    for it in items:
        if it["gid"] == last_gid:
            return list(reversed(new_items)), False  # found it: normal case
        new_items.append(it)
    # last_gid never matched anything in the feed.
    return [items[0]], True  # stale/out-of-window: just the newest one


def main():
    webhook_urls = load_webhook_urls()
    if not webhook_urls:
        raise SystemExit(
            "No webhook URLs configured. Set the DISCORD_WEBHOOK_URL secret "
            "(newline-, comma-, or pipe-separated)."
        )
 
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
        # First ever run: don't spam history, just record where we are.
        print("First run - recording current state, not posting old updates.")
        save_last_gid(newest["gid"])
        return
 
    to_post, was_stale = collect_new_items(items, last_gid)
    if was_stale:
        print(
            "Last seen update not in current feed window; "
            "posting only the newest item."
        )
 
    # Post oldest-first. Only advance state past items that actually delivered,
    # so a Discord/network hiccup means we retry next run instead of silently
    # skipping a patch note forever.
    highest_delivered = None
    for it in to_post:
        if post_to_discord(it, webhook_urls):
            print(f"Posted: {it['title']}")
            highest_delivered = it["gid"]
        else:
            print(f"Delivery failed for '{it['title']}'; will retry next run.")
            break  # stop so we don't skip past an item we never delivered
 
    if highest_delivered is not None:
        save_last_gid(highest_delivered)
    else:
        print("Nothing delivered; leaving state unchanged for retry.")


if __name__ == "__main__":
    main()
