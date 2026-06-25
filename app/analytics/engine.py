import re

def normalize(code):
    return re.sub(r"\s+", "", code.upper())

def prerequisite_met(prereq_raw, passed, earned_hours=0):
    if not prereq_raw or prereq_raw in {"—", "-"}: return True, "لا يوجد متطلب سابق"
    raw = prereq_raw.strip()
    if "اجتياز السنة الأولى" in raw:
        return earned_hours >= 30, "يتطلب اجتياز السنة الأولى"
    m = re.search(r"(\d+)\s*ساعة", raw)
    if m:
        n = int(m.group(1)); return earned_hours >= n, f"يتطلب إكمال {n} ساعة"
    codes = [normalize(x) for x in re.findall(r"[A-Z]{2,5}\s*\d{3}", raw)]
    missing = [c for c in codes if c not in passed]
    if "/" in raw and codes:
        ok = any(c in passed for c in codes)
        return ok, "يتطلب أحد: " + ", ".join(codes)
    return not missing, ("المتطلبات مكتملة" if not missing else "ناقص: " + ", ".join(missing))

class AcademicAnalyzer:
    def analyze(self, transcript, curriculum):
        courses = transcript.get("courses", [])
        passed = {normalize(c["code"]) for c in courses if c.get("status") == "passed"}
        failed = {normalize(c["code"]) for c in courses if c.get("status") == "failed"}
        earned_hours = float(transcript.get("profile", {}).get("earned_hours") or 0)
        remaining, eligible, blocked = [], [], []
        for c in curriculum.get("courses", []):
            code = normalize(c.get("code", ""))
            if not code or code in passed: continue
            ok, reason = prerequisite_met(c.get("prerequisite_raw", ""), passed, earned_hours)
            item = {**c, "code": code, "reason": reason}
            if code in failed:
                item["priority"] = 100
            elif ok:
                item["priority"] = 50 + len([x for x in curriculum.get("courses", []) if code in x.get("prerequisite_raw", "")])
            if ok or code in failed: eligible.append(item)
            else: blocked.append(item)
            remaining.append(item)
        eligible_sorted = sorted(eligible, key=lambda x: x.get("priority", 0), reverse=True)
        recommendations = {
            "safe": eligible_sorted[:4],
            "balanced": eligible_sorted[:6],
            "fast": eligible_sorted[:7],
            "maximum": eligible_sorted[:8],
        }
        total = max(len(curriculum.get("courses", [])), 1)
        return {"passed": sorted(passed), "failed": sorted(failed), "remaining": remaining, "eligible": eligible_sorted, "blocked": blocked, "recommendations": recommendations, "progress_percent": round(len(passed)/total*100, 1)}
