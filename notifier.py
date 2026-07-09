"""
CS2 Update Notifier -> Discord webhook (one-shot version for GitHub Actions)
Checks Steam news for CS2 (appid 730) once, posts anything new to Discord,
updates last_seen_gid.json, then exits. Scheduling is handled by the
GitHub Actions workflow.
"""

import os
import re
import html
import json
import time
import requests

STEAM_NEWS_URL = (
    "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
    "?appid=730&count=10&maxlength=0&feeds=steam_community_announcements"
)
STATE_FILE = "last_seen_gid.json"

STEAM_CDN = "https://clan.cloudflare.steamstatic.com/images/"
TOKEN_RE  = re.compile(r"(\[h[1-6]\].*?\[/h[1-6]\]|\[img\]\s*.*?\s*\[/img\])", re.S)
HEADER_RE = re.compile(r"\[h[1-6]\](.*?)\[/h[1-6]\]", re.S)
IMG_RE    = re.compile(r"\[img\]\s*(.*?)\s*\[/img\]", re.S)


def load_last_gid():
    try:
        with open(STATE_FILE) as f:
            return json.load(f).get("gid")
    except FileNotFoundError:
        return None


def save_last_gid(gid):
    with open(STATE_FILE, "w") as f:
        json.dump({"gid": gid}, f)

def fetch_news():
    resp = requests.get(STEAM_NEWS_URL, timeout=15)
    resp.raise_for_status()
    return resp.json()["appnews"]["newsitems"]


def is_update_post(item):
    tags = item.get("tags", [])
    #title = item.get("title", "").lower()
    return "patchnotes" in tags # or "release notes" in title or "update" in title


def load_webhook_urls():
    raw = os.environ.get("DISCORD_WEBHOOK_URL", "")
    # Split on newlines, commas, or pipes; drop empties and stray whitespace
    return [u.strip() for u in re.split(r"[\n,|]+", raw) if u.strip()]

def _md(text):
    """BBCode body text -> Discord markdown (headers/images handled separately)."""
    text = normalize_raw(raw)

    text = re.sub(r"\[url=(.*?)\](.*?)\[/url\]", r"[\2](\1)", text, flags=re.S)
    text = re.sub(r"\[/?b\]", "**", text)
    text = re.sub(r"\[/?i\]", "*", text)
    text = text.replace("[/*]", "")
    text = re.sub(r"\[\*\]", "\n- ", text)
    text = re.sub(r"\[/?(?:list|olist)\]", "", text)
    text = re.sub(r"\[/?[a-zA-Z][^\]]*\]", "", text)   # strip whatever's left
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    text = strip_orphan_backslashes(text)

    return text.strip()

def normalize_raw(raw):
    text = html.unescape(raw)
    # normalize Steam's line endings (handles both real and literal-escaped forms)
    text = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text

def strip_orphan_backslashes(text):
    text = re.sub(r"\\(?![*_~`>\[\]()#-])", "", text)
    text = re.sub(r"\\+\s*$", "", text, flags=re.M)
    return text

def clean_patchnotes(raw):
    text = normalize_raw(raw)

    # [ SECTION ] -> bold header on its own line  (do before list/tag stripping)
    text = re.sub(r"\[\s*([A-Z0-9][A-Z0-9 &/]+?)\s*\]", r"\n\n**[ \1 ]**\n", text)

    # nested lists -> indented markdown bullets
    text = text.replace("[/*]", "")
    out, depth = [], 0
    for tok in re.split(r"(\[/?o?list\]|\[\*\])", text):
        if tok in ("[list]", "[olist]"):
            depth += 1
        elif tok in ("[/list]", "[/olist]"):
            depth = max(0, depth - 1)
        elif tok == "[*]":
            out.append("\n" + "  " * max(0, depth - 1) + "- ")
        else:
            out.append(tok)
    text = "".join(out)

    text = re.sub(r"\[url=(.*?)\](.*?)\[/url\]", r"[\2](\1)", text, flags=re.S)
    text = re.sub(r"\[/?b\]", "**", text)
    text = re.sub(r"\[/?i\]", "*", text)
    text = re.sub(r"\[/?[a-zA-Z][^\]]*\]", "", text)     # strip leftovers
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    text = strip_orphan_backslashes(text)

    return text.strip()

def chunk_text(text, limit=4000):
    if len(text) <= limit:
        return [text]
    chunks, cur = [], ""
    for block in re.split(r"(?=\n?\*\*\[ )", text):      # split at section headers
        if len(cur) + len(block) <= limit:
            cur += block
        else:
            if cur.strip():
                chunks.append(cur.strip())
            cur = block if len(block) <= limit else ""
            if len(block) > limit:                       # one huge section: split by line
                for line in block.split("\n"):
                    if len(cur) + len(line) + 1 > limit:
                        chunks.append(cur.strip()); cur = ""
                    cur += line + "\n"
    if cur.strip():
        chunks.append(cur.strip())
    return chunks

def build_patchnotes_embeds(item, color=0xDE9B35):
    chunks = chunk_text(clean_patchnotes(item.get("contents", "")))
    embeds = [{"description": c, "color": color} for c in chunks]
    embeds[0]["title"] = item["title"]
    embeds[0]["url"] = item["url"]
    if item.get("date"):
        embeds[0]["timestamp"] = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(item["date"]))
    embeds[-1]["footer"] = {"text": "Counter-Strike 2 • Steam News"}
    return embeds

def build_announcement_embeds(item, color=0xDE9B35, max_embeds=10):
     raw = item.get("contents", "")

     tokens = []
     for piece in TOKEN_RE.split(raw):
         if not piece:
             continue
         h, m = HEADER_RE.fullmatch(piece), IMG_RE.fullmatch(piece)
         if h:
             title = _md(h.group(1))
             if title:
                 tokens.append(("header", f"**{title}**"))
         elif m:
             url = m.group(1).strip().replace("{STEAM_CLAN_IMAGE}", STEAM_CDN)
             tokens.append(("image", url))
         else:
             body = _md(piece)
             if body:
                 tokens.append(("text", body))

     embeds, cur = [], {"description": ""}

     def flush():
         nonlocal cur
         if cur["description"].strip() or "image" in cur:
             cur["description"] = cur["description"].strip()[:4096]
             cur["color"] = color
             embeds.append(cur)
         cur = {"description": ""}

     for kind, val in tokens:
         if kind == "image":
             if "image" in cur:                         # one image per embed
                 flush()
             cur["image"] = {"url": val}
         elif kind == "header":
             if "image" in cur or cur["description"].strip():
                 flush()                                # header opens a fresh card
             cur["description"] = val
         else:                                          # text
             cur["description"] += ("\n\n" if cur["description"] else "") + val
     flush()

     if embeds:
         embeds[0]["title"] = item["title"]
         embeds[0]["url"] = item["url"]
         if item.get("date"):
             embeds[0]["timestamp"] = time.strftime(
                 "%Y-%m-%dT%H:%M:%SZ", time.gmtime(item["date"]))
         embeds[-1]["footer"] = {"text": "Counter-Strike 2 • Steam News"}
     return embeds[:max_embeds]

def build_embeds(item):
    if is_update_post(item):
        return build_patchnotes_embeds(item)
    return build_announcement_embeds(item)

def _send_one(url, payload, max_retries=5):
    for _ in range(max_retries):
        try:
            resp = requests.post(url, json=payload, timeout=15)
        except requests.RequestException as e:
            print(f"  request error: {e}")
            return False

        if resp.status_code in (200, 204):   # 204 = normal webhook success
            return True
        if resp.status_code == 429:           # rate limited
            retry_after = float(resp.json().get("retry_after", 1))
            print(f"  rate limited, sleeping {retry_after}s")
            time.sleep(retry_after + 0.5)
            continue
        print(f"  webhook {resp.status_code}: {resp.text[:200]}")
        return False
    return False

def batch_embeds(embeds, max_per_msg=10, max_chars=6000):
    batches, cur, chars = [], [], 0
    for e in embeds:
        elen = (len(e.get("description", "")) + len(e.get("title", ""))
                + len(e.get("footer", {}).get("text", "")))
        if cur and (len(cur) >= max_per_msg or chars + elen > max_chars):
            batches.append(cur); cur, chars = [], 0
        cur.append(e); chars += elen
    if cur:
        batches.append(cur)
    return batches

def post_to_discord(item, webhook_urls):
    embeds = build_embeds(item)
    if not embeds:
        return False
    messages = batch_embeds(embeds)
    all_ok = True
    for url in webhook_urls:
        for i, msg in enumerate(messages):
            payload = {
                "username": "CS2 Updates",
                "embeds": msg,
                "allowed_mentions": {"parse": ["everyone"]},
            }
            if i == 0:
                payload["content"] = "@here"      # ping once, not per chunk
            if not _send_one(url, payload):
                all_ok = False
                break                              # preserve order; retry next run
    return all_ok

def collect_new_items(items, last_gid, raw_items):
    """
    items:     update posts only, newest-first (what we actually post)
    raw_items: full unfiltered feed, newest-first (used to detect staleness)
    """
    if not any(it["gid"] == last_gid for it in raw_items):
        return [items[0]], True            # genuinely out of window

    new_items = []
    for it in items:
        if it["gid"] == last_gid:
            break
        new_items.append(it)
    return list(reversed(new_items)), False


def main():
    webhook_urls = load_webhook_urls()
    if not webhook_urls:
        raise SystemExit(
            "No webhook URLs configured. Set the DISCORD_WEBHOOK_URL secret "
            "(newline-, comma-, or pipe-separated)."
        )
 
    last_gid = load_last_gid()
    raw_items = fetch_news()

    items = raw_items #[i for i in raw_items if is_update_post(i)]
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

    to_post, was_stale = collect_new_items(items, last_gid, raw_items)
    #to_post, was_stale = collect_new_items(items, last_gid)
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
