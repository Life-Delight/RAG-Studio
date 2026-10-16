from datetime import datetime, timedelta

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.core.config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def beijing_now() -> datetime:
    return datetime.utcnow() + timedelta(hours=8)


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    created_at = Column(DateTime, default=beijing_now)
    updated_at = Column(DateTime, default=beijing_now, onupdate=beijing_now)
    document_count = Column(Integer, default=0)


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    kb_id = Column(Integer, nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    original_name = Column(String(255), nullable=False)
    file_size = Column(Integer, default=0)
    file_type = Column(String(50), default="")
    status = Column(String(50), default="processing")  # processing, ready, failed
    chunk_count = Column(Integer, default=0)
    progress_percent = Column(Integer, default=0)
    progress_message = Column(Text, default="")
    created_at = Column(DateTime, default=beijing_now)
    updated_at = Column(DateTime, default=beijing_now, onupdate=beijing_now)
    error_message = Column(Text, default="")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    kb_id = Column(Integer, nullable=False, index=True)
    title = Column(String(255), default="新对话")
    created_at = Column(DateTime, default=beijing_now)
    updated_at = Column(DateTime, default=beijing_now, onupdate=beijing_now)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user, assistant
    content = Column(Text, nullable=False)
    sources = Column(Text, default="[]")  # JSON string
    tool_steps = Column(Text, default="[]")  # Agent 模式工具调用过程（JSON string）
    created_at = Column(DateTime, default=beijing_now)


class Employee(Base):
    """业务数据表：员工（供 Agent 模式 SQL 查询工具使用）"""
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    emp_no = Column(String(20), nullable=False)
    name = Column(String(50), nullable=False)
    gender = Column(String(10), default="")
    department = Column(String(50), nullable=False)
    position = Column(String(50), default="")
    hire_date = Column(String(20), default="")
    status = Column(String(20), default="在职")


class LeaveRecord(Base):
    """业务数据表：请假记录"""
    __tablename__ = "leave_records"

    id = Column(Integer, primary_key=True, index=True)
    emp_id = Column(Integer, nullable=False, index=True)
    leave_type = Column(String(20), nullable=False)  # 年假/病假/事假/婚假
    start_date = Column(String(20), nullable=False)
    end_date = Column(String(20), nullable=False)
    days = Column(Float, nullable=False)
    reason = Column(String(200), default="")
    status = Column(String(20), default="已批准")


class Reimbursement(Base):
    """业务数据表：报销记录"""
    __tablename__ = "reimbursements"

    id = Column(Integer, primary_key=True, index=True)
    emp_id = Column(Integer, nullable=False, index=True)
    expense_type = Column(String(20), nullable=False)  # 差旅/办公/招待
    amount = Column(Float, nullable=False)
    submit_date = Column(String(20), nullable=False)
    status = Column(String(20), default="待审核")  # 待审核/已报销/已驳回


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_document_progress_columns():
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(documents)")).fetchall()
        existing_columns = {row[1] for row in rows}
        if "progress_percent" not in existing_columns:
            conn.execute(text("ALTER TABLE documents ADD COLUMN progress_percent INTEGER DEFAULT 0"))
        if "progress_message" not in existing_columns:
            conn.execute(text("ALTER TABLE documents ADD COLUMN progress_message TEXT DEFAULT ''"))


def _ensure_chat_tool_steps_column():
    """旧库迁移：chat_messages 补 tool_steps 列（Agent 模式工具调用过程）。"""
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(chat_messages)")).fetchall()
        existing_columns = {row[1] for row in rows}
        if "tool_steps" not in existing_columns:
            conn.execute(text("ALTER TABLE chat_messages ADD COLUMN tool_steps TEXT DEFAULT '[]'"))


def seed_business_data():
    """写入演示用业务数据（仅首次，幂等）。供 Agent 模式的 SQL 查询工具使用。"""
    with engine.begin() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM employees")).scalar()
        if count:
            return

        conn.execute(text("""
            INSERT INTO employees (emp_no, name, gender, department, position, hire_date, status) VALUES
            ('E001', '张伟', '男', '研发部', '高级工程师', '2021-03-15', '在职'),
            ('E002', '李娜', '女', '研发部', '工程师', '2022-07-01', '在职'),
            ('E003', '王强', '男', '研发部', '技术总监', '2019-05-20', '在职'),
            ('E004', '刘洋', '男', '市场部', '市场专员', '2023-02-13', '在职'),
            ('E005', '陈静', '女', '市场部', '市场经理', '2020-09-01', '在职'),
            ('E006', '杨帆', '女', '人事部', 'HR专员', '2021-11-08', '在职'),
            ('E007', '赵敏', '女', '财务部', '财务主管', '2018-06-25', '在职'),
            ('E008', '孙磊', '男', '研发部', '工程师', '2024-04-01', '试用期'),
            ('E009', '周婷', '女', '行政部', '行政专员', '2023-08-14', '在职'),
            ('E010', '吴昊', '男', '市场部', '市场专员', '2025-01-05', '在职')
        """))

        conn.execute(text("""
            INSERT INTO leave_records (emp_id, leave_type, start_date, end_date, days, reason, status) VALUES
            (1, '年假', '2026-01-20', '2026-01-22', 3, '春节前休假', '已批准'),
            (1, '年假', '2026-07-06', '2026-07-10', 5, '暑期休假', '已批准'),
            (2, '病假', '2026-09-01', '2026-09-03', 3, '感冒发烧', '已批准'),
            (3, '年假', '2026-02-09', '2026-02-11', 3, '年假', '已批准'),
            (4, '事假', '2026-08-18', '2026-08-18', 1, '家中有事', '已批准'),
            (5, '年假', '2026-10-09', '2026-10-13', 5, '国庆后补休', '已批准'),
            (6, '婚假', '2026-05-18', '2026-05-25', 8, '五月婚期', '待审批'),
            (8, '事假', '2026-09-30', '2026-09-30', 1, '个人事务', '已批准'),
            (9, '病假', '2026-06-11', '2026-06-12', 2, '牙疼就医', '已批准'),
            (10, '事假', '2026-04-07', '2026-04-07', 0.5, '半天事假', '已批准')
        """))

        conn.execute(text("""
            INSERT INTO reimbursements (emp_id, expense_type, amount, submit_date, status) VALUES
            (1, '差旅', 2180.00, '2026-07-06', '已报销'),
            (3, '差旅', 4550.00, '2026-03-12', '已报销'),
            (2, '办公', 320.50, '2026-08-02', '已报销'),
            (4, '差旅', 1680.00, '2026-06-20', '待审核'),
            (5, '招待', 880.00, '2026-09-15', '已报销'),
            (7, '办公', 126.00, '2026-05-30', '已报销'),
            (6, '办公', 89.90, '2026-02-11', '已报销'),
            (9, '办公', 245.00, '2026-07-28', '已报销'),
            (8, '差旅', 720.00, '2026-09-08', '已驳回'),
            (10, '差旅', 1350.00, '2026-10-10', '待审核')
        """))


def init_db():
    Base.metadata.create_all(bind=engine)
    _ensure_document_progress_columns()
    _ensure_chat_tool_steps_column()
    seed_business_data()
