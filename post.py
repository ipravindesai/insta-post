"""Instagram daily 'Day N' auto poster (post + story).
Usage:  python post.py make      -> out/ me images banati hai
        python post.py publish   -> Instagram pe post + story karti hai
        python post.py refresh   -> token refresh (60 din ka timer reset)
"""
import os, sys, time, datetime as dt, subprocess
import requests
from PIL import Image, ImageDraw, ImageFont

# ---------- SETTINGS (yahan badal sakte ho) ----------
START_DATE = dt.date(2026, 10, 6)   # is date ko Day 72 hai
START_DAY = 72
CAPTION = ""                        # post ka caption (khali = no caption)
FONT_FILE = "font.ttf"              # apna font daalna ho to isi naam se replace karo
# Day 71 image se naapa hua: text ka size/jagah
CAP_H, TARGET_W71, BASE_Y, CENTER_X = 74, 214, 797, 541.5
# ------------------------------------------------------

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
API = "https://graph.instagram.com/v21.0"


def today_day():
    # 3 ghante ka buffer: GitHub late chale (12 ke baad) tab bhi sahi din aaye
    d = (dt.datetime.now(IST) - dt.timedelta(hours=3)).date()
    return START_DAY + (d - START_DATE).days


def ink_box(font, text, size_pad=1200):
    m = Image.new("L", (size_pad * 2, 900), 0)
    ImageDraw.Draw(m).text((20, 600), text, font=font, fill=255, anchor="ls")
    return m, m.getbbox()


def make(n):
    os.makedirs("out", exist_ok=True)
    img = Image.open("template.png").convert("RGB")
    font = ImageFont.truetype(FONT_FILE, 400)
    cap = -font.getbbox("D", anchor="ls")[1]
    ky = CAP_H / cap
    _, b71 = ink_box(font, "Day 71")
    kx = TARGET_W71 / (b71[2] - b71[0])
    mask, bb = ink_box(font, f"Day {n}")
    mask = mask.crop(bb)
    w, h = round(mask.width * kx), round(mask.height * ky)
    mask = mask.resize((w, h), Image.LANCZOS)
    top = BASE_Y - round((600 - bb[1]) * ky) + 1
    x = round(CENTER_X - w / 2)
    img.paste((255, 255, 255), (x, top), mask)
    img.save(f"out/day{n}_story.jpg", quality=95)
    # Feed post me 9:16 allowed nahi, isliye beech se 4:5 crop
    img.crop((0, 285, 1080, 1635)).save(f"out/day{n}_post.jpg", quality=95)
    print("made Day", n)


def raw_url(name):
    repo = os.environ["GITHUB_REPOSITORY"]
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    return f"https://raw.githubusercontent.com/{repo}/{branch}/out/{name}"


def create_and_publish(token, image_url, story, caption=""):
    uid = os.environ.get("IG_USER_ID", "me")
    data = {"image_url": image_url, "access_token": token}
    if story:
        data["media_type"] = "STORIES"
    elif caption:
        data["caption"] = caption
    cid = None
    for _ in range(6):  # image URL live hone ka thoda wait
        r = requests.post(f"{API}/{uid}/media", data=data, timeout=60)
        if r.ok:
            cid = r.json()["id"]
            break
        print("create retry:", r.text)
        time.sleep(15)
    if not cid:
        raise SystemExit("container create fail")
    for _ in range(20):
        s = requests.get(f"{API}/{cid}", params={"fields": "status_code", "access_token": token}, timeout=60).json()
        if s.get("status_code") == "FINISHED":
            break
        time.sleep(5)
    r = requests.post(f"{API}/{uid}/media_publish", data={"creation_id": cid, "access_token": token}, timeout=60)
    r.raise_for_status()
    print("published", "story" if story else "post", r.json())


def publish(n):
    token = os.environ["IG_TOKEN"]
    create_and_publish(token, raw_url(f"day{n}_post.jpg"), False, CAPTION)
    create_and_publish(token, raw_url(f"day{n}_story.jpg"), True)


def refresh():
    token = os.environ["IG_TOKEN"]
    r = requests.get("https://graph.instagram.com/refresh_access_token",
                     params={"grant_type": "ig_refresh_token", "access_token": token}, timeout=60)
    if not r.ok:
        print("refresh skip:", r.text)
        return
    new = r.json()["access_token"]
    if os.environ.get("GH_TOKEN"):
        subprocess.run(["gh", "secret", "set", "IG_TOKEN", "--body", new,
                        "--repo", os.environ["GITHUB_REPOSITORY"]], check=True)
        print("token refreshed + secret updated")


if __name__ == "__main__":
    cmd = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else today_day()
    {"make": lambda: make(n), "publish": lambda: publish(n), "refresh": refresh}[cmd]()
