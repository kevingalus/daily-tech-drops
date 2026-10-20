"""Weekly performance report: how each post and lane did over the last 7 days.

Writes reports/<date>.md (the Sunday research reads the latest one to pick next week's
products) and keeps a follower history in state/insights.json for week-over-week change.
"""

from collections import defaultdict
from datetime import datetime, timedelta

from . import instagram
from .config import EASTERN, ROOT, load_all_weeks, read_state, write_state

REPORTS_DIR = ROOT / "reports"
POST_METRICS = ["reach", "views", "likes", "comments", "saved", "shares", "total_interactions"]
REEL_METRICS = POST_METRICS + ["ig_reels_avg_watch_time"]
ACCOUNT_METRICS = ["reach", "views", "accounts_engaged", "total_interactions", "profile_links_taps"]


def build(days: int = 7) -> tuple[str, str]:
    """Returns (title, markdown)."""
    until = datetime.now(EASTERN)
    since = until - timedelta(days=days)
    history = read_state("history", [])
    by_media = {m: h for h in history for m in h.get("media_ids", [])}
    lanes = {i["id"]: i.get("lane") for i in load_all_weeks()}

    rows = []
    for media in instagram.media_since(since):
        reel = media.get("media_product_type") == "REELS"
        stats = instagram.media_insights(media["id"], REEL_METRICS if reel else POST_METRICS)
        post = by_media.get(media["id"], {})
        reach = stats.get("reach", 0)
        rows.append({
            "name": (post.get("name") or _snippet(media.get("caption", ""))).replace("|", "/"),
            "lane": lanes.get(post.get("id")) or "other",
            "kind": "Reel" if reel else {"CAROUSEL_ALBUM": "Carousel", "IMAGE": "Photo"}.get(media.get("media_type"), "Post"),
            "when": instagram._ts(media["timestamp"]).astimezone(EASTERN),
            "url": media.get("permalink", ""),
            "reach": reach,
            "views": stats.get("views", 0),
            "saves": stats.get("saved", 0),
            "shares": stats.get("shares", 0),
            "interactions": stats.get("total_interactions", media.get("like_count", 0) + media.get("comments_count", 0)),
            "watch_s": stats.get("ig_reels_avg_watch_time", 0) / 1000,
            "dms": post.get("dms", 0),
        })
    for r in rows:
        r["eng"] = r["interactions"] / r["reach"] if r["reach"] else 0

    acct = instagram.account()
    totals = instagram.account_insights(ACCOUNT_METRICS, since, until)
    followers = acct.get("followers_count", 0)
    snapshots = read_state("insights", [])
    previous = snapshots[-1]["followers"] if snapshots else None
    snapshots.append({"date": f"{until:%Y-%m-%d}", "followers": followers, **totals})
    write_state("insights", snapshots[-52:])

    title = f"Weekly report: {since:%b %d} to {until:%b %d}"
    md = [f"## {title}\n"]
    change = f" ({followers - previous:+d} this week)" if previous is not None else ""
    md.append(f"**Followers:** {followers}{change}  ")
    md.append(f"**Posts:** {len(rows)}  ·  **Link DMs sent:** {sum(r['dms'] for r in rows)}  ")
    md.append(
        f"**Accounts reached:** {totals.get('reach', 0):,.0f}  ·  **Views:** {totals.get('views', 0):,.0f}  ·  "
        f"**Engaged:** {totals.get('accounts_engaged', 0):,.0f}  ·  **Bio link taps:** {totals.get('profile_links_taps', 0):,.0f}\n"
    )
    if not rows:
        md.append("No posts in the last 7 days.")
        return title, "\n".join(md) + "\n"

    # Link DMs are the closest thing to a sale we can see, so they rank first.
    ranked = sorted(rows, key=lambda r: (r["dms"], r["saves"] + r["shares"], r["reach"]), reverse=True)
    md.append("### Posts, best first\n")
    md.append("| Post | Type | Reach | Views | Saves | Shares | Eng. | Watch | Link DMs |")
    md.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for r in ranked:
        watch = f"{r['watch_s']:.1f}s" if r["watch_s"] else ""
        md.append(
            f"| [{r['name']}]({r['url']}) {r['when']:%a %-I:%M%p} | {r['kind']} | {r['reach']:,.0f} | {r['views']:,.0f} "
            f"| {r['saves']:.0f} | {r['shares']:.0f} | {r['eng']:.1%} | {watch} | {r['dms']} |"
        )

    by_lane = defaultdict(list)
    for r in rows:
        by_lane[r["lane"]].append(r)
    md.append("\n### By lane\n")
    md.append("| Lane | Posts | Avg reach | Avg eng. | Link DMs |")
    md.append("| --- | ---: | ---: | ---: | ---: |")
    lane_rows = sorted(by_lane.items(), key=lambda kv: (sum(r["dms"] for r in kv[1]), _avg(kv[1], "reach")), reverse=True)
    for lane, items in lane_rows:
        md.append(f"| {lane} | {len(items)} | {_avg(items, 'reach'):,.0f} | {_rate(items):.1%} | {sum(r['dms'] for r in items)} |")

    best, worst = ranked[0], ranked[-1]
    md.append("\n### For next week's picks\n")
    md.append(f"- Best post: **{best['name']}** ({best['lane']}).")
    if len(ranked) > 1:
        md.append(f"- Weakest post: **{worst['name']}** ({worst['lane']}).")
    if lane_rows[0][0] != "other":
        md.append(f"- Strongest lane: **{lane_rows[0][0]}**. Lean into it next week while keeping the mix varied.")
    return title, "\n".join(md) + "\n"


def run() -> str:
    title, md = build()
    REPORTS_DIR.mkdir(exist_ok=True)
    (REPORTS_DIR / f"{datetime.now(EASTERN):%Y-%m-%d}.md").write_text(md)
    (REPORTS_DIR / "latest.md").write_text(md)
    print(md)
    return title


def _avg(items: list[dict], key: str) -> float:
    return sum(i[key] for i in items) / len(items) if items else 0


def _rate(items: list[dict]) -> float:
    """Engagement over the lane's total reach, so a post seen by 3 people cannot skew it."""
    reach = sum(i["reach"] for i in items)
    return sum(i["interactions"] for i in items) / reach if reach else 0


def _snippet(caption: str) -> str:
    first = caption.strip().splitlines()[0] if caption.strip() else "Untitled post"
    return (first[:40] + "...") if len(first) > 40 else first
