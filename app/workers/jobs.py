import json, asyncio
from datetime import datetime
from app.db import SessionLocal, Student, Operation, Log, CurriculumProgram
from app.core.security import decrypt
from app.banner.client import BannerClient
from app.curriculum.crawler import CurriculumCrawler
from app.analytics.engine import AcademicAnalyzer
from app.reports.pdf import make_report

async def run_operation(operation_id: int):
    db = SessionLocal()
    op = db.get(Operation, operation_id)
    student = db.get(Student, op.student_id)
    async def log(msg, level="INFO"):
        db.add(Log(operation_id=operation_id, level=level, message=msg)); db.commit()
        op.step = msg; op.updated_at = datetime.utcnow(); db.commit()
    try:
        op.status = "running"; op.progress = 5; db.commit()
        await log("بدء التحليل الحقيقي")
        password = decrypt(student.banner_password_enc)
        banner = BannerClient(student.banner_username, password, operation_id, log)
        transcript = await banner.collect_student_data()
        op.progress = 45; db.commit()
        crawler = CurriculumCrawler(log)
        curriculum = await crawler.discover_and_parse(transcript.get('profile', {}).get('program',''))
        db.add(CurriculumProgram(url=curriculum.get('url'), title=curriculum.get('title'), raw_json=json.dumps(curriculum, ensure_ascii=False)))
        db.commit()
        op.progress = 70; db.commit()
        analysis = AcademicAnalyzer().analyze(transcript, curriculum)
        result = {"transcript": transcript, "curriculum": curriculum, "analysis": analysis}
        report = make_report(student.label, result)
        op.result_json = json.dumps(result, ensure_ascii=False)
        op.report_path = report
        op.progress = 100
        op.status = "completed"
        op.step = "اكتمل التحليل وتم إنشاء التقرير"
        op.updated_at = datetime.utcnow()
        db.commit()
        await log("اكتمل التحليل بنجاح")
    except Exception as e:
        op.status = "failed"; op.message = str(e); op.step = "فشل التشغيل"; op.updated_at = datetime.utcnow(); db.commit()
        await log(f"فشل: {e}", "ERROR")
    finally:
        db.close()

def start_background(operation_id: int):
    import threading

    def runner():
        asyncio.run(run_operation(operation_id))

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
