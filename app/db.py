from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from datetime import datetime
from app.core.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True)
    label = Column(String(200), nullable=False)
    banner_username = Column(String(200), nullable=False)
    banner_password_enc = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    operations = relationship("Operation", back_populates="student")

class Operation(Base):
    __tablename__ = "operations"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    status = Column(String(50), default="queued")
    progress = Column(Integer, default=0)
    step = Column(String(255), default="waiting")
    message = Column(Text, default="")
    result_json = Column(Text, default="{}")
    report_path = Column(String(500), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    student = relationship("Student", back_populates="operations")

class CurriculumProgram(Base):
    __tablename__ = "curriculum_programs"
    id = Column(Integer, primary_key=True)
    url = Column(String(700), unique=True)
    title = Column(String(500))
    raw_json = Column(Text, default="{}")
    updated_at = Column(DateTime, default=datetime.utcnow)

class Log(Base):
    __tablename__ = "operation_logs"
    id = Column(Integer, primary_key=True)
    operation_id = Column(Integer, index=True)
    level = Column(String(20), default="INFO")
    message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=engine)
