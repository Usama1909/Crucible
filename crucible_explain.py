"""Turn a Crucible verdict + real stats into plain human English. No LLM."""
import re

def _conf_pct(confidence):
    if confidence is None: return None
    return round(max(0.0, min(1.0, float(confidence))) * 100)

def _parse_mean(reason):
    if not reason: return None
    m = re.search(r"mean=(-?\d+\.?\d*)", reason)
    return float(m.group(1)) if m else None

def _magnitude(mean):
    if mean is None: return "unclear"
    m = abs(mean)
    if m >= 0.03: return "heavily"
    if m >= 0.01: return "consistently"
    if m >= 0.003: return "slightly"
    return "barely"

def _data_note(n):
    if n is None: return ""
    if n < 15: return f"Only {n} decisions so far — thin evidence."
    if n < 30: return f"Built on {n} decisions — moderate evidence."
    return f"Built on {n} decisions — solid sample."

def _trend_note(trend, mean):
    if trend is None or trend == "": return ""
    try: t = float(trend)
    except: return ""
    if t < 0: return "And it's getting worse recently, not recovering."
    if t > 0:
        if mean is not None and mean < 0:
            return "But recent decisions are improving — worth watching before retiring."
        return "And recent decisions are strengthening it."
    return ""

def explain_verdict(cell):
    verdict = (cell.get("verdict") or "").upper()
    reason = cell.get("reason") or ""
    mean = _parse_mean(reason)
    conf = _conf_pct(cell.get("confidence"))
    n = cell.get("evidence")
    trend = cell.get("trend")
    mag = _magnitude(mean)
    losing = mean is not None and mean < 0
    verb = "losing" if losing else ("making" if mean is not None else "moving")
    data = _data_note(n)
    tnote = _trend_note(trend, mean)
    headline = verdict + " — no plain rule yet."
    detail = reason
    tone = "neutral"
    if verdict == "RETIRE":
        headline = "Retire this — it consistently loses money."
        c = ("Crucible is " + str(conf) + "% sure") if conf is not None else "Crucible is confident"
        detail = c + " this strategy is " + mag + " " + verb + " money over time. " + data + " " + tnote
        tone = "bad"
    elif verdict == "LEAN_AWAY":
        headline = "Lean away — it's been a net loser."
        detail = "On average this has been " + mag + " " + verb + " money. Reduce how much you rely on it. " + data + " " + tnote
        tone = "warn"
    elif verdict == "WATCH":
        headline = "Watch — interesting but unproven."
        detail = "Early signal may be there but there isn't enough evidence yet to trust it. " + data + " Crucible is deliberately not calling this a real edge. " + tnote
        tone = "neutral"
    elif verdict in ("LEAVE", "KEEP"):
        headline = "Keep it — this one is pulling its weight."
        c = (str(conf) + "% confident") if conf is not None else "confident"
        detail = "Crucible is " + c + " this is " + mag + " " + verb + " money and worth keeping. " + data + " " + tnote
        tone = "good"
    return {"headline": headline, "detail": " ".join(detail.split()), "confidence": conf, "tone": tone}
