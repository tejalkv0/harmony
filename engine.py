"""Harmony engine: Personal Hormone Baseline + Hormonal Context Conflict Detection.
Pure Python (no ML libraries) so it runs anywhere, and every decision is explainable."""
from statistics import median, mean, pstdev
from datetime import date

# ---------------------------------------------------------------- vocab
AREAS = {
    "thyroid": {"icon": "🔥", "name": "Energy & body speed", "tech": "thyroid"},
    "stress":  {"icon": "🌙", "name": "Stress & sleep",      "tech": "cortisol"},
    "sex":     {"icon": "🌸", "name": "Periods & body balance", "tech": "sex hormones / PCOS signs"},
    "sugar":   {"icon": "🍬", "name": "Blood sugar & hunger", "tech": "insulin"},
}
# symptom -> (emoji, plain label, {area: weight})
SYMPTOMS = {
    "tired":        ("😴", "Tired all the time", {"thyroid": 2, "stress": 1, "sugar": 1}),
    "cold":         ("🥶", "Feeling cold easily", {"thyroid": 3}),
    "hairfall":     ("💇", "Hair falling more", {"thyroid": 2, "sex": 2}),
    "weightgain":   ("⚖️", "Weight going up", {"thyroid": 2, "sex": 2, "sugar": 1, "stress": 1}),
    "constipation": ("🚽", "Constipation", {"thyroid": 2}),
    "dryskin":      ("🧴", "Very dry skin", {"thyroid": 2}),
    "palpitations": ("💓", "Racing heart", {"thyroid": 2, "stress": 1}),
    "anxious":      ("😟", "Worried / anxious", {"stress": 3, "thyroid": 1}),
    "poorsleep":    ("🌃", "Can't sleep well", {"stress": 3}),
    "bellyfat":     ("🍩", "Belly fat increasing", {"stress": 2, "sugar": 1}),
    "acne":         ("🔴", "New pimples", {"sex": 3}),
    "facialhair":   ("🪒", "Extra face/body hair", {"sex": 3}),
    "irregular":    ("📅", "Irregular periods", {"sex": 3}),
    "heavyperiod":  ("🩸", "Very heavy periods", {"sex": 2, "thyroid": 1}),
    "moodswings":   ("🎭", "Mood swings", {"sex": 2, "stress": 1}),
    "thirst":       ("💧", "Very thirsty / urinating a lot", {"sugar": 3}),
    "cravings":     ("🍰", "Sweet cravings", {"sugar": 3, "stress": 1}),
    "darkpatches":  ("🟤", "Dark patches on neck", {"sugar": 3, "sex": 1}),
    "lowdrive":     ("🔋", "Low interest / drive", {"sex": 2, "stress": 1}),
}
# things that happened today (context) -> label
CONTEXT = {
    "sick": ("🤒", "I was unwell / fever"),
    "stressday": ("😤", "Very stressful day"),
    "caffeine": ("☕", "Lots of tea/coffee"),
    "skipmeal": ("🥣", "Skipped meals"),
    "hardwork": ("🏋️", "Very hard workout"),
    "biotin": ("💊", "Took biotin / hair-skin-nail tablet"),
    "pill": ("🟣", "On birth-control pills"),
    "travel": ("✈️", "Travelled / late night"),
}
METRICS = {
    "sleep":  {"label": "Sleep", "unit": " h", "floor": 0.7, "bad": "down"},
    "energy": {"label": "Energy", "unit": "/5", "floor": 0.5, "bad": "down"},
    "mood":   {"label": "Mood", "unit": "/5", "floor": 0.5, "bad": "down"},
    "stress": {"label": "Stress", "unit": "/5", "floor": 0.5, "bad": "up"},
}
EXPLAIN = {"sleep": ["sick", "travel", "caffeine"], "energy": ["sick", "hardwork", "skipmeal", "travel"],
           "mood": ["stressday", "sick"], "stress": ["stressday", "travel"]}
MIN_DAYS = 8
LEVELS = ["Looking calm", "Worth watching", "Talk to a doctor soon"]

# ---------------------------------------------------------------- feature 1: personal baseline
def _robust(vals, floor):
    m = median(vals)
    mad = median([abs(v - m) for v in vals]) * 1.4826
    return m, max(mad, floor)

def _drift_text(k, usual, now, worse):
    d = abs(now - usual)
    if k == "sleep":
        return f"You are sleeping about {d:.1f} hours {'less' if now < usual else 'more'} than your usual {usual:.1f} hours."
    if k == "energy":
        return f"Your energy is lower than your usual (about {now:.1f} vs {usual:.1f} out of 5)." if worse > 0 else "Your energy is better than your usual."
    if k == "mood":
        return f"Your mood has been lower than your usual (about {now:.1f} vs {usual:.1f} out of 5)." if worse > 0 else "Your mood is better than your usual."
    return f"Your stress is higher than your usual (about {now:.1f} vs {usual:.1f} out of 5)." if worse > 0 else "Your stress is lower than your usual."

def cycle_info(period_dates, today):
    ds = sorted(set(period_dates))
    if not ds:
        return None
    last = ds[-1]
    since = (today - last).days
    info = {"last": last.isoformat(), "days_since": since, "usual": None, "late": False, "irregular": False}
    if len(ds) >= 3:
        lens = [(b - a).days for a, b in zip(ds, ds[1:])][-6:]
        info["usual"] = round(median(lens))
        info["irregular"] = (max(lens) - min(lens)) >= 9
        info["late"] = since > info["usual"] + 7
    return info

def analyze_baseline(rows, period_dates, sex, today=None):
    today = today or date.today()
    n = len(rows)
    out = {"days": n, "needed": MIN_DAYS, "ready": n >= MIN_DAYS, "metrics": {}, "drifts": [], "good": [],
           "cycle": cycle_info(period_dates, today) if sex == "female" else None}
    if not out["ready"]:
        return out
    recent, base = rows[-3:], rows[:-3][-28:]
    ctx = {c for r in recent for c in r["context"]}
    for k, meta in METRICS.items():
        bv = [r[k] for r in base if r.get(k) is not None]
        rv = [r[k] for r in recent if r.get(k) is not None]
        if len(bv) < 4 or not rv:
            continue
        m, s = _robust(bv, meta["floor"])
        now = mean(rv)
        z = (now - m) / s
        worse = -z if meta["bad"] == "down" else z
        out["metrics"][k] = {
            "label": meta["label"], "unit": meta["unit"], "usual": round(m, 1), "now": round(now, 1),
            "band": [round(m - 1.5 * s, 1), round(m + 1.5 * s, 1)], "worse": round(worse, 2),
            "series": [{"d": r["date"], "v": r[k]} for r in rows[-30:] if r.get(k) is not None]}
        if worse >= 1.5:
            why = [CONTEXT[c][1] for c in EXPLAIN[k] if c in ctx]
            out["drifts"].append({"metric": k, "level": 2 if worse >= 2.5 else 1, "text": _drift_text(k, m, now, worse),
                                  "maybe_because": why})
        elif worse <= -1.5:
            out["good"].append(_drift_text(k, m, now, worse))
    return out

# ---------------------------------------------------------------- body-signal areas
def score_areas(rows, baseline, sex):
    win = rows[-7:]
    n = max(len(win), 3)
    res = {}
    for a, meta in AREAS.items():
        score, reasons = 0.0, []
        contrib = []
        for key, (emo, label, w) in SYMPTOMS.items():
            if a in w:
                days = sum(1 for r in win if key in r["symptoms"])
                if days:
                    c = w[a] * days / n
                    score += c
                    contrib.append((c, f"{label} ({days} of last {len(win)} days)"))
        for d in baseline.get("drifts", []):
            if a == "stress" and d["metric"] in ("stress", "sleep"):
                score += 0.8 * d["level"] * 1.0; contrib.append((1.5, d["text"]))
            if a == "thyroid" and d["metric"] == "energy":
                score += 0.8 * d["level"]; contrib.append((1.5, d["text"]))
            if a == "sex" and d["metric"] == "mood":
                score += 0.4 * d["level"]
        cyc = baseline.get("cycle")
        if a == "sex" and cyc and (cyc["late"] or cyc["irregular"]):
            score += 2.5
            contrib.append((3, f"Your period is {cyc['days_since'] - cyc['usual']} days later than your usual pattern"
                            if cyc["late"] else "Your cycle length has been changing a lot"))
        contrib.sort(reverse=True)
        lvl = 0 if score < 2 else (1 if score < 5 else 2)
        res[a] = {"id": a, "icon": meta["icon"], "name": meta["name"], "tech": meta["tech"], "level": lvl,
                  "status": LEVELS[lvl], "score": round(score, 1), "reasons": [t for _, t in contrib[:3]]}
    return res

# ---------------------------------------------------------------- labs
LABS = {
    "tsh":      {"name": "TSH (thyroid control hormone)", "unit": "mIU/L", "ref": (0.4, 4.0),
                 "means": {"high": "Your thyroid may be running slow.", "low": "Your thyroid may be running fast."}},
    "ft4":      {"name": "Free T4 (thyroid hormone)", "unit": "ng/dL", "ref": (0.8, 1.8),
                 "means": {"high": "Thyroid hormone is above usual.", "low": "Thyroid hormone is below usual."}},
    "cortisol": {"name": "Cortisol (stress hormone, morning)", "unit": "µg/dL", "ref": (6.0, 18.0),
                 "means": {"high": "Stress hormone looks high.", "low": "Stress hormone looks low."}},
    "glucose":  {"name": "Fasting blood sugar", "unit": "mg/dL", "ref": (70, 100),
                 "means": {"high": "Blood sugar is above the usual fasting level.", "low": "Blood sugar is on the low side."}},
    "insulin":  {"name": "Fasting insulin", "unit": "µIU/mL", "ref": (2, 25),
                 "means": {"high": "Your body may be needing extra insulin to manage sugar.", "low": "Insulin is on the low side."}},
    "prolactin": {"name": "Prolactin (milk hormone)", "unit": "ng/mL", "ref": (4, 25),
                  "means": {"high": "Prolactin is up, which can affect periods.", "low": "Prolactin is low."}},
    "estradiol": {"name": "Estradiol (main female hormone)", "unit": "pg/mL", "ref": (30, 400),
                  "means": {"high": "Estradiol is on the high side.", "low": "Estradiol is on the low side."}},
}
IMMUNO = ["tsh", "ft4", "cortisol", "insulin", "prolactin", "estradiol"]

def _status(test, v):
    lo, hi = LABS[test]["ref"]
    return "low" if v < lo else ("high" if v > hi else "normal")

def personal_band(history):
    if len(history) < 2:
        return None
    m, sd = mean(history), pstdev(history)
    w = max(2 * sd, 0.12 * m)
    return [round(m - w, 2), round(m + w, 2), round(m, 2)]

def evaluate_lab(test, value, ctx, history, area_levels, sex="female"):
    """Returns result + list of context conflicts (feature 2)."""
    meta = LABS[test]
    st = _status(test, value)
    flags = []
    def add(sev, title, why, todo):
        flags.append({"severity": sev, "title": title, "why": why, "todo": todo})

    hour = ctx.get("hour")
    # 1 collected at the wrong time
    if test == "cortisol" and hour is not None and hour >= 11:
        add("warn", "Sample taken too late in the day",
            "Cortisol is naturally highest in the morning and drops through the day. The normal range is made for morning samples (6-10 am), so a later sample can look falsely low.",
            "Repeat between 6 and 10 am for a fair reading.")
    # 2 biotin
    if ctx.get("biotin") and test in IMMUNO:
        add("warn", "Biotin tablet can disturb this test",
            "Biotin (found in hair-skin-nail tablets) can trick many lab machines and give falsely high or low hormone values. This is a well-known lab problem.",
            "Ask your doctor, then stop biotin for 2-3 days before repeating the test.")
    # 3 thyroid medicine
    if ctx.get("thyroid_med") and test == "ft4":
        add("warn", "Thyroid tablet taken before the test",
            "Free T4 rises for a few hours after the thyroid tablet, so it can look higher than it really is.",
            "Next time, give blood first and take the tablet after.")
    # 4 not fasting
    if not ctx.get("fasting") and test in ("glucose", "insulin"):
        add("warn", "You were not fasting",
            "This test is compared with 'empty-stomach' normal values. Food in the last 8 hours pushes sugar and insulin up.",
            "Repeat after 8-10 hours without food (water is fine).")
    # 5 bad sleep
    if ctx.get("poor_sleep") and test in ("cortisol", "glucose", "insulin", "prolactin"):
        add("info", "Short sleep before the test",
            "One bad night can raise stress hormone, sugar and insulin for a day or two.",
            "If the value is high, repeat after two normal nights of sleep.")
    # 6 hard exercise
    if ctx.get("exercise") and test in ("prolactin", "cortisol", "glucose"):
        add("info", "Hard workout in the last day",
            "Heavy exercise can push prolactin, cortisol and sugar up for several hours.",
            "Rest for a day before the next test.")
    # 7 illness
    if ctx.get("sick") and test in ("tsh", "ft4"):
        add("warn", "Recent illness",
            "After fever or infection, thyroid numbers can swing for 4-8 weeks and then settle on their own.",
            "Repeat 6-8 weeks after you fully recover before drawing conclusions.")
    # 8 pill
    if ctx.get("pill") and test in ("estradiol", "cortisol"):
        add("warn", "Birth-control pills change this number",
            "Pills lower natural estradiol and raise total cortisol in the blood, so normal ranges do not fit well.",
            "Tell your doctor you are on pills when they read this result.")
    # 9 pregnancy
    if ctx.get("pregnant") and test in ("tsh", "ft4", "prolactin", "cortisol", "estradiol"):
        add("warn", "Pregnancy changes normal ranges",
            "In pregnancy these hormones naturally change, so the standard ranges shown here do not apply.",
            "Ask your doctor to read this with pregnancy ranges.")
    # 10 estradiol timing
    if test == "estradiol" and sex == "female" and not ctx.get("cycle_day"):
        add("info", "Cycle day not told",
            "Estradiol goes up and down a lot during your cycle. Without the cycle day, 'normal' or 'abnormal' cannot be judged properly.",
            "Add the day of your cycle (day 1 = first day of period).")
    # 11 stressful day / caffeine
    if ctx.get("stress_day") and test == "cortisol":
        add("info", "Stressful day / worry before test", "Even worry about a blood test can raise cortisol for a short while.", "If high, repeat on a calm morning.")
    if ctx.get("caffeine") and test in ("cortisol", "glucose"):
        add("info", "Tea/coffee before the test", "Caffeine can push cortisol and sugar up for a few hours.", "Skip tea/coffee before the next sample.")

    # 12 body signals vs result
    area = {"tsh": "thyroid", "ft4": "thyroid", "cortisol": "stress", "glucose": "sugar", "insulin": "sugar",
            "prolactin": "sex", "estradiol": "sex"}[test]
    lvl = area_levels.get(area, 0)
    if st == "normal" and lvl == 2:
        add("warn", "Report says normal, but your body says otherwise",
            f"Your daily check-ins show strong signals in '{AREAS[area]['name']}', yet this number is inside the normal range. Early or mild problems can hide inside the 'normal' range.",
            "Do not ignore your symptoms. Show your check-in summary to your doctor and ask about repeating or adding tests.")
    if st != "normal" and lvl == 0:
        add("info", "Result is off, but you have felt fine",
            "This number is outside the normal range, but your daily check-ins show no matching signals.",
            "Check the other flags above. One odd number with no symptoms is often a one-time blip, so a repeat is sensible.")
    # 13 personal baseline vs normal range
    pb = personal_band(history)
    personal = None
    if pb:
        personal = {"low": pb[0], "high": pb[1], "usual": pb[2], "outside": value < pb[0] or value > pb[1]}
        if st == "normal" and personal["outside"]:
            add("warn", "Normal for most people, but not normal for YOU",
                f"Your own past results sit around {pb[2]} {meta['unit']}. This one ({value}) is far from your usual, even though the lab's range calls it fine.",
                "This is a possible early change. Repeat in 4-6 weeks under the same conditions and show the trend to your doctor.")
    # 14 pattern conflicts
    other = ctx.get("others", {})
    if test == "tsh" and "ft4" in other:
        s2 = _status("ft4", other["ft4"])
        if (st == "high" and s2 == "high") or (st == "low" and s2 == "low"):
            add("warn", "TSH and Free T4 do not agree with each other",
                "These two usually move in opposite directions. When both are high (or both low), the cause is often a lab disturbance, such as biotin, or an illness recovery.",
                "Repeat both together after removing the possible causes above.")

    score = 100 - 30 * sum(f["severity"] == "warn" for f in flags) - 10 * sum(f["severity"] == "info" for f in flags)
    score = max(score, 5)
    trust = "Looks reliable" if score >= 80 else ("Use with care" if score >= 50 else "Retest advised")
    return {"test": test, "name": meta["name"], "value": value, "unit": meta["unit"], "ref": list(meta["ref"]),
            "status": st, "meaning": meta["means"].get(st, "Inside the usual range for most people."),
            "personal": personal, "conflicts": flags, "trust_score": score, "trust": trust}

# ---------------------------------------------------------------- plain-language outputs
def care_plan(areas, baseline, sex):
    items = []
    top = [a for a in areas.values() if a["level"] >= 1]
    if any(a["id"] == "stress" for a in top):
        items.append({"icon": "🌙", "title": "Protect your sleep", "tips": [
            "Sleep and wake at the same time every day, even on holidays.",
            "Keep phone away from bed 30 minutes before sleeping.",
            "Have tea or coffee only before noon."]})
    if any(a["id"] == "thyroid" for a in top):
        items.append({"icon": "🥗", "title": "Feed your energy", "tips": [
            "Eat regular meals with some protein (dal, eggs, paneer, sprouts).",
            "Use iodised salt in normal amounts; do not take thyroid-support supplements on your own.",
            "Walk for 20-30 minutes daily."]})
    if any(a["id"] == "sex" for a in top):
        items.append({"icon": "🌸", "title": "Track your cycle", "tips": [
            "Mark the first day of every period in the check-in.",
            "Keep a gentle exercise routine and avoid crash diets.",
            "Note acne, hair changes and mood so your doctor sees the full picture."]})
    if any(a["id"] == "sugar" for a in top):
        items.append({"icon": "🍬", "title": "Steady your sugar", "tips": [
            "Swap sugary drinks for water or buttermilk.",
            "Add millets, vegetables and protein, and eat at fixed times.",
            "A 10-minute walk after meals helps a lot."]})
    if not items:
        items.append({"icon": "💚", "title": "Keep doing what works", "tips": [
            "Keep your sleep, food and movement steady.", "Keep logging daily so Harmony knows your usual better."]})
    when = ["Signals stay in 'Talk to a doctor soon' for more than 2 weeks.",
            "Periods stop for 3 months or become very heavy.",
            "You get chest pain, fainting, a very fast heartbeat, or extreme thirst with weight loss: see a doctor straight away."]
    return {"items": items, "see_doctor_if": when,
            "note": "This is a self-care plan, not a medicine prescription. Only a doctor can prescribe medicines or tell you if you have a hormone problem."}

def doctor_summary(profile, rows, baseline, areas, labs):
    name, age = profile.get("name") or "I", profile.get("age")
    sec = []
    sec.append(("About me", f"{name}{', age ' + str(age) if age else ''}. I tracked my daily health for {len(rows)} days using Harmony."))
    if rows:
        last = rows[-14:]
        sl, en, mo, st = (round(mean([r[k] for r in last]), 1) for k in ("sleep", "energy", "mood", "stress"))
        sec.append(("How I have been in the last 2 weeks", f"Sleep about {sl} hours, energy {en}/5, mood {mo}/5, stress {st}/5."))
    if baseline["ready"]:
        if baseline["drifts"]:
            sec.append(("What changed from MY usual", " ".join(d["text"] for d in baseline["drifts"])))
        else:
            sec.append(("What changed from MY usual", "Nothing big. I am close to my own usual pattern."))
    else:
        sec.append(("What changed from MY usual", f"Harmony is still learning my usual ({baseline['days']} of {MIN_DAYS} days logged)."))
    cyc = baseline.get("cycle")
    if cyc:
        t = f"Last period started {cyc['last']} ({cyc['days_since']} days ago)."
        if cyc["usual"]:
            t += f" My usual cycle is about {cyc['usual']} days." + (" This one is late." if cyc["late"] else "")
        sec.append(("My periods", t))
    flagged = [a for a in areas.values() if a["level"] >= 1]
    sec.append(("Body signals I noticed", "; ".join(f"{a['name']}: {a['status'].lower()} ({'; '.join(a['reasons'][:2])})" for a in flagged) if flagged else "Nothing that stood out."))
    if labs:
        lines = []
        for l in labs[-5:]:
            s = f"{l['name']}: {l['value']} {l['unit']} ({l['status']}, {l['trust'].lower()})"
            if l["conflicts"]:
                s += ". Things that may have affected it: " + ", ".join(c["title"].lower() for c in l["conflicts"])
            lines.append(s)
        sec.append(("My test results and how much to trust them", "\n".join(lines)))
    qs = ["Could my symptoms be linked to my hormones, and which tests should I do?",
          "Should I repeat any test under better conditions (fasting, morning, no biotin)?"]
    if any(l["personal"] and l["personal"]["outside"] for l in labs[-5:]):
        qs.append("A result looks normal on paper but is far from my own usual. Does this trend matter?")
    sec.append(("Questions I want to ask", "\n".join(f"{i+1}. {q}" for i, q in enumerate(qs))))
    return sec
