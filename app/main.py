import json
from pathlib import Path
from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.db import init_db, SessionLocal, Student, Operation, Log
from app.core.security import encrypt
from app.core.config import settings
from app.workers.jobs import start_background, start_manual_html

app = FastAPI(title="SEU Academic Registration Assistant")
templates = Jinja2Templates(directory="app/web/templates")

@app.on_event("startup")
def startup():
    Path("data").mkdir(exist_ok=True); Path("logs").mkdir(exist_ok=True); Path("reports").mkdir(exist_ok=True); Path("screenshots").mkdir(exist_ok=True)
    init_db()

def db_dep():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def is_authed(request: Request):
    return request.cookies.get("admin") == settings.admin_username

@app.get("/health")
def health(): return {"ok": True}

@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(db_dep)):
    if not is_authed(request): return RedirectResponse("/login")
    students = db.query(Student).order_by(Student.id.desc()).all()
    ops = db.query(Operation).order_by(Operation.id.desc()).limit(10).all()
    return templates.TemplateResponse("index.html", {"request": request, "students": students, "ops": ops})

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request): return templates.TemplateResponse("login.html", {"request": request, "error": ""})

@app.post("/login")
def login(username: str = Form(...), password: str = Form(...)):
    if username == settings.admin_username and password == settings.admin_password:
        r = RedirectResponse("/", status_code=303); r.set_cookie("admin", username, httponly=True, samesite="lax"); return r
    return HTMLResponse("<h3>بيانات دخول المشرف غير صحيحة</h3><a href='/login'>رجوع</a>", status_code=401)

@app.get("/logout")
def logout():
    r = RedirectResponse("/login"); r.delete_cookie("admin"); return r

@app.get("/students/new", response_class=HTMLResponse)
def new_student(request: Request):
    if not is_authed(request): return RedirectResponse("/login")
    return templates.TemplateResponse("new_student.html", {"request": request})

@app.post("/students")
def create_student(request: Request, label: str = Form(...), banner_username: str = Form(...), banner_password: str = Form(...), db: Session = Depends(db_dep)):
    if not is_authed(request): return RedirectResponse("/login")
    s = Student(label=label, banner_username=banner_username, banner_password_enc=encrypt(banner_password))
    db.add(s); db.commit()
    return RedirectResponse(f"/students/{s.id}", status_code=303)

@app.get("/students/{student_id}", response_class=HTMLResponse)
def student_detail(request: Request, student_id: int, db: Session = Depends(db_dep)):
    if not is_authed(request): return RedirectResponse("/login")
    s = db.get(Student, student_id)
    if not s: raise HTTPException(404)
    ops = db.query(Operation).filter(Operation.student_id==student_id).order_by(Operation.id.desc()).all()
    return templates.TemplateResponse("student.html", {"request": request, "student": s, "ops": ops})

@app.post("/students/{student_id}/run")
def run_analysis(request: Request, student_id: int, db: Session = Depends(db_dep)):
    if not is_authed(request): return RedirectResponse("/login")
    s = db.get(Student, student_id)
    if not s: raise HTTPException(404)
    op = Operation(student_id=student_id, status="queued", progress=0, step="في الانتظار")
    db.add(op); db.commit()
    start_background(op.id)
    return RedirectResponse(f"/operations/{op.id}", status_code=303)



@app.get("/students/{student_id}/manual", response_class=HTMLResponse)
def manual_upload_page(request: Request, student_id: int, db: Session = Depends(db_dep)):
    if not is_authed(request): return RedirectResponse("/login")
    s = db.get(Student, student_id)
    if not s: raise HTTPException(404)
    return templates.TemplateResponse("manual_upload.html", {"request": request, "student": s})

@app.post("/students/{student_id}/manual")
def manual_upload_submit(request: Request, student_id: int, transcript_html: str = Form(...), db: Session = Depends(db_dep)):
    if not is_authed(request): return RedirectResponse("/login")
    s = db.get(Student, student_id)
    if not s: raise HTTPException(404)
    op = Operation(student_id=student_id, status="queued", progress=0, step="في انتظار تحليل كشف الدرجات اليدوي")
    db.add(op); db.commit()
    start_manual_html(op.id, transcript_html)
    return RedirectResponse(f"/operations/{op.id}", status_code=303)

@app.get("/operations/{operation_id}", response_class=HTMLResponse)
def operation_page(request: Request, operation_id: int, db: Session = Depends(db_dep)):
    if not is_authed(request): return RedirectResponse("/login")
    op = db.get(Operation, operation_id)
    if not op: raise HTTPException(404)
    logs = db.query(Log).filter(Log.operation_id==operation_id).order_by(Log.id.desc()).limit(100).all()
    result = {}
    try: result = json.loads(op.result_json or "{}")
    except Exception: pass
    return templates.TemplateResponse("operation.html", {"request": request, "op": op, "logs": logs, "result": result})

@app.get("/operations/{operation_id}/report")
def download_report(request: Request, operation_id: int, db: Session = Depends(db_dep)):
    if not is_authed(request): return RedirectResponse("/login")
    op = db.get(Operation, operation_id)
    if not op or not op.report_path or not Path(op.report_path).exists(): raise HTTPException(404)
    return FileResponse(op.report_path, filename=Path(op.report_path).name)
