#!/usr/bin/env python3
"""JMU countdown bot.

Renders a daily countdown graphic and posts it to Bluesky and X.

Usage:
  python bot/countdown.py                  # render, then post to every platform with credentials set
  python bot/countdown.py --dry-run        # render and print the posts, post nothing
  python bot/countdown.py --dry-run --date 2027-02-24   # preview any day
  python bot/countdown.py --only bluesky   # post to one platform
  python bot/countdown.py --force          # post even if today's post already went out

Runs every morning at 6:00 a.m. ET from a GitLab scheduled pipeline, which
clones this GitHub repo fresh each run. This repo stays the single source of
truth for the code and for docs/config.json.

Credentials come from environment variables (GitLab CI/CD variables):
  BSKY_HANDLE, BSKY_APP_PASSWORD
  X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET
A platform with missing credentials is skipped, so Bluesky can launch before X.

Double-post guard: the run starts from a fresh copy each day, so it checks the
platforms themselves. Bluesky: skip if the account already has a post today
with today's countdown line. X: X refuses a post whose text matches an earlier
one, and the bot treats that refusal as "already posted".
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "docs" / "config.json"
STATE_PATH = ROOT / "state.json"
TODAY_PNG = ROOT / "out" / "today.png"   # docs/latest.png is the page's fixed link preview; the bot leaves it alone
FONT_DIR = ROOT / "fonts"

W, H = 1600, 900
PURPLE = (69, 0, 132)       # JMU purple #450084
PURPLE_DARK = (42, 0, 82)
GOLD = (203, 182, 119)      # JMU gold #CBB677
WHITE = (255, 255, 255)

X_MAX = 280
X_URL_WEIGHT = 23           # X counts any link as 23 characters
BSKY_MAX = 300
BSKY_LINK_LABEL = "Watch the live clock"
RETRY_WAITS = (30, 90)      # seconds between attempts after a failure; safe because of the double-post guard


# ---------------------------------------------------------------- config / dates

def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def today_in(tz: ZoneInfo, override: str | None) -> date:
    if override:
        return date.fromisoformat(override)
    return datetime.now(tz).date()


def active_countdown(cfg: dict, today: date, tz: ZoneInfo):
    """First enabled countdown whose target date is today or later (in ET)."""
    for cd in cfg["countdowns"]:
        if not cd.get("enabled", True):
            continue
        target = datetime.fromisoformat(cd["target"]).astimezone(tz)
        if target.date() >= today:
            return cd, target
    return None, None


# ---------------------------------------------------------------- text

def when_line(cd: dict, days: int) -> str:
    official = cd.get("status") == "official"
    time_label = cd["time_label_official"] if official else cd["time_label_projected"]
    if days == 0:
        return f"{'Set for' if official else 'Expected'} {time_label}."
    return f"{'Set' if official else 'Projected'}: {cd['date_label']}, {time_label}."


def lead_line(cd: dict, days: int) -> str:
    if days == 0:
        return f"{cd['today_phrase']}."
    unit = "day" if days == 1 else "days"
    return f"{days} {unit} until {cd['event_phrase']}."


def sponsor_line(cfg: dict) -> str | None:
    sp = cfg.get("sponsor")
    if not sp or not sp.get("name"):
        return None
    disclosure = sp.get("disclosure", "#ad")
    return f"Presented by {sp['name']} {disclosure}".strip()


def body_parts(cfg: dict, cd: dict, days: int, include_subhead: bool = True) -> list[str]:
    parts = [lead_line(cd, days)]
    if include_subhead and cd.get("subhead"):
        parts.append(f"{cd['subhead']}.")
    parts.append(when_line(cd, days))
    sp = sponsor_line(cfg)
    if sp:
        parts.append(sp)
    return parts


def hashtags(cfg: dict) -> list[str]:
    return [h.lstrip("#") for h in cfg.get("hashtags", []) if h.strip()]


def short_url(url: str) -> str:
    return url.replace("https://", "").replace("http://", "").rstrip("/")


def x_weighted_len(text: str, link: str) -> int:
    """Length as X counts it: the link counts as 23 characters."""
    if link and link in text:
        return len(text) - len(link) + X_URL_WEIGHT
    return len(text)


def x_text(cfg: dict, cd: dict, days: int) -> str:
    """X post, with the live-clock link (Brett's call, 2026-11-23). X bills about
    $0.20 for a post with a link vs $0.015 without; the spend cap is $10 a month."""
    url = cfg.get("site_url", "")
    link = short_url(url) if url else ""
    for include_subhead in (True, False):
        parts = body_parts(cfg, cd, days, include_subhead)
        if link:
            parts.append(f"Live clock: {link}")
        tags = " ".join(f"#{t}" for t in hashtags(cfg))
        text = "\n\n".join(parts + ([tags] if tags else []))
        if x_weighted_len(text, link) <= X_MAX:
            return text
    return text[:X_MAX]


def bsky_segments(cfg: dict, cd: dict, days: int) -> list[tuple[str, str, str | None]]:
    """Bluesky post as (kind, text, target) segments so links and tags are clickable.
    Bluesky posting is free, so the live-clock link is included."""
    url = cfg.get("site_url", "")
    for include_subhead in (True, False):
        segs: list[tuple[str, str, str | None]] = [
            ("text", "\n\n".join(body_parts(cfg, cd, days, include_subhead)), None)
        ]
        if url:
            # The words carry the link, so no web address shows in the post.
            segs.append(("text", "\n\n", None))
            segs.append(("link", BSKY_LINK_LABEL, url))
        tags = hashtags(cfg)
        if tags:
            segs.append(("text", "\n\n", None))
            for i, t in enumerate(tags):
                if i:
                    segs.append(("text", " ", None))
                segs.append(("tag", f"#{t}", t))
        if sum(len(s[1]) for s in segs) <= BSKY_MAX:
            return segs
    return segs


def plain(segs) -> str:
    return "".join(s[1] for s in segs)


def alt_text(cd: dict, days: int) -> str:
    if days == 0:
        lead = f"Today is release day for the {cd['headline']}."
    else:
        lead = f"{days} {'day' if days == 1 else 'days'} to go until the {cd['headline']}."
    return (
        f"Countdown graphic in purple and gold. {lead} "
        f"{when_line(cd, days)} Unofficial fan countdown."
    )


# ---------------------------------------------------------------- image

def font(name: str, size: int, weight: str | None = None) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT_DIR / name), size)
    if weight:
        f.set_variation_by_name(weight)
    return f


def text_w(draw: ImageDraw.ImageDraw, s: str, f, spacing: int = 0) -> int:
    if spacing:
        return sum(draw.textlength(c, font=f) for c in s) + spacing * (len(s) - 1)
    return int(draw.textlength(s, font=f))


def draw_spaced(draw, xy, s, f, fill, spacing):
    x, y = xy
    for c in s:
        draw.text((x, y), c, font=f, fill=fill)
        x += draw.textlength(c, font=f) + spacing


def fit_font(draw, s, name, start, max_w, weight=None, spacing=0):
    size = start
    while size > 10:
        f = font(name, size, weight)
        if text_w(draw, s, f, spacing) <= max_w:
            return f
        size -= 2
    return font(name, size, weight)


def render_image(cd: dict, days: int) -> bytes:
    img = Image.new("RGB", (W, H), PURPLE)
    d = ImageDraw.Draw(img)

    # subtle vertical gradient toward the bottom
    for y in range(H):
        t = max(0.0, (y - 300) / (H - 300))
        c = tuple(int(PURPLE[i] + (PURPLE_DARK[i] - PURPLE[i]) * t) for i in range(3))
        d.line([(0, y), (W, y)], fill=c)

    margin = 90
    official = cd.get("status") == "official"

    # header
    d.rectangle([margin, 64, W - margin, 68], fill=GOLD)
    kicker = "COUNTDOWN TO THE"
    fk = font("Oswald-Variable.ttf", 34, b"SemiBold")
    draw_spaced(d, ((W - text_w(d, kicker, fk, 6)) // 2, 92), kicker, fk, GOLD, 6)
    head = cd["headline"].upper()
    fh = fit_font(d, head, "Oswald-Variable.ttf", 70, W - 2 * margin, b"Bold", 2)
    draw_spaced(d, ((W - text_w(d, head, fh, 2)) // 2, 140), head, fh, WHITE, 2)

    # the number (band from y=268 to y=620)
    band_top, band_bottom = 268, 620
    if days == 0:
        big = "SCHEDULE DAY"
        fn = fit_font(d, big, "Anton-Regular.ttf", 300, W - 2 * margin)
        nb = d.textbbox((0, 0), big, font=fn)
        num_w, num_h = nb[2] - nb[0], nb[3] - nb[1]
        top = band_top + (band_bottom - band_top - num_h) // 2
        d.text(((W - num_w) // 2 - nb[0], top - nb[1]), big, font=fn, fill=GOLD)
    else:
        big, lab1, lab2 = str(days), ("DAY" if days == 1 else "DAYS"), "TO GO"
        fn = font("Anton-Regular.ttf", 400)
        fl1 = font("Oswald-Variable.ttf", 110, b"Bold")
        fl2 = font("Oswald-Variable.ttf", 54, b"Medium")
        nb = d.textbbox((0, 0), big, font=fn)
        num_w, num_h = nb[2] - nb[0], nb[3] - nb[1]
        lab_w = max(text_w(d, lab1, fl1), text_w(d, lab2, fl2, 4))
        gap = 44
        x0 = (W - (num_w + gap + lab_w)) // 2
        d.text((x0 - nb[0], band_top - nb[1]), big, font=fn, fill=GOLD)
        # labels vertically centered on the number
        l1b = d.textbbox((0, 0), lab1, font=fl1)
        l2b = d.textbbox((0, 0), lab2, font=fl2)
        l1h, l2h = l1b[3] - l1b[1], l2b[3] - l2b[1]
        ly = band_top + (num_h - (l1h + 22 + l2h)) // 2
        lx = x0 + num_w + gap
        d.text((lx - l1b[0], ly - l1b[1]), lab1, font=fl1, fill=WHITE)
        draw_spaced(d, (lx - l2b[0], ly + l1h + 22 - l2b[1]), lab2, fl2, GOLD, 4)

    # subhead
    sub = cd.get("subhead", "")
    if sub:
        fs = fit_font(d, sub, "Oswald-Variable.ttf", 44, W - 2 * margin, b"Regular")
        d.text(((W - text_w(d, sub, fs)) // 2, 662), sub, font=fs, fill=(235, 225, 245))

    # yard-line hash marks
    for x in range(margin, W - margin + 1, 30):
        tall = (x - margin) % 150 == 0
        d.rectangle([x, 752 - (10 if tall else 0), x + 2, 764], fill=(150, 120, 170) if not tall else GOLD)

    # footer strip
    d.rectangle([0, 790, W, H], fill=PURPLE_DARK)
    d.rectangle([0, 790, W, 793], fill=GOLD)
    time_label = cd["time_label_official"] if official else cd["time_label_projected"]
    label = "RELEASE SET" if official else "PROJECTED"
    foot = f"{label}  ·  {cd['date_label'].upper()}  ·  {time_label.upper()}"
    ff = fit_font(d, foot, "Oswald-Variable.ttf", 36, 1000, b"Medium", 2)
    draw_spaced(d, (margin, 822), foot, ff, GOLD, 2)
    tag = "UNOFFICIAL FAN COUNTDOWN"
    ft = font("Oswald-Variable.ttf", 26, b"Regular")
    draw_spaced(d, (W - margin - text_w(d, tag, ft, 3), 830), tag, ft, (200, 185, 215), 3)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ---------------------------------------------------------------- state

def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"posted": {}}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def already_posted(state: dict, platform: str, today: date, cd_id: str) -> bool:
    p = state.get("posted", {}).get(platform)
    return bool(p and p.get("date") == today.isoformat() and p.get("countdown") == cd_id)


# ---------------------------------------------------------------- platforms

def bsky_ready() -> bool:
    return bool(os.getenv("BSKY_HANDLE") and os.getenv("BSKY_APP_PASSWORD"))


def x_ready() -> bool:
    return all(os.getenv(k) for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"))


class AlreadyPosted(Exception):
    """The platform already has today's post."""


def bsky_posted_today(client, handle: str, lead: str, today: date, tz: ZoneInfo) -> str | None:
    """Return the URI of today's countdown post if the account already made it."""
    feed = client.get_author_feed(actor=handle, limit=15)
    for item in feed.feed:
        post = item.post
        if post.author.handle != handle:
            continue  # a repost of someone else
        rec = post.record
        text = (rec.get("text") if isinstance(rec, dict) else getattr(rec, "text", "")) or ""
        stamp = (rec.get("createdAt") if isinstance(rec, dict) else getattr(rec, "created_at", "")) or ""
        if not stamp:
            continue
        created = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if created.astimezone(tz).date() == today and text.startswith(lead):
            return post.uri
    return None


def post_bluesky(segs, png: bytes, alt: str, lead: str, today: date, tz: ZoneInfo,
                 force: bool = False) -> str:
    from atproto import Client, client_utils, models

    handle = os.environ["BSKY_HANDLE"]
    client = Client()
    client.login(handle, os.environ["BSKY_APP_PASSWORD"])
    if not force:
        try:
            existing = bsky_posted_today(client, handle, lead, today, tz)
        except Exception as e:  # noqa: BLE001
            # A failed check should not cost the day's post.
            print(f"  warning: could not read the Bluesky feed to check for today's post ({e})")
            existing = None
        if existing:
            raise AlreadyPosted(existing)
    tb = client_utils.TextBuilder()
    for kind, txt, target in segs:
        if kind == "link":
            tb.link(txt, target)
        elif kind == "tag":
            tb.tag(txt, target)
        else:
            tb.text(txt)
    resp = client.send_image(
        text=tb,
        image=png,
        image_alt=alt,
        image_aspect_ratio=models.AppBskyEmbedDefs.AspectRatio(width=W, height=H),
        langs=["en"],
    )
    return resp.uri


def _x_check(r, step: str):
    if r.status_code >= 300:
        raise RuntimeError(f"X {step} failed: HTTP {r.status_code} {r.text[:500]}")


def post_x(text: str, png: bytes, alt: str) -> str:
    from requests_oauthlib import OAuth1Session

    s = OAuth1Session(
        client_key=os.environ["X_API_KEY"],
        client_secret=os.environ["X_API_SECRET"],
        resource_owner_key=os.environ["X_ACCESS_TOKEN"],
        resource_owner_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )
    r = s.post(
        "https://api.x.com/2/media/upload",
        files={"media": ("countdown.png", png, "image/png")},
        data={"media_category": "tweet_image"},
        timeout=60,
    )
    _x_check(r, "media upload")
    media_id = r.json()["data"]["id"]

    # Alt text is optional; a failure here should not stop the post.
    try:
        m = s.post(
            "https://api.x.com/2/media/metadata",
            json={"id": media_id, "metadata": {"alt_text": {"text": alt[:1000]}}},
            timeout=30,
        )
        if m.status_code >= 300:
            print(f"  warning: X alt text not set (HTTP {m.status_code})")
    except Exception as e:  # noqa: BLE001
        print(f"  warning: X alt text not set ({e})")

    r = s.post(
        "https://api.x.com/2/tweets",
        json={"text": text, "media": {"media_ids": [media_id]}},
        timeout=30,
    )
    if r.status_code == 403 and "duplicate" in r.text.lower():
        raise AlreadyPosted("X refused a duplicate of today's post")
    _x_check(r, "post")
    return r.json()["data"]["id"]


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="render and print, post nothing")
    ap.add_argument("--date", help="pretend today is YYYY-MM-DD (testing)")
    ap.add_argument("--only", choices=["bluesky", "x"], help="post to one platform only")
    ap.add_argument("--force", action="store_true", help="post even if already posted today")
    ap.add_argument("--out", help="write the image here instead of out/today.png")
    args = ap.parse_args()

    cfg = load_config()
    tz = ZoneInfo(cfg.get("timezone", "America/New_York"))
    today = today_in(tz, args.date)
    cd, target = active_countdown(cfg, today, tz)
    if not cd:
        print(f"{today}: no active countdown. Nothing to post.")
        return 0

    days = (target.date() - today).days
    png = render_image(cd, days)
    out = Path(args.out) if args.out else TODAY_PNG
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png)

    xt = x_text(cfg, cd, days)
    segs = bsky_segments(cfg, cd, days)
    alt = alt_text(cd, days)

    print(f"{today} | countdown: {cd['id']} | days: {days} | image: {out}")
    print(f"--- X ({x_weighted_len(xt, short_url(cfg.get('site_url', '')))}/{X_MAX} as X counts it) ---\n{xt}")
    print(f"--- Bluesky ({len(plain(segs))}/{BSKY_MAX}) ---\n{plain(segs)}")
    print(f"--- Alt text ---\n{alt}")

    if args.dry_run:
        print("Dry run: nothing posted.")
        return 0

    state = load_state()
    failures = 0
    targets = [("bluesky", bsky_ready), ("x", x_ready)]
    for name, ready in targets:
        if args.only and args.only != name:
            continue
        if not ready():
            print(f"{name}: no credentials set, skipped.")
            continue
        if already_posted(state, name, today, cd["id"]) and not args.force:
            print(f"{name}: already posted today, skipped.")
            continue
        try:
            ref = None
            for attempt in range(len(RETRY_WAITS) + 1):
                try:
                    if name == "bluesky":
                        ref = post_bluesky(segs, png, alt, lead_line(cd, days), today, tz, args.force)
                    else:
                        ref = post_x(xt, png, alt)
                    break
                except AlreadyPosted:
                    raise
                except Exception as e:  # noqa: BLE001
                    if attempt == len(RETRY_WAITS):
                        raise
                    wait = RETRY_WAITS[attempt]
                    print(f"{name}: attempt {attempt + 1} failed ({e}); retrying in {wait}s")
                    time.sleep(wait)
            state.setdefault("posted", {})[name] = {
                "date": today.isoformat(),
                "countdown": cd["id"],
                "days": days,
                "ref": ref,
            }
            save_state(state)
            print(f"{name}: posted ({ref})")
        except AlreadyPosted as e:
            print(f"{name}: already posted today, skipped ({e}).")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"{name}: FAILED: {e}", file=sys.stderr)

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
