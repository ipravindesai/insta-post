"""Instagram daily 'Day N' auto poster (post + story).

python post.py run      -> post + story (MODE: auto / now / dry)
python post.py refresh  -> Instagram token refresh
"""
import os, sys, json, time, datetime as dt, subprocess
import requests
from PIL import Image, ImageDraw, ImageFont

# ---------------- SETTINGS ----------------
START_DATE = dt.date(2026, 10, 9)   # is date ko Day 75
START_DAY = 75
POST_HOUR, POST_MIN = 23, 4         # roz 11:04 PM IST
CAPTION = ""                        # post ka caption (khali = no caption)
FONT_FILE = "font.ttf"
CAP_H, TARGET_W71, BASE_Y, CENTER_X = 74, 214, 797, 541.5  # Day 71 image se naapa
STATE_FILE = "state.json"
# ------------------------------------------

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
API = "https://graph.instagram.com/v21.0"
BRANCH = os.environ.get("GITHUB_REF_NAME", "main")


def now():
    return dt.datetime.now(IST)


def day_key():
    # 6 ghante ka buffer: subah 6 baje tak wahi "din" maana jata hai
    return (now() - dt.timedelta(hours=6)).date()


def today_day():
    return START_DAY + (day_key() - START_DATE).days


# ---------- image ----------
def ink_box(font, text):
    m = Image.new("L", (2400, 900), 0)
    ImageDraw.Draw(m).text((20, 600), text, font=font, fill=255, anchor="ls")
    return m, m.getbbox()


def make(n):
    os.makedirs("out", exist_ok=True)
    img = Image.open("template.png").convert("RGB")
    font = ImageFont.truetype(FONT_FILE, 400)
    ky = CAP_H / (-font.getbbox("D", anchor="ls")[1])
    _, b71 = ink_box(font, "Day 71")
    kx = TARGET_W71 / (b71[2] - b71[0])
    mask, bb = ink_box(font, f"Day {n}")
    mask = mask.crop(bb)
    w, h = round(mask.width * kx), round(mask.height * ky)
    mask = mask.resize((w, h), Image.LANCZOS)
    top = BASE_Y - round((600 - bb[1]) * ky) + 1
    img.paste((255, 255, 255), (round(CENTER_X - w / 2), top), mask)
    img.save(f"out/day{n}_story.jpg", quality=95)
    img.crop((0, 285, 1080, 1635)).save(f"out/day{n}_post.jpg", quality=95)  # feed 4:5
    print("images ready: Day", n)


# ---------- git ----------
def sh(*a):
    return subprocess.run(a, capture_output=True, text=True)


def git_push(paths, msg):
    sh("git", "config", "user.name", "bot")
    sh("git", "config", "user.email", "bot@users.noreply.github.com")
    sh("git", "add", *paths)
    if sh("git", "diff", "--cached", "--quiet").returncode == 0:
        print("git: koi naya change nahi")
        return
    sh("git", "commit", "-m", msg)
    for i in range(8):
        a = sh("git", "pull", "--rebase", "origin", BRANCH)
        b = sh("git", "push", "origin", f"HEAD:{BRANCH}") if a.returncode == 0 else a
        if b.returncode == 0:
            print("git: pushed")
            return
        print("git retry", i, (b.stderr or "")[-200:])
        time.sleep(5 + 3 * i)
    raise SystemExit("git push fail")


def git_sync():
    sh("git", "pull", "--rebase", "origin", BRANCH)


# ---------- state ----------
def load_state():
    try:
        return json.load(open(STATE_FILE))
    except Exception:
        return {}


def save_state(s):
    json.dump(s, open(STATE_FILE, "w"))


# ---------- instagram ----------
def raw_url(name):
    return f"https://raw.githubusercontent.com/{os.environ['GITHUB_REPOSITORY']}/{BRANCH}/out/{name}"


def wait_url(url):
    for _ in range(24):
        try:
            if requests.get(url, timeout=30).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(10)
    raise SystemExit("Image URL khul nahi rahi (repo Public hai?): " + url)


def check_token(token):
    r = requests.get(f"{API}/me", params={"fields": "username", "access_token": token}, timeout=60)
    if not r.ok:
        raise SystemExit("IG_TOKEN kharab ya expire: " + r.text)
    print("Instagram account:", r.json().get("username"))


def create_container(token, image_url, story, caption=""):
    uid = os.environ.get("IG_USER_ID", "me")
    data = {"image_url": image_url, "access_token": token}
    if story:
        data["media_type"] = "STORIES"
    elif caption:
        data["caption"] = caption
    cid = None
    for _ in range(6):
        r = requests.post(f"{API}/{uid}/media", data=data, timeout=60)
        if r.ok:
            cid = r.json()["id"]
            break
        print("create retry:", r.status_code, r.text)
        time.sleep(15)
    if not cid:
        raise SystemExit("container create fail")
    for _ in range(30):
        s = requests.get(f"{API}/{cid}", params={"fields": "status_code", "access_token": token}, timeout=60).json()
        print("status:", s)
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") in ("ERROR", "EXPIRED"):
            raise SystemExit("container error: " + str(s))
        time.sleep(5)
    return cid


def publish_container(token, cid, label):
    uid = os.environ.get("IG_USER_ID", "me")
    for _ in range(6):
        r = requests.post(f"{API}/{uid}/media_publish", data={"creation_id": cid, "access_token": token}, timeout=60)
        if r.ok:
            print("PUBLISHED", label, r.json(), now().strftime("%H:%M:%S"))
            return True
        print("publish retry:", label, r.status_code, r.text)
        time.sleep(10)
    return False


def sleep_until(target):
    while True:
        left = (target - now()).total_seconds()
        if left <= 0:
            return
        time.sleep(min(left, 30))


# ---------- main ----------
def run():
    token = os.environ["IG_TOKEN"]
    mode = (os.environ.get("MODE") or "auto").strip()  # auto / now / dry
    key, n = str(day_key()), today_day()
    print(f"Day {n} | din {key} | mode {mode} | abhi {now():%Y-%m-%d %H:%M:%S} IST")
    check_token(token)
    st = load_state()
    if st.get("post") == key and st.get("story") == key:
        print("Aaj ka Day pehle hi post+story ho chuka hai. Kuch nahi karna.")
        return
    target = dt.datetime.combine(day_key(), dt.time(POST_HOUR, POST_MIN), IST)
    if mode == "auto" and (target - now()).total_seconds() > 6.5 * 3600:
        print("Abhi post time se bahut pehle hai, skip. Shaam wala run 11:04 PM pe post karega.")
        return
    make(n)
    git_push(["out"], f"images day {n}")
    pu, su = raw_url(f"day{n}_post.jpg"), raw_url(f"day{n}_story.jpg")
    wait_url(pu)
    wait_url(su)
    if mode == "dry":
        print(f"DRY OK: Day {n} ke liye sab theek hai. (Kuch post nahi kiya)")
        return
    pc = create_container(token, pu, False, CAPTION)
    sc = create_container(token, su, True)
    if mode == "auto":
        left = (target - now()).total_seconds()
        if left > 0:
            print(f"{left/60:.0f} minute ruk ke {POST_HOUR}:{POST_MIN:02d} IST pe post karungi")
            sleep_until(target)
    git_sync()                       # kisi aur run ne beech me post kiya ho to dekh lo
    st = load_state()
    ok = True
    if st.get("post") != key:
        if publish_container(token, pc, "post"):
            st["post"] = key
            save_state(st)
        else:
            ok = False
    if st.get("story") != key:
        if publish_container(token, sc, "story"):
            st["story"] = key
            save_state(st)
        else:
            ok = False
    git_push([STATE_FILE], f"state {key}")
    if not ok:
        raise SystemExit("Kuch publish nahi hua, backup run dobara try karega")


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
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    if cmd == "make":
        make(int(sys.argv[2]) if len(sys.argv) > 2 else today_day())
    else:
        {"run": run, "refresh": refresh}[cmd]()
