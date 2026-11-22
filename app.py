import os, json, sqlite3, uuid, urllib.request, urllib.parse, random
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, request, jsonify, send_from_directory
import engine, chatbot

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.environ.get("HARMONY_DB") or ("/tmp/harmony.db" if os.environ.get("VERCEL") else os.path.join(BASE, "harmony.db"))  # Vercel only allows writing to /tmp
app = Flask(__name__, static_folder="static", static_url_path="/static")

def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row; return c

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, name TEXT, age INTEGER, sex TEXT, lang TEXT);
        CREATE TABLE IF NOT EXISTS checkins(uid TEXT, day TEXT, sleep REAL, energy INT, mood INT, stress INT,
            symptoms TEXT, context TEXT, PRIMARY KEY(uid, day));
        CREATE TABLE IF NOT EXISTS periods(uid TEXT, day TEXT, PRIMARY KEY(uid, day));
        CREATE TABLE IF NOT EXISTS labs(id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT, day TEXT, test TEXT, value REAL, ctx TEXT);
        CREATE TABLE IF NOT EXISTS tcache(k TEXT PRIMARY KEY, v TEXT);""")
init_db()

# ------------------------------------------------------------ helpers
def load_rows(uid):
    with db() as c:
        rows = c.execute("SELECT * FROM checkins WHERE uid=? ORDER BY day", (uid,)).fetchall()
    return [{"date": r["day"], "sleep": r["sleep"], "energy": r["energy"], "mood": r["mood"], "stress": r["stress"],
             "symptoms": json.loads(r["symptoms"]), "context": json.loads(r["context"])} for r in rows]

def build_state(uid):
    with db() as c:
        u = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not u: return None
        pds = [date.fromisoformat(r["day"]) for r in c.execute("SELECT day FROM periods WHERE uid=?", (uid,))]
        lab_rows = c.execute("SELECT * FROM labs WHERE uid=? ORDER BY day, id", (uid,)).fetchall()
    profile = dict(u)
    rows = load_rows(uid)
    base = engine.analyze_baseline(rows, pds, profile["sex"])
    areas = engine.score_areas(rows, base, profile["sex"])
    levels = {k: v["level"] for k, v in areas.items()}
    labs, hist = [], {}
    for r in lab_rows:   # re-evaluate in order so each result is judged against the user's PAST results only
        ctx = json.loads(r["ctx"])
        h = hist.setdefault(r["test"], [])
        res = engine.evaluate_lab(r["test"], r["value"], ctx, list(h), levels, profile["sex"])
        res["id"], res["date"] = r["id"], r["day"]
        labs.append(res); h.append(r["value"])
    return {"profile": profile, "checkins": rows, "baseline": base, "areas": areas, "labs": labs}

def today(): return date.today().isoformat()

# ------------------------------------------------------------ pages / config
@app.get("/")
def index(): return send_from_directory(os.path.join(BASE, "static"), "index.html")

@app.get("/api/config")
def config():
    return jsonify({"symptoms": {k: {"emoji": v[0], "label": v[1]} for k, v in engine.SYMPTOMS.items()},
                    "context": {k: {"emoji": v[0], "label": v[1]} for k, v in engine.CONTEXT.items()},
                    "labs": {k: {"name": v["name"], "unit": v["unit"], "ref": v["ref"]} for k, v in engine.LABS.items()}})

# ------------------------------------------------------------ users
@app.post("/api/profile")
def profile():
    d = request.json or {}
    uid = d.get("uid") or uuid.uuid4().hex[:12]
    with db() as c:
        c.execute("INSERT INTO users(id,name,age,sex,lang) VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, age=excluded.age, sex=excluded.sex, lang=excluded.lang",
                  (uid, (d.get("name") or "Friend")[:40], d.get("age") or None, d.get("sex") or "female", d.get("lang") or "en"))
    return jsonify({"uid": uid})

@app.get("/api/state")
def state():
    s = build_state(request.args.get("uid", ""))
    return (jsonify(s), 200) if s else (jsonify({"error": "no user"}), 404)

@app.post("/api/checkin")
def checkin():
    d = request.json; uid = d["uid"]; day = d.get("date") or today()
    ctx = [c for c in d.get("context", []) if c != "period"]
    with db() as c:
        c.execute("REPLACE INTO checkins VALUES(?,?,?,?,?,?,?,?)",
                  (uid, day, float(d["sleep"]), int(d["energy"]), int(d["mood"]), int(d["stress"]),
                   json.dumps(d.get("symptoms", [])), json.dumps(ctx)))
        if d.get("period_started"): c.execute("REPLACE INTO periods VALUES(?,?)", (uid, day))
    return jsonify(build_state(uid))

@app.post("/api/labs")
def add_lab():
    d = request.json; uid = d["uid"]
    ctx = d.get("ctx", {})
    with db() as c:
        # remember the other tests entered the same day so pattern rules (TSH vs FT4) can use them
        others = {r["test"]: r["value"] for r in c.execute("SELECT test,value FROM labs WHERE uid=? AND day=?", (uid, d.get("date") or today()))}
        ctx["others"] = others
        c.execute("INSERT INTO labs(uid,day,test,value,ctx) VALUES(?,?,?,?,?)", (uid, d.get("date") or today(), d["test"], float(d["value"]), json.dumps(ctx)))
    s = build_state(uid)
    return jsonify({"result": s["labs"][-1] if s["labs"] else None, "state": s})

@app.post("/api/summary")
def summary():
    s = build_state(request.json["uid"])
    flagged = [l for l in s["labs"]]
    return jsonify({"summary": engine.doctor_summary(s["profile"], s["checkins"], s["baseline"], s["areas"], flagged),
                    "plan": engine.care_plan(s["areas"], s["baseline"], s["profile"]["sex"])})

@app.post("/api/chat")
def chat():
    d = request.json
    s = build_state(d["uid"]) or {"areas": {}, "checkins": [], "labs": []}
    text, kind = chatbot.reply(d.get("message", ""), s)
    return jsonify({"reply": text, "kind": kind})

@app.post("/api/reset")
def reset():
    uid = request.json["uid"]
    with db() as c:
        for t in ("checkins", "periods", "labs"): c.execute(f"DELETE FROM {t} WHERE uid=?", (uid,))
    return jsonify({"ok": True})

@app.post("/api/delete")
def delete_all():
    uid = request.json["uid"]
    with db() as c:
        for t in ("checkins", "periods", "labs"): c.execute(f"DELETE FROM {t} WHERE uid=?", (uid,))
        c.execute("DELETE FROM users WHERE id=?", (uid,))
    return jsonify({"ok": True})

@app.post("/api/demo")
def demo():
    """3 weeks of realistic sample data with a quiet drift in the last 5 days, plus labs with context traps."""
    uid = request.json["uid"]; rnd = random.Random(7); t = date.today()
    with db() as c:
        c.execute("UPDATE users SET sex='female' WHERE id=?", (uid,))
        for t_ in ("checkins", "periods", "labs"): c.execute(f"DELETE FROM {t_} WHERE uid=?", (uid,))
        for i in range(24, -1, -1):
            day = (t - timedelta(days=i)).isoformat(); drift = i <= 5
            sleep = round(7.2 + rnd.uniform(-.5, .5) - (1.6 if drift else 0), 1)
            energy = max(1, min(5, round(4 + rnd.uniform(-.6, .6) - (1.6 if drift else 0))))
            mood = max(1, min(5, round(4 + rnd.uniform(-.6, .6) - (1.0 if drift else 0))))
            stress = max(1, min(5, round(2 + rnd.uniform(-.6, .6) + (1.8 if drift else 0))))
            sym = (["tired", "poorsleep", "hairfall"] if drift and i % 2 == 0 else (["tired", "anxious"] if drift else []))
            if i in (3, 4, 5, 6): sym.append("irregular")
            c.execute("REPLACE INTO checkins VALUES(?,?,?,?,?,?,?,?)", (uid, day, sleep, energy, mood, stress, json.dumps(sym), json.dumps(["stressday"] if drift and i % 3 == 0 else [])))
        for off in (94, 66, 38): c.execute("REPLACE INTO periods VALUES(?,?)", (uid, (t - timedelta(days=off)).isoformat()))
        L = lambda days, test, v, ctx: c.execute("INSERT INTO labs(uid,day,test,value,ctx) VALUES(?,?,?,?,?)", (uid, (t - timedelta(days=days)).isoformat(), test, v, json.dumps(ctx)))
        ok = {"fasting": True, "hour": 8}
        L(180, "tsh", 2.1, ok); L(120, "tsh", 2.3, ok); L(60, "tsh", 2.0, ok)
        L(2, "tsh", 3.6, {**ok, "biotin": True}); L(2, "ft4", 1.9, {**ok, "biotin": True})
        L(2, "cortisol", 5.2, {"fasting": True, "hour": 15, "poor_sleep": True}); L(2, "glucose", 108, {"fasting": False, "hour": 15})
    return jsonify(build_state(uid))

# ------------------------------------------------------------ translation (free MyMemory API, cached in SQLite)
def _tr_one(text, target, source="en"):
    key = f"{source}>{target}|{text}"
    with db() as c:
        r = c.execute("SELECT v FROM tcache WHERE k=?", (key,)).fetchone()
    if r: return r["v"]
    try:
        url = "https://api.mymemory.translated.net/get?" + urllib.parse.urlencode({"q": text[:480], "langpair": f"{source}|{target}"})
        with urllib.request.urlopen(url, timeout=6) as resp:
            out = json.loads(resp.read().decode())["responseData"]["translatedText"]
        if not out or "MYMEMORY WARNING" in out.upper(): return None
        with db() as c: c.execute("REPLACE INTO tcache VALUES(?,?)", (key, out))
        return out
    except Exception:
        return None

@app.post("/api/translate")
def translate():
    d = request.json; target = d.get("target", "en"); source = d.get("source", "en"); texts = d.get("texts", [])[:80]
    if target == source: return jsonify({"texts": texts, "ok": True})
    with ThreadPoolExecutor(8) as ex: res = list(ex.map(lambda t: _tr_one(t, target, source), texts))
    return jsonify({"texts": [r or t for r, t in zip(res, texts)], "ok": all(r for r in res) or not texts})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=bool(os.environ.get("DEBUG")))
