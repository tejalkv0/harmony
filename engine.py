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
    # ---- thyroid
    "tsh":      {"group": "Thyroid", "name": "TSH (thyroid control hormone)", "unit": "mIU/L", "ref": (0.4, 4.0),
                 "means": {"high": "Your thyroid may be running slow.", "low": "Your thyroid may be running fast."}},
    "ft4":      {"group": "Thyroid", "name": "Free T4 (thyroid hormone)", "unit": "ng/dL", "ref": (0.8, 1.8),
                 "means": {"high": "Thyroid hormone is above usual.", "low": "Thyroid hormone is below usual."}},
    # ---- stress & sugar
    "cortisol": {"group": "Stress & sugar", "name": "Cortisol (stress hormone, morning)", "unit": "µg/dL", "ref": (6.0, 18.0),
                 "means": {"high": "Stress hormone looks high.", "low": "Stress hormone looks low."}},
    "glucose":  {"group": "Stress & sugar", "name": "Fasting blood sugar", "unit": "mg/dL", "ref": (70, 100),
                 "means": {"high": "Blood sugar is above the usual fasting level.", "low": "Blood sugar is on the low side."}},
    "insulin":  {"group": "Stress & sugar", "name": "Fasting insulin", "unit": "µIU/mL", "ref": (2, 25),
                 "means": {"high": "Your body may be needing extra insulin to manage sugar. This is common in PCOS.", "low": "Insulin is on the low side."}},
    # ---- female hormones
    "estradiol": {"group": "Estrogen & periods", "name": "Estradiol (main estrogen)", "unit": "pg/mL",
                  "ref": {"female": (30, 400), "male": (10, 40)},
                  "means": {"high": "Estrogen is on the high side.", "low": "Estrogen is on the low side."}},
    "progesterone": {"group": "Estrogen & periods", "name": "Progesterone (period-balance hormone)", "unit": "ng/mL",
                  "ref": {"female": (0.1, 25), "male": (0.2, 1.4)},
                  "means": {"high": "Progesterone is high, which is normal after an egg is released or in pregnancy.",
                            "low": "Low progesterone can mean no egg was released this cycle, or the test was on the wrong day."}},
    "prolactin": {"group": "Estrogen & periods", "name": "Prolactin (milk hormone)", "unit": "ng/mL",
                  "ref": {"female": (4, 25), "male": (4, 15)},
                  "means": {"high": "Prolactin is up, which can stop or delay periods.", "low": "Prolactin is low."}},
    # ---- PCOS / PCOD markers
    "lh":  {"group": "PCOS / PCOD markers", "name": "LH (egg-release signal)", "unit": "mIU/mL", "ref": {"female": (2, 15), "male": (1.5, 9.3)},
            "means": {"high": "LH is high. In PCOS it is often higher than FSH.", "low": "LH is low. This can happen with very low weight or heavy stress."}},
    "fsh": {"group": "PCOS / PCOD markers", "name": "FSH (egg-growth signal)", "unit": "mIU/mL", "ref": {"female": (3, 12.5), "male": (1.5, 12.4)},
            "means": {"high": "FSH is high, which can mean the ovaries are responding less.", "low": "FSH is low."}},
    "amh": {"group": "PCOS / PCOD markers", "name": "AMH (egg reserve hormone)", "unit": "ng/mL", "ref": {"female": (1.0, 4.0), "male": (0.7, 19)},
            "means": {"high": "AMH is high. This is often seen in PCOS (many small follicles).", "low": "AMH is low, which suggests fewer eggs remaining."}},
    "shbg": {"group": "PCOS / PCOD markers", "name": "SHBG (carrier protein for sex hormones)", "unit": "nmol/L", "ref": {"female": (18, 144), "male": (10, 57)},
            "means": {"high": "Carrier protein is high, so less free hormone is active.",
                      "low": "Carrier protein is low, so more free androgen is active. Often linked with insulin resistance and PCOS."}},
    # ---- androgens
    "testosterone": {"group": "Androgens", "name": "Testosterone (main androgen)", "unit": "ng/dL", "ref": {"female": (15, 70), "male": (300, 1000)},
            "means": {"high": "Androgen (male-type hormone) is above usual. It can go with pimples, extra hair and irregular periods.",
                      "low": "Androgen is below usual. It can go with low energy and low drive."}},
    "dheas": {"group": "Androgens", "name": "DHEA-S (adrenal androgen)", "unit": "µg/dL", "ref": {"female": (35, 430), "male": (80, 560)},
            "means": {"high": "Adrenal androgen is up, which can add to pimples, hair growth and period changes.", "low": "Adrenal androgen is low. It also falls naturally with age."}},
    # ---- bonding
    "oxytocin": {"group": "Bonding hormone", "name": "Oxytocin (bonding & calm hormone)", "unit": "pg/mL", "ref": None,
            "note": "There is no standard doctor-approved range for oxytocin. Use it only to watch YOUR own trend.", "means": {}},
}
IMMUNO = ["tsh", "ft4", "cortisol", "insulin", "prolactin", "estradiol", "progesterone", "lh", "fsh", "amh", "shbg", "testosterone", "dheas", "oxytocin"]
SEX_HORMONES = ["estradiol", "progesterone", "prolactin", "lh", "fsh", "amh", "shbg", "testosterone", "dheas"]

def ref_for(test, sex="female"):
    r = LABS[test]["ref"]
    if r is None: return None
    if isinstance(r, dict): return r.get(sex) or r.get("female")
    return r

def _status(test, v, sex="female"):
    r = ref_for(test, sex)
    if r is None: return "unknown"
    return "low" if v < r[0] else ("high" if v > r[1] else "normal")

def personal_band(history):
    if len(history) < 2:
        return None
    m, sd = mean(history), pstdev(history)
    w = max(2 * sd, 0.12 * m)
    return [round(m - w, 2), round(m + w, 2), round(m, 2)]

def evaluate_lab(test, value, ctx, history, area_levels, sex="female"):
    """Returns result + list of context conflicts (feature 2)."""
    meta = LABS[test]
    ref = ref_for(test, sex)
    st = _status(test, value, sex)
    other = ctx.get("others", {})
    cd = ctx.get("cycle_day")
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
    if ctx.get("pill") and test in ("estradiol", "cortisol", "testosterone", "shbg", "lh", "fsh", "progesterone", "amh", "dheas"):
        add("warn", "Birth-control pills change this number",
            "Pills lower natural estrogen, testosterone, LH and FSH, and raise SHBG and total cortisol, so normal ranges do not fit well.",
            "Tell your doctor you are on pills when they read this result.")
    # 9 pregnancy
    if ctx.get("pregnant") and test in ("tsh", "ft4", "prolactin", "cortisol", "estradiol", "progesterone", "lh", "fsh", "amh", "shbg", "testosterone", "dheas"):
        add("warn", "Pregnancy changes normal ranges",
            "In pregnancy these hormones naturally change, so the standard ranges shown here do not apply.",
            "Ask your doctor to read this with pregnancy ranges.")
    # 10 estradiol timing
    if test == "estradiol" and sex == "female" and not cd:
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
            "oxytocin": "stress"}.get(test, "sex")
    lvl = area_levels.get(area, 0)
    if st == "normal" and lvl == 2:
        add("warn", "Report says normal, but your body says otherwise",
            f"Your daily check-ins show strong signals in '{AREAS[area]['name']}', yet this number is inside the normal range. Early or mild problems can hide inside the 'normal' range.",
            "Do not ignore your symptoms. Show your check-in summary to your doctor and ask about repeating or adding tests.")
    if st in ("low", "high") and lvl == 0:
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
    # 15 PCOS / androgen / oxytocin rules
    if test == "oxytocin":
        add("warn", "Oxytocin has no standard blood test range",
            "Oxytocin is not a routine lab test. Different kits give very different numbers, and levels jump with touch, mood and stress.",
            "Do not judge this as high or low. Only compare it with your own earlier oxytocin results, taken the same way.")
    if test == "testosterone" and hour is not None and hour >= 11:
        add("info", "Sample taken late in the day", "Testosterone is highest in the early morning and drops through the day, so a late sample can look lower.", "Repeat between 7 and 10 am if the value is low.")
    if test == "testosterone" and ctx.get("poor_sleep"):
        add("info", "Short sleep before the test", "A few nights of poor sleep can lower testosterone.", "Repeat after a week of normal sleep if the value is low.")
    if sex != "male" and test in ("lh", "fsh"):
        if cd is None:
            add("info", "Cycle day not told", "LH and FSH change a lot during the cycle (LH shoots up around ovulation). Without the cycle day they cannot be judged properly.", "Add the cycle day. Day 2 to 5 of your period is the best time for this test.")
        elif not 2 <= cd <= 5:
            add("info", "Not taken on day 2 to 5 of the cycle", "LH and FSH are compared with the early part of the cycle. A mid-cycle sample can show a normal LH surge that looks 'high'.", "Repeat on day 2 to 5 of your next period.")
    if sex != "male" and test == "progesterone":
        if cd is None:
            add("info", "Cycle day not told", "Progesterone is only high in the second half of the cycle, after an egg is released.", "Add the cycle day. The best day is about 7 days before your next period (around day 21 of a 28-day cycle).")
        elif not 18 <= cd <= 25:
            add("warn", "Not taken in the best week for progesterone", "Progesterone is naturally low before ovulation, so a low value on this day does not mean a problem.", "Repeat about 7 days before your next period.")
    if sex != "male" and test in ("lh", "fsh"):
        lh = value if test == "lh" else other.get("lh"); fsh = value if test == "fsh" else other.get("fsh")
        if lh and fsh and lh / fsh >= 2:
            add("info", f"LH is {lh / fsh:.1f} times FSH", "In PCOS, LH is often twice FSH or more. But this ratio alone cannot prove PCOS and it changes with the cycle day.", "Show both numbers, with your cycle day, to your doctor.")
    if test in ("glucose", "insulin"):
        g = value if test == "glucose" else other.get("glucose"); i = value if test == "insulin" else other.get("insulin")
        if g and i and ctx.get("fasting") and g * i / 405 >= 2.5:
            add("info", f"Insulin-resistance score (HOMA-IR) is {g * i / 405:.1f}", "Sugar and insulin together give this score. Above about 2.5 suggests the body is resisting insulin, which is common in PCOS.", "Discuss it with your doctor. Walking after meals and less sugary food help.")

    # 14 pattern conflicts
    if test == "tsh" and "ft4" in other:
        s2 = _status("ft4", other["ft4"])
        if (st == "high" and s2 == "high") or (st == "low" and s2 == "low"):
            add("warn", "TSH and Free T4 do not agree with each other",
                "These two usually move in opposite directions. When both are high (or both low), the cause is often a lab disturbance, such as biotin, or an illness recovery.",
                "Repeat both together after removing the possible causes above.")

    score = 100 - 30 * sum(f["severity"] == "warn" for f in flags) - 10 * sum(f["severity"] == "info" for f in flags)
    score = max(score, 5)
    trust = "Looks reliable" if score >= 80 else ("Use with care" if score >= 50 else "Retest advised")
    return {"test": test, "name": meta["name"], "value": value, "unit": meta["unit"], "ref": list(ref) if ref else None,
            "status": st, "meaning": meta.get("note", "") if st == "unknown" else meta["means"].get(st, "Inside the usual range for most people."),
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

def pcos_pattern(labs, rows, baseline, sex):
    """Plain-language PCOS/PCOD pattern check (Rotterdam-style idea). NOT a diagnosis."""
    if sex == "male":
        return {"applicable": False}
    last = {l["test"]: l for l in labs}
    recent = rows[-7:]
    sy = lambda k: any(k in r["symptoms"] for r in recent)
    cyc = baseline.get("cycle") or {}
    irregular = bool(cyc.get("late") or cyc.get("irregular") or sy("irregular"))
    lab_andro = [last[k]["name"].split(" (")[0] for k in ("testosterone", "dheas") if k in last and last[k]["status"] == "high"]
    signs = [x for x, k in (("pimples", "acne"), ("extra face/body hair", "facialhair")) if sy(k)]
    andro = bool(lab_andro or signs)
    crit = [
        {"name": "Irregular or missing periods", "met": irregular,
         "detail": "Your cycle is late or changing, or you logged irregular periods." if irregular else "Not seen in your check-ins."},
        {"name": "Signs of extra male-type hormone (androgen)", "met": andro,
         "detail": ("High on lab: " + ", ".join(lab_andro) + ". " if lab_andro else "") + (("Logged: " + ", ".join(signs) + ".") if signs else "") if andro else "No lab or symptom sign yet."},
        {"name": "Many small follicles on the ovary scan", "met": None, "detail": "Only a pelvic ultrasound can show this. A doctor has to advise it."}]
    sup = []
    lh, fsh = last.get("lh"), last.get("fsh")
    if lh and (lh["status"] == "high" or (fsh and fsh["value"] and lh["value"] / fsh["value"] >= 2)):
        sup.append("LH is high compared with FSH")
    if "shbg" in last and last["shbg"]["status"] == "low": sup.append("SHBG (carrier protein) is low")
    if "amh" in last and last["amh"]["status"] == "high": sup.append("AMH is high")
    if ("insulin" in last and last["insulin"]["status"] == "high") or ("glucose" in last and last["glucose"]["status"] == "high" and last["glucose"]["trust_score"] >= 80):
        sup.append("Insulin or fasting sugar is high")
    if sy("darkpatches") or sy("weightgain"): sup.append("Dark neck patches or weight gain logged")
    met = sum(c["met"] is True for c in crit)
    if met >= 2: lvl, head = 2, "Several PCOS/PCOD signs are present. Please see a gynaecologist or endocrinologist."
    elif met == 1 and len(sup) >= 2: lvl, head = 1, "Some PCOS/PCOD hints. Worth discussing with a doctor."
    elif met == 1 or len(sup) >= 2: lvl, head = 1, "A few hints, but not a clear pattern yet."
    else: lvl, head = 0, "No clear PCOS/PCOD pattern right now."
    nxt = ["Only a doctor can diagnose PCOS/PCOD. Show this page and your doctor will decide about a pelvic ultrasound."]
    if "tsh" not in last or "prolactin" not in last:
        nxt.append("Also get TSH and prolactin checked, because thyroid and prolactin problems can look like PCOS.")
    nxt.append("Keep marking your period start dates in the check-in.")
    return {"applicable": True, "level": lvl, "headline": head, "criteria": crit, "supportive": sup, "next": nxt,
            "note": "PCOS and PCOD are used for the same everyday problem. This is a pattern check, not a diagnosis."}

def doctor_summary(profile, rows, baseline, areas, labs, pcos=None):
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
    if pcos and pcos.get("applicable") and pcos["level"] > 0:
        met = [c["name"] for c in pcos["criteria"] if c["met"] is True]
        sec.append(("PCOS / PCOD pattern check (not a diagnosis)", pcos["headline"] + ("\nSigns found: " + "; ".join(met) if met else "") + ("\nAlso noticed: " + "; ".join(pcos["supportive"]) if pcos["supportive"] else "")))
    qs = ["Could my symptoms be linked to my hormones, and which tests should I do?",
          "Should I repeat any test under better conditions (fasting, morning, no biotin)?"]
    if any(l["personal"] and l["personal"]["outside"] for l in labs[-5:]):
        qs.append("A result looks normal on paper but is far from my own usual. Does this trend matter?")
    sec.append(("Questions I want to ask", "\n".join(f"{i+1}. {q}" for i, q in enumerate(qs))))
    return sec
