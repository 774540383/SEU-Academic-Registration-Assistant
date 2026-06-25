import re
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
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
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
            page = await browser.new_page(viewport={"width": 1365, "height": 900})
            try:
                await self.log("فتح صفحة Banner")
                await page.goto(settings.banner_registration_url, wait_until="domcontentloaded", timeout=60000)
                await self._snapshot(page, "01_open_registration")

                await self._try_login(page)
                await self._snapshot(page, "02_after_login")

                await self.log("فتح صفحة كشف الدرجات")
                html = await self._open_transcript(page)
                profile = self._extract_profile(html)
                courses = self._extract_courses(html)

                if not courses:
                    await self.log("لم يتم العثور على مقررات في صفحة كشف الدرجات", "ERROR")
                    raise RuntimeError("Banner فتح، لكن لم يتم استخراج مقررات. قد يوجد تحقق إضافي، أو الصفحة لم تعرض Web Transcript، أو selectors تحتاج تحديث.")

                return {"profile": profile, "courses": courses, "source": settings.banner_transcript_url, "captured_at": datetime.utcnow().isoformat()}
            finally:
                await browser.close()

    async def _try_login(self, page):
        await self.log("اكتشاف حقول تسجيل الدخول")
        user_selectors = ['input[name="username"]', 'input#username', 'input[type="email"]', 'input[type="text"]', 'input[name*="user" i]']
        pass_selectors = ['input[name="password"]', 'input#password', 'input[type="password"]']
        u = await self._first_visible(page, user_selectors)
        pw = await self._first_visible(page, pass_selectors)
        if not (u and pw):
            await self.log("لم تظهر حقول الدخول؛ سأفحص هل هناك جلسة مفتوحة أو تحويل SSO", "WARN")
            return
        await u.fill(self.username)
        await pw.fill(self.password)
        await self.log("تم إدخال بيانات الدخول داخل جلسة المتصفح دون طباعتها")
        submit = await self._first_visible(page, ['button[type="submit"]', 'input[type="submit"]', 'button:has-text("Login")', 'button:has-text("Sign in")', 'button:has-text("تسجيل")', 'button:has-text("دخول")'])
        if submit:
            await submit.click()
        else:
            await pw.press("Enter")
        try:
            await page.wait_for_load_state("networkidle", timeout=60000)
        except Exception:
            await page.wait_for_load_state("domcontentloaded", timeout=30000)
        content = await page.content()
        if re.search(r"invalid|incorrect|wrong password|خطأ|غير صحيحة|فشل", content, re.I):
            raise RuntimeError("فشل تسجيل الدخول: بيانات غير صحيحة أو تحقق إضافي مطلوب.")

    async def _open_transcript(self, page):
        await page.goto(settings.banner_transcript_url, wait_until="domcontentloaded", timeout=90000)
        await self._snapshot(page, "03_transcript_page")
        await self._select_option_fuzzy(page, ["Undergraduate", "المرحلة الجامعية"])
        await self._select_option_fuzzy(page, ["Web"])
        clicked = False
        for txt in ["Submit", "عرض", "إرسال", "View", "متابعة", "Continue"]:
            loc = page.locator(f'text={txt}').first
            try:
                if await loc.count() and await loc.is_visible(timeout=1500):
                    await self.log(f"ضغط زر: {txt}")
                    await loc.click()
                    clicked = True
                    break
            except Exception:
                pass
        if clicked:
            try:
                await page.wait_for_load_state("networkidle", timeout=60000)
            except Exception:
                await page.wait_for_timeout(5000)
        else:
            await self.log("لم أجد زر عرض واضح؛ سأحفظ الصفحة كما هي للفحص", "WARN")
        await self._snapshot(page, "04_transcript_result")
        return await page.content()

    async def _select_option_fuzzy(self, page, labels):
        selects = page.locator("select")
        count = await selects.count()
        for i in range(count):
            sel = selects.nth(i)
            for label in labels:
                try:
                    await sel.select_option(label=label, timeout=1500)
                    await self.log(f"اختيار: {label}")
                    return True
                except Exception:
                    pass
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
        try:
            await page.screenshot(path=str(base.with_suffix(".png")), full_page=True)
        except Exception:
            pass
        try:
            base.with_suffix(".html").write_text(await page.content(), encoding="utf-8")
        except Exception:
            pass

    def _extract_profile(self, html):
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text("\n", strip=True)
        profile = {"student_name": "", "program": "", "gpa": "", "earned_hours": ""}
        patterns = [
            (r"GPA[:\s]+([0-9.]+)", "gpa"),
            (r"المعدل[^0-9]*([0-9.]+)", "gpa"),
            (r"Earned\s+Hours[:\s]+([0-9.]+)", "earned_hours"),
            (r"الساعات[^0-9]*([0-9.]+)", "earned_hours"),
            (r"Program[:\s]+(.+)", "program"),
            (r"البرنامج[:\s]+(.+)", "program"),
        ]
        for pattern, key in patterns:
            m = re.search(pattern, text, re.I)
            if m and not profile.get(key):
                profile[key] = m.group(1).strip()[:200]
        return profile

    def _extract_courses(self, html):
        soup = BeautifulSoup(html, "lxml")
        rows = []
        seen = set()
        for tr in soup.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            joined = " | ".join(cells)
            for m in re.finditer(r"\b([A-Z]{2,5})\s*[- ]?\s*([0-9]{3})\b", joined):
                code = (m.group(1) + m.group(2)).upper().replace(" ", "")
                key = code + joined[:80]
                if key not in seen:
                    seen.add(key)
                    rows.append({"code": code, "raw": joined, "status": self._status(joined)})
        return rows

    def _status(self, text):
        if re.search(r"\bF\b|راسب|Fail|Failed", text, re.I):
            return "failed"
        if re.search(r"\b(A\+?|B\+?|C\+?|D\+?|P|NP)\b|ناجح|Pass|Passed", text, re.I):
            return "passed"
        return "unknown"
