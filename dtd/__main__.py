"""Command line entry point.

  python -m dtd render  --week weeks/2026-10-26.yaml   render every product in a week -> output/<id>/
  python -m dtd preview --week weeks/2026-10-26.yaml   print a markdown preview of the week
  python -m dtd post-due                               post the next product whose time has come
  python -m dtd reply                                  DM the link to anyone who commented the keyword
  python -m dtd report                                 write the weekly performance report to reports/
  python -m dtd refresh-token                          print a refreshed Instagram token
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from . import instagram, report
from .carousel import render_carousel
from .config import EASTERN, OUTPUT_DIR, affiliate_link, env, load_all_weeks, load_config, load_week, read_state, write_state
from .reel import render_reel
from .writer import full_caption, write_content

# A post whose time passed longer ago than this is skipped rather than posted late.
STALE_AFTER = timedelta(hours=6)


def render(cfg: dict, week: Path) -> int:
    for item in load_week(week):
        out = OUTPUT_DIR / item["id"]
        content = write_content(cfg, item)
        reel = render_reel(cfg, content, out / "work")
        reel.rename(out / "reel.mp4")
        slides = render_carousel(cfg, content, out)
        link = affiliate_link(cfg, item["asin"])
        draft = {
            "id": item["id"],
            "slot": item["when"].isoformat(),
            "name": item["name"],
            "asin": item["asin"],
            "lane": item.get("lane"),
            "link": link,
            "caption": full_caption(cfg, content),
            "dm_message": content.dm_message.replace("{link}", link),
            "slides": [p.name for p in slides],
        }
        (out / "draft.json").write_text(json.dumps(draft, indent=2))
        shutil.rmtree(out / "work")
        print(f"Rendered {item['id']}: {item['name']}")
    return 0


def preview(cfg: dict, week: Path, base: str) -> int:
    print(f"### Week of {week.stem}\n")
    print("Merging this pull request approves every post below.\n")
    for item in load_week(week):
        raw = f"{base}/{item['id']}"
        # GitHub's raw links download instead of playing on phones; jsDelivr streams the same file.
        phone = f"https://cdn.jsdelivr.net/gh/{os.environ.get('GITHUB_REPOSITORY', '')}@media/{item['id']}/reel.mp4"
        print(f"**{item['when']:%a %b %d, %-I:%M %p} ET: {item['name']}**  ")
        print(f"[Watch on phone]({phone}) · [Reel file]({raw}/reel.mp4) · [Amazon](https://www.amazon.com/dp/{item['asin']})\n")
        print(f'<img src="{raw}/slide_1.jpg" width="200"> <img src="{raw}/slide_2.jpg" width="200">\n')
    return 0


def post_due(cfg: dict) -> int:
    if not (env("IG_USER_ID") and env("IG_ACCESS_TOKEN")):
        print("Instagram secrets not set yet; skipping.")
        return 0
    now = datetime.now(EASTERN)
    history = read_state("history", [])
    posted = {h["id"] for h in history}
    due = sorted((i for i in load_all_weeks() if i["id"] not in posted and i["when"] <= now), key=lambda i: i["when"])
    for item in due:
        if now - item["when"] > STALE_AFTER:
            print(f"Skipping {item['id']}: its time passed more than {STALE_AFTER} ago")
            history.append({"id": item["id"], "skipped": True})
            continue
        _publish(item["id"], history)
        break  # one product per run keeps posts spaced out if several are due
    else:
        print("Nothing due.")
    write_state("history", history)
    return 0


def _publish(item_id: str, history: list) -> None:
    out = OUTPUT_DIR / item_id
    if not out.exists():
        # Rendered media lives on the media branch; pull just this product's folder.
        OUTPUT_DIR.mkdir(exist_ok=True)
        archive = subprocess.run(["git", "archive", "origin/media", item_id], capture_output=True, check=True)
        subprocess.run(["tar", "-x", "-C", str(OUTPUT_DIR)], input=archive.stdout, check=True)
    draft = json.loads((out / "draft.json").read_text())
    reel_id = instagram.publish_reel(out / "reel.mp4", draft["caption"])
    base = env("MEDIA_BASE_URL") or f"https://raw.githubusercontent.com/{os.environ.get('GITHUB_REPOSITORY', '')}/media"
    carousel_id = None
    try:
        carousel_id = instagram.publish_carousel([f"{base}/{item_id}/{s}" for s in draft["slides"]], draft["caption"])
    except instagram.InstagramError as e:
        # The reel is the main post; a failed carousel should not undo it.
        print(f"Carousel failed, reel is live: {e}", file=sys.stderr)
    history.append({
        "id": item_id, "asin": draft["asin"], "name": draft["name"], "link": draft["link"],
        "dm_message": draft["dm_message"], "media_ids": [m for m in (reel_id, carousel_id) if m],
    })
    print(f"Published {item_id}: reel {reel_id}, carousel {carousel_id}")


def reply(cfg: dict) -> int:
    if not (env("IG_USER_ID") and env("IG_ACCESS_TOKEN")):
        # Runs every 30 minutes; stay quiet until Instagram is connected.
        print("Instagram secrets not set yet; skipping.")
        return 0
    keyword = cfg["instagram"]["comment_keyword"].lower()
    handle = cfg["brand"]["handle"].lower()
    history = read_state("history", [])
    by_media = {m: h for h in history for m in h.get("media_ids", [])}
    replied = set(read_state("replied", []))
    sent = 0
    for media in instagram.recent_media(days=7):
        post = by_media.get(media["id"])
        if not post:
            continue
        for c in instagram.comments(media["id"]):
            if c["id"] in replied or c.get("username", "").lower() == handle:
                continue
            if re.search(rf"\b{re.escape(keyword)}\b", c.get("text", "").lower()):
                try:
                    instagram.private_reply(c["id"], post["dm_message"])
                    instagram.public_reply(c["id"], "Sent! Check your DMs.")
                    sent += 1
                    post["dms"] = post.get("dms", 0) + 1  # counted for the weekly report
                except instagram.InstagramError as e:
                    print(f"Reply to {c['id']} failed: {e}", file=sys.stderr)
                    continue
                replied.add(c["id"])
    write_state("replied", sorted(replied))
    write_state("history", history)
    print(f"Sent {sent} link DMs")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="dtd")
    parser.add_argument("command", choices=["render", "preview", "post-due", "reply", "report", "refresh-token"])
    parser.add_argument("--week", type=Path)
    parser.add_argument("--base", default="", help="media URL base for preview links")
    args = parser.parse_args()
    cfg = load_config()
    if args.command == "render":
        return render(cfg, args.week)
    if args.command == "preview":
        return preview(cfg, args.week, args.base)
    if args.command == "post-due":
        return post_due(cfg)
    if args.command == "reply":
        return reply(cfg)
    if args.command == "report":
        if not (env("IG_USER_ID") and env("IG_ACCESS_TOKEN")):
            print("Instagram secrets not set yet; skipping.")
            return 1
        report.run()
        return 0
    print(instagram.refresh_token())
    return 0


if __name__ == "__main__":
    sys.exit(main())
