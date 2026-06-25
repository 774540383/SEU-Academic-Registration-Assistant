import re, json
from datetime import datetime
import httpx
from bs4 import BeautifulSoup
from app.core.config import settings

def normalize_code(value: str) -> str:
    return re.sub(r"\s+", "", value.upper().replace("STAT 101", "STAT101"))

class CurriculumCrawler:
    def __init__(self, log):
        self.log = log

    async def discover_and_parse(self, program_hint: str = ""):
        await self.log("جلب الخطط من موقع الجامعة الرسمي")
        urls = [settings.seu_programs_url]
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            links = []
            try:
                r = await client.get(settings.seu_programs_url)
                soup = BeautifulSoup(r.text, "lxml")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    title = a.get_text(" ", strip=True)
                    if "/programs/" in href and ("بكالوريوس" in title or "bachelor" in href.lower() or "bachelor" in title.lower()):
                        if href.startswith("/"): href = "https://seu.edu.sa" + href
                        if not href.endswith("/structure/"):
                            href = href.rstrip("/") + "/structure/"
                        links.append(href)
            except Exception as e:
                await self.log(f"فشل اكتشاف البرامج تلقائيًا: {e}", "WARN")
            if not links:
                links = ["https://seu.edu.sa/ar/programs/bachelor-of-english-language-and-translation/structure/",
                         "https://seu.edu.sa/ar/programs/bachelor-of-business-administration-management/structure/"]
            best = links[0]
            if program_hint:
                for u in links:
                    if any(part and part.lower() in u.lower() for part in re.split(r"\s+", program_hint)):
                        best = u; break
            r = await client.get(best)
            parsed = self.parse_structure(r.text, best)
            await self.log(f"تم تحليل خطة رسمية: {parsed.get('title') or best}")
            return parsed

    def parse_structure(self, html: str, url: str):
        soup = BeautifulSoup(html, "lxml")
        title = soup.find(["h1","h2"])
        courses = []
        text = soup.get_text("\n", strip=True)
        # Parse table rows first
        for tr in soup.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td","th"])]
            joined = " | ".join(cells)
            m = re.search(r"\b([A-Z]{2,5})\s*([0-9]{3})\b", joined)
            if m:
                code = normalize_code(m.group(0))
                hours = next((x for x in cells if re.fullmatch(r"\d+", x)), "")
                prereq = cells[0] if cells else ""
                name = max(cells, key=len) if cells else ""
                courses.append({"code": code, "name": name, "hours": hours, "prerequisite_raw": prereq})
        # Fallback line parser for current SEU text layout
        lines = [x.strip() for x in text.split("\n") if x.strip()]
        for i, line in enumerate(lines):
            m = re.fullmatch(r"[A-Z]{2,5}\s*\d{3}", line)
            if m and normalize_code(line) not in {c['code'] for c in courses}:
                code = normalize_code(line)
                name = lines[i-1] if i > 0 else ""
                hours = lines[i-2] if i > 1 and re.fullmatch(r"\d+", lines[i-2]) else ""
                prereq = lines[i-3] if i > 2 else ""
                courses.append({"code": code, "name": name, "hours": hours, "prerequisite_raw": prereq})
        return {"url": url, "title": title.get_text(' ', strip=True) if title else "SEU Program", "courses": courses, "captured_at": datetime.utcnow().isoformat()}
