import json
import asyncio
import threading
import traceback
from datetime import datetime
from app.db import SessionLocal, Student, Operation, Log, CurriculumProgram
from app.core.security import decrypt
from app.banner.client import BannerClient
from app.curriculum.crawler import CurriculumCrawler
from app.analytics.engine import AcademicAnalyzer
from app.reports.pdf import make_report


def _set_op(operation_id: int, *, status=None, progress=None, step=None, message=None, result_json=None, report_path=None):
    db = SessionLocal()
    try:
        op = db.get(Operation, operation_id)
        if not op:
            return
        if status is not None: op.status = status
        if progress is not None: op.progress = progress
        if step is not None: op.step = step
        if message is not None: op.message = message
        if result_json is not None: op.result_json = result_json
        if report_path is not None: op.report_path = report_path
        op.updated_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


def _log(operation_id: int, msg: str, level: str = "INFO"):
    db = SessionLocal()
    try:
        db.add(Log(operation_id=operation_id, level=level, message=msg))
        op = db.get(Operation, operation_id)
        if op:
            op.step = msg[:250]
            op.updated_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


async def run_operation(operation_id: int):
    db = SessionLocal()
    try:
        op = db.get(Operation, operation_id)
        if not op:
            return
        student = db.get(Student, op.student_id)
        if not student:
            _set_op(operation_id, status="failed", progress=100, step="الطالب غير موجود", message="student not found")
            return
        username = student.banner_username
        password_enc = student.banner_password_enc
    finally:
        db.close()

    async def log(msg, level="INFO"):
        _log(operation_id, msg, level)

    try:
        _set_op(operation_id, status="running", progress=5, step="بدء التحليل الحقيقي")
        await log("بدء التحليل الحقيقي")

        password = decrypt(password_enc)
        if not username or not password:
            raise RuntimeError("بيانات Banner ناقصة. أعد إضافة الطالب باسم المستخدم وكلمة المرور.")

        _set_op(operation_id, progress=10, step="فتح Banner ومحاولة تسجيل الدخول")
        banner = BannerClient(username, password, operation_id, log)
        transcript = await asyncio.wait_for(banner.collect_student_data(), timeout=180)

        courses = transcript.get("courses") or []
        profile = transcript.get("profile") or {}
        if not courses:
            raise RuntimeError("لم يتم استخراج أي مقرر من Banner. تم حفظ screenshot و HTML في مجلد screenshots للتصحيح. لا توجد نتائج مؤكدة.")

        _set_op(operation_id, progress=45, step=f"تم استخراج {len(courses)} مقرر من Banner")
        await log(f"تم استخراج {len(courses)} مقرر من Banner")

        program = profile.get("program") or ""
        _set_op(operation_id, progress=55, step="جلب الخطة الرسمية من موقع الجامعة")
        crawler = CurriculumCrawler(log)
        curriculum = await asyncio.wait_for(crawler.discover_and_parse(program), timeout=120)
        if not curriculum or not curriculum.get("courses"):
            raise RuntimeError("لم يتم استخراج خطة دراسية رسمية من موقع الجامعة. لا يمكن إنشاء توصيات مؤكدة.")

        db = SessionLocal()
        try:
            db.add(CurriculumProgram(url=curriculum.get('url'), title=curriculum.get('title'), raw_json=json.dumps(curriculum, ensure_ascii=False)))
            db.commit()
        finally:
            db.close()

        _set_op(operation_id, progress=70, step="تحليل السجل مقابل الخطة الرسمية")
        analysis = AcademicAnalyzer().analyze(transcript, curriculum)
        result = {"transcript": transcript, "curriculum": curriculum, "analysis": analysis}

        _set_op(operation_id, progress=90, step="إنشاء تقرير PDF")
        report = make_report(f"student_{operation_id}", result)

        _set_op(
            operation_id,
            status="completed",
            progress=100,
            step="اكتمل التحليل الحقيقي وتم إنشاء التقرير",
            message="",
            result_json=json.dumps(result, ensure_ascii=False),
            report_path=report,
        )
        await log("اكتمل التحليل الحقيقي بنجاح")
    except Exception as e:
        tb = traceback.format_exc(limit=6)
        _set_op(operation_id, status="failed", progress=100, step="فشل التشغيل", message=f"{e}\n\n{tb}")
        _log(operation_id, f"فشل: {e}", "ERROR")
        _log(operation_id, tb, "ERROR")


def start_background(operation_id: int):
    def runner():
        asyncio.run(run_operation(operation_id))
    thread = threading.Thread(target=runner, daemon=True)
    thread.start()


async def run_manual_html_operation(operation_id: int, transcript_html: str):
    db = SessionLocal()
    try:
        op = db.get(Operation, operation_id)
        if not op:
            return
        student = db.get(Student, op.student_id)
        if not student:
            _set_op(operation_id, status="failed", progress=100, step="الطالب غير موجود", message="student not found")
            return
    finally:
        db.close()

    async def log(msg, level="INFO"):
        _log(operation_id, msg, level)

    try:
        _set_op(operation_id, status="running", progress=10, step="استلام كشف الدرجات من تسجيل دخول يدوي")
        await log("بدء التحليل من كشف درجات مرفوع يدويًا بعد تسجيل دخول الطالب")

        if not transcript_html or len(transcript_html.strip()) < 300:
            raise RuntimeError("المحتوى المرفوع قصير جدًا. افتح صفحة كشف الدرجات بعد تسجيل الدخول ثم انسخ الصفحة كاملة أو ارفع HTML كامل.")

        from app.banner.client import BannerClient
        parser = BannerClient("", "", operation_id, log)
        profile = parser._extract_profile(transcript_html)
        courses = parser._extract_courses(transcript_html)
        if not courses:
            raise RuntimeError("لم أستخرج أي مقرر من المحتوى المرفوع. تأكد أنك رفعت صفحة Web Transcript بعد اختيار Undergraduate و Web، وليس صفحة تسجيل الدخول أو صفحة فارغة.")

        transcript = {
            "profile": profile,
            "courses": courses,
            "source": "manual_transcript_html_after_user_login",
            "captured_at": datetime.utcnow().isoformat(),
            "manual_mode": True,
        }

        _set_op(operation_id, progress=45, step=f"تم استخراج {len(courses)} مقرر من كشف الدرجات المرفوع")
        await log(f"تم استخراج {len(courses)} مقرر من كشف الدرجات المرفوع يدويًا")

        program = profile.get("program") or ""
        _set_op(operation_id, progress=55, step="جلب الخطة الرسمية من موقع الجامعة")
        crawler = CurriculumCrawler(log)
        curriculum = await asyncio.wait_for(crawler.discover_and_parse(program), timeout=120)
        if not curriculum or not curriculum.get("courses"):
            raise RuntimeError("لم يتم استخراج خطة دراسية رسمية من موقع الجامعة. لا يمكن إنشاء توصيات مؤكدة.")

        db = SessionLocal()
        try:
            db.add(CurriculumProgram(url=curriculum.get('url'), title=curriculum.get('title'), raw_json=json.dumps(curriculum, ensure_ascii=False)))
            db.commit()
        finally:
            db.close()

        _set_op(operation_id, progress=75, step="تحليل السجل مقابل الخطة الرسمية")
        analysis = AcademicAnalyzer().analyze(transcript, curriculum)
        result = {"transcript": transcript, "curriculum": curriculum, "analysis": analysis}

        _set_op(operation_id, progress=90, step="إنشاء تقرير PDF")
        report = make_report(f"student_{operation_id}", result)

        _set_op(
            operation_id,
            status="completed",
            progress=100,
            step="اكتمل التحليل من تسجيل الدخول اليدوي وتم إنشاء التقرير",
            message="",
            result_json=json.dumps(result, ensure_ascii=False),
            report_path=report,
        )
        await log("اكتمل التحليل اليدوي بنجاح")
    except Exception as e:
        tb = traceback.format_exc(limit=6)
        _set_op(operation_id, status="failed", progress=100, step="فشل التحليل اليدوي", message=f"{e}\n\n{tb}")
        _log(operation_id, f"فشل: {e}", "ERROR")
        _log(operation_id, tb, "ERROR")


def start_manual_html(operation_id: int, transcript_html: str):
    def runner():
        asyncio.run(run_manual_html_operation(operation_id, transcript_html))
    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
