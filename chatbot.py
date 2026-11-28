"""Small, offline, explainable chatbot: keyword intent matching + live answers from the user's own data."""
import re

EMERGENCY = ["chest pain", "can't breathe", "cannot breathe", "faint", "unconscious", "severe bleeding",
             "suicide", "kill myself", "want to die", "seizure"]

KB = [
 (["hello", "hi ", "hey", "namaste"], "Hi! I'm Harmony 🌿 I can explain hormones in simple words, look at your check-ins, or explain your lab report. What would you like to know?"),
 (["how to use", "help", "what can you do", "start"], "Easy: 1) Do the 1-minute daily check-in. 2) After about 8 days I learn YOUR usual and warn you early when you drift. 3) Add lab results to see if they can be trusted. 4) Open 'Doctor Summary' to show your doctor."),
 (["which hormones", "what hormones", "list of hormones", "hormones you", "hormones are", "hormones responsible", "hormones cause", "test for pcos", "tests for pcos", "pcos test", "pcod test"], "Harmony covers: thyroid (TSH, Free T4), stress (cortisol), sugar (glucose, insulin), estrogen (estradiol), progesterone, prolactin, PCOS/PCOD markers (LH, FSH, AMH, SHBG), androgens (testosterone, DHEA-S) and oxytocin. For PCOS/PCOD doctors mainly look at irregular periods, androgen signs (testosterone, DHEA-S, pimples, extra hair), LH and FSH, AMH, SHBG, insulin and sugar, plus an ovary ultrasound. Add your results in 'Lab Check' and I will show a PCOS pattern check."),
 (["androgen", "testosterone", "dhea", "male hormone", "shbg", "facial hair"], "Androgens (testosterone, DHEA-S) are 'male-type' hormones that every body makes in small amounts. In women, too much can cause pimples, extra face or body hair, hair thinning and irregular periods, and it is common in PCOS. SHBG is the protein that carries them: low SHBG means more active androgen. Only a doctor can interpret the tests."),
 (["estrogen", "oestrogen", "estradiol", "progesterone"], "Estrogen and progesterone run your monthly cycle. Estrogen builds up in the first half, and progesterone rises after an egg is released. Their levels change a lot through the month, so I always ask for your cycle day when you add these tests."),
 (["oxytocin", "love hormone", "bonding"], "Oxytocin is the 'bonding and calm' hormone. It rises with hugs, bonding, breastfeeding and relaxation, and helps reduce stress. It is not a routine blood test and there is no standard normal range, so use it only to watch your own trend. Calm routines, sleep, time with loved ones and gentle touch support it naturally."),
 (["lh", "fsh", "amh", "egg", "ovulation", "ovary"], "LH and FSH are brain signals that grow and release an egg each month. In PCOS, LH is often higher than FSH. AMH shows egg reserve and is often high in PCOS. LH and FSH should be tested on day 2 to 5 of the period, so tell me your cycle day when you add them."),
 (["baseline", "my usual", "personal"], "Your 'baseline' is simply YOUR normal: your usual sleep, energy, mood and stress. Everyone is different, so I compare you with yourself, not with a textbook. If you drift away from your usual for a few days, I warn you early."),
 (["conflict", "context", "interfere", "wrong result", "fasting", "biotin"], "Sometimes a lab number is not wrong, it is just measured at a bad moment: not fasting, afternoon sample, biotin tablets, fever last month, no sleep. I check for these 'context conflicts' and tell you whether to trust the number or retest."),
 (["thyroid", "tsh", "t4"], "The thyroid is a small gland in your neck that sets your body's speed. Slow thyroid: tired, cold, weight gain, dry skin, constipation, hair fall. Fast thyroid: racing heart, sweating, weight loss, worry. A blood test (TSH) checks it. Only a doctor can diagnose it."),
 (["pcos", "pcod", "irregular period", "periods", "period", "menstrual", "cycle"], "Periods are a monthly sign of hormone balance. Late or very irregular periods, new pimples and extra facial hair together can be linked to PCOS. Mark your period start in the check-in so I can learn your normal cycle. If periods stop for 3 months, please see a doctor."),
 (["cortisol", "stress hormone", "stress"], "Cortisol is your body's stress hormone. It should be high in the morning and low at night. Long stress, poor sleep and too much caffeine can keep it off-balance. Try fixed sleep time, a short walk, deep breathing, and less late-evening screen time."),
 (["sugar", "insulin", "diabetes", "thirst", "cravings"], "Insulin moves sugar from blood into your cells. When the body resists insulin, you may feel very hungry, crave sweets, get sleepy after meals and see dark patches on the neck. Regular meals, walking after food and less sugary drinks help. A fasting sugar test can confirm."),
 (["sleep", "insomnia"], "Sleep is when your hormones reset. Aim for the same bedtime daily, no tea or coffee after noon, dim lights at night and no phone in bed. If you cannot sleep for more than 2 weeks, tell your doctor."),
 (["diet", "food", "eat", "meal"], "Simple hormone-friendly plate: half vegetables, a quarter protein (dal, egg, paneer, sprouts), a quarter whole grains or millets. Eat at regular times, drink enough water, and avoid crash diets."),
 (["hair", "hairfall"], "Hair fall can be linked to thyroid changes, low iron, stress or hormone changes. Note it in your check-in. If it continues over 2-3 months, ask your doctor about thyroid and iron tests."),
 (["weight", "obese", "fat"], "Sudden weight change can be linked to thyroid, sugar or stress hormones, but also to food, sleep and activity. Track it with your check-ins, and ask a doctor if it changes without a clear reason."),
 (["tired", "fatigue", "energy", "weak"], "Feeling tired has many causes: poor sleep, low iron, thyroid, stress, or sugar swings. Look at your 'My Usual' page to see whether your energy has dropped from your own usual."),
 (["mood", "anxiety", "anxious", "depress", "sad"], "Hormones can affect mood, but so can many other things. If sadness or worry lasts more than 2 weeks or affects daily life, please talk to a doctor or someone you trust. Tele-MANAS (14416) is a free helpline in India."),
 (["doctor", "summary", "prescription", "report"], "Open 'Doctor Summary' to get a simple page you can show your doctor or print. I do not write medicines: only a doctor can prescribe. I give a self-care plan instead."),
 (["privacy", "data", "safe"], "Your data stays in this app's own database on the server you run it on. It is not shared with anyone. You can delete everything from the Settings page."),
 (["thank"], "You're welcome 💚 Keep checking in, small daily notes make me smarter about you."),
]
DISCLAIMER = " (I'm an assistant, not a doctor.)"

def reply(msg, state):
    m = " " + msg.lower().strip() + " "
    if any(e in m for e in EMERGENCY):
        return "This sounds serious. Please call 112 (India emergency) or go to the nearest hospital now. If you feel low or unsafe, Tele-MANAS 14416 is free and available any time. Please don't wait.", "emergency"
    if re.search(r"how am i|my status|my health|how is my|am i ok|my signals", m):
        flagged = [a for a in state["areas"].values() if a["level"] >= 1]
        if not state["checkins"]:
            return "I don't know you yet 🙂 Do your first check-in, it takes one minute.", "status"
        if not flagged:
            return "All four body areas look calm right now 🟢. Keep logging daily.", "status"
        a = max(flagged, key=lambda x: x["score"])
        return f"Right now, '{a['name']}' needs most attention: {a['status'].lower()}. Because: {' | '.join(r.rstrip('.') for r in a['reasons'][:2]) or 'your recent signals'}. Open 'Doctor Summary' for the full picture.", "status"
    if re.search(r"my pcos|pcos risk|do i have pcos|do i have pcod|pcos pattern|pcod pattern", m):
        p = state.get("pcos")
        if not p or not p.get("applicable"): return "The PCOS/PCOD pattern check is for people with periods. Add your check-ins and lab results first.", "pcos"
        return p["headline"] + " " + p["next"][0], "pcos"
    if re.search(r"my (lab|result|test)", m):
        labs = state["labs"]
        if not labs:
            return "You haven't added any lab result yet. Go to 'Lab Check' and I'll tell you if the result can be trusted.", "labs"
        l = labs[-1]
        extra = f" But note: {l['conflicts'][0]['title'].lower()}." if l["conflicts"] else ""
        return f"Your latest {l['name']} is {l['value']} {l['unit']}, which is {l['status']} compared with the usual range. Trust level: {l['trust']}.{extra}", "labs"
    best, score = None, 0
    for kws, ans in KB:
        s = sum(1 for k in kws if k in m)
        if s > score:
            best, score = ans, s
    if best:
        return best + (DISCLAIMER if score and "Hi!" not in best else ""), "kb"
    return "I'm not sure I understood. You can ask things like: 'What is thyroid?', 'How am I doing?', 'Why is my report not reliable?' or 'Why are my periods late?'", "fallback"
