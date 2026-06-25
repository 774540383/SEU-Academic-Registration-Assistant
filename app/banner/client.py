import json, re, asyncio
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from app.core.config import settings

ARTIFACTS = Path("screenshots")
ARTIFACTS.mkdir(exist_ok=True)

class BannerClient:
    def __init__(self, username: str, password: str, operation_id: int, log):
        self.username = username
        self.password = password
        self.operation_id = operation_id
        self.log = log

    async def collect_student_data(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            page = await browser.new_page(viewport={"width": 1365, "height": 900})
            try:
                await self.log("فتح Banner")
                await page.goto(settings.banner_registration_url, wait_until="domcontentloaded", timeout=60000)
                await self._snapshot(page, "01_open_registration")
                await self._try_login(page)
                await self._snapshot(page, "02_after_login")
                transcript = await self._open_transcript(page)
                profile = self._extract_profile(transcript.get("html", ""))
                courses = self._extract_courses(transcript.get("html", ""))
                return {"profile": profile, "courses": courses, "source": settings.banner_transcript_url, "captured_at": datetime.utcnow().isoformat()}
            finally:
                await browser.close()

    async def _try_login(self, page):
        await self.log("محاولة اكتشاف حقول تسجيل الدخول")
        user_selectors = ['input[name="username"]', 'input#username', 'input[type="text"]', 'input[name="user"]']
        pass_selectors = ['input[name="password"]', 'input#password', 'input[type="password"]']
        u = await self._first_visible(page, user_selectors)
        p = await self._first_visible(page, pass_selectors)
        if u and p:
            await u.fill(self.username)
            await p.fill(self.password)
            await self.log("تم إدخال بيانات الدخول محليًا بشكل مخفي")
            submit = await self._first_visible(page, ['button[type="submit"]', 'input[type="submit"]', 'button:has-text("Login")', 'button:has-text("تسجيل")'])
            if submit:
                await submit.click()
            else:
                await p.press("Enter")
            await page.wait_for_load_state("domcontentloaded", timeout=60000)
        else:
            await self.log("لم تظهر حقول الدخول؛ قد تكون هناك جلسة أو صفحة دخول مختلفة", "WARN")
        content = await page.content()
        if re.search(r"invalid|incorrect|خطأ|غير صحيحة", content, re.I):
            raise RuntimeError("فشل تسجيل الدخول: بيانات غير صحيحة أو تحقق إضافي مطلوب.")

    async def _open_transcript(self, page):
        await self.log("فتح صفحة كشف الدرجات")
        await page.goto(settings.banner_transcript_url, wait_until="networkidle", timeout=90000)
        await self._snapshot(page, "03_transcript_page")
        await self._select_if_possible(page, ["Undergraduate", "المرحلة الجامعية"])
        await self._select_if_possible(page, ["Web"])
        for txt in ["Submit", "عرض", "إرسال", "View"]:
            btn = page.locator(f'text={txt}').first
            try:
                if await btn.count() and await btn.is_visible(timeout=1000):
                    await btn.click()
                    await page.wait_for_load_state("networkidle", timeout=60000)
                    break
            except Exception:
                pass
        await self._snapshot(page, "04_transcript_result")
        return {"html": await page.content()}

    async def _select_if_possible(self, page, options):
        selects = page.locator("select")
        for i in range(await selects.count()):
            sel = selects.nth(i)
            for opt in options:
                try:
                    await sel.select_option(label=opt, timeout=1000)
                    await self.log(f"اختيار {opt}")
                    return True
                except Exception:
                    continue
        return False

    async def _first_visible(self, page, selectors):
        for s in selectors:
            loc = page.locator(s).first
            try:
                if await loc.count() and await loc.is_visible(timeout=1500):
                    return loc
            except Exception:
                pass
        return None

    async def _snapshot(self, page, name):
        base = ARTIFACTS / f"op{self.operation_id}_{name}"
        await page.screenshot(path=str(base.with_suffix(".png")), full_page=True)
        base.with_suffix(".html").write_text(await page.content(), encoding="utf-8")

    def _extract_profile(self, html):
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text("\n", strip=True)
        profile = {"student_name": "", "program": "", "gpa": "", "earned_hours": ""}
        for pattern, key in [(r"GPA[:\s]+([0-9.]+)", "gpa"), (r"المعدل[^0-9]*([0-9.]+)", "gpa"), (r"Earned Hours[:\s]+([0-9.]+)", "earned_hours")]:
            m = re.search(pattern, text, re.I)
            if m: profile[key] = m.group(1)
        return profile

    def _extract_courses(self, html):
        soup = BeautifulSoup(html, "lxml")
        rows = []
        for tr in soup.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td","th"])]
            joined = " | ".join(cells)
            m = re.search(r"\b([A-Z]{2,5})\s*([0-9]{3})\b", joined)
            if m:
                code = (m.group(1)+m.group(2)).upper()
                rows.append({"code": code, "raw": joined, "status": self._status(joined)})
        return rows

    def _status(self, text):
        if re.search(r"\bF\b|راسب|Fail", text, re.I): return "failed"
        if re.search(r"\b(A|B|C|D|P)\b|ناجح|Pass", text, re.I): return "passed"
        return "unknown"
