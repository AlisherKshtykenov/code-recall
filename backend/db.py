"""SQLite через SQLAlchemy. Задача = рабочая папка; база хранит версии её текстовых файлов,
попытки и расписание повторений."""
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# CODE_RECALL_DATA — другая папка данных (например, отдельная копия для экспериментов)
DATA_DIR = Path(os.getenv("CODE_RECALL_DATA") or Path(__file__).resolve().parent.parent / "data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "recall.db"

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()


class Task(Base):
    """Задача: папка data/tasks/<name>/ (description.md, reference/, starter/, tests/, data/, results/)."""
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)  # имя папки
    title = Column(String, nullable=False)
    kind = Column(String, default="algo")  # algo | ml
    tag = Column(String, default="")
    difficulty = Column(Integer, default=3)
    notes = Column(Text, default="")
    python = Column(Text, default="")  # путь к .venv / python; "" — окружение приложения
    timeout = Column(Integer, default=60)  # секунд на запуск и прогон тестов
    main_file = Column(String, default="")  # что запускает «Запустить» по умолчанию
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    # FSRS (пересчитывается по истории попыток, см. review.replay)
    due_at = Column(DateTime, nullable=True)
    fsrs_s = Column(Float, nullable=True)
    fsrs_d = Column(Float, nullable=True)
    last_review = Column(DateTime, nullable=True)
    reps = Column(Integer, default=0)
    lapses = Column(Integer, default=0)

    versions = relationship("TaskVersion", back_populates="task", order_by="TaskVersion.number",
                            cascade="all, delete-orphan")
    attempts = relationship("Attempt", back_populates="task", order_by="Attempt.started_at",
                            cascade="all, delete-orphan")

    @property
    def current(self):
        return self.versions[-1] if self.versions else None


class TaskVersion(Base):
    """Снимок текстовых файлов задачи. data/ и results/ в версии не входят (они большие)."""
    __tablename__ = "task_versions"
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    number = Column(Integer, nullable=False)
    files = Column(Text, nullable=False)  # JSON {путь: текст}: description.md, reference/*, starter/*, tests/*
    roles = Column(Text, default="{}")  # JSON {reference/x.py: "write" | "given"}
    content_hash = Column(String, nullable=False)
    ref_results = Column(Text, default="")  # JSON: результаты тестов на эталоне (кэш по окружению)
    created_at = Column(DateTime, default=datetime.now)

    task = relationship("Task", back_populates="versions")


class Attempt(Base):
    __tablename__ = "attempts"
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    version_id = Column(Integer, ForeignKey("task_versions.id"), nullable=False)
    status = Column(String, default="active")  # active | checking | submitted | abandoned
    started_at = Column(DateTime, default=datetime.now)
    finished_at = Column(DateTime, nullable=True)
    total_ms = Column(Integer, default=0)
    files = Column(Text, default="{}")  # JSON {имя.py: текст} — файлы попытки
    checks = Column(Integer, default=0)  # сколько раз нажато «Проверить»
    ref_opened = Column(Integer, default=0)  # открывал эталон до сдачи
    score = Column(Integer, nullable=True)
    grade_auto = Column(Integer, nullable=True)  # 1 забыл, 2 трудно, 3 нормально, 4 легко
    grade = Column(Integer, nullable=True)
    grade_manual = Column(Integer, default=0)
    report = Column(Text, default="")  # JSON-отчёт
    last_check = Column(Text, default="")  # JSON: результат последнего «Проверить» (виден и у брошенной)
    last_output = Column(Text, default="")  # JSON: вывод последнего «Запустить»
    touched_at = Column(DateTime, nullable=True)  # последняя активность (правка, запуск, таймер)

    task = relationship("Task", back_populates="attempts")
    reviews = relationship("ReviewSession", back_populates="attempt", order_by="ReviewSession.started_at",
                           cascade="all, delete-orphan")


class ReviewSession(Base):
    """«Работа над ошибками» по попытке: 1 — смотрю, 2 — переписываю с подглядыванием, 3 — по памяти.
    Файлы проходятся по одному; на FSRS влияет только шаг 3."""
    __tablename__ = "review_sessions"
    id = Column(Integer, primary_key=True)
    attempt_id = Column(Integer, ForeignKey("attempts.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    version_id = Column(Integer, ForeignKey("task_versions.id"), nullable=False)
    status = Column(String, default="active")  # active | passed | failed | abandoned
    files = Column(Text, default="[]")  # JSON: какие файлы переписываю, по порядку
    idx = Column(Integer, default=0)  # текущий файл
    step = Column(Integer, default=1)  # 1 | 2 | 3
    step_started = Column(DateTime, default=datetime.now)
    peeked = Column(Integer, default=0)  # подглядывал на шаге 3 текущего файла
    checks = Column(Integer, default=0)  # «Проверить» на текущем шаге
    log = Column(Text, default="[]")  # JSON: [{file, step, ms, passed, peeked, checks}]
    work = Column(Text, default="{}")  # JSON {файл: текст} — что написано в редакторе
    runs = Column(Text, default="[]")  # JSON: история «Запустить» / «Проверить» — код, тесты, вывод
    peeks = Column(Integer, default=0)  # сколько раз подсматривал эталон на шаге 3 текущего файла
    started_at = Column(DateTime, default=datetime.now)
    finished_at = Column(DateTime, nullable=True)

    attempt = relationship("Attempt", back_populates="reviews")


class Setting(Base):
    __tablename__ = "settings"
    key = Column(String, primary_key=True)
    value = Column(Text, default="")


OLD_TABLES = ("ref_cells", "tests", "attempts", "ref_versions", "references")
OLD_SETTINGS = ("cell_timeout", "w_exec", "w_tests", "w_judge", "hint_penalty", "plan_penalty")


def drop_notebook_era():
    """Разовый переход: эталоны-ноутбуки и их попытки удаляются (перед этим — копия базы)."""
    if not DB_PATH.exists():
        return
    con = sqlite3.connect(DB_PATH)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "references" not in tables:
        con.close()
        return
    backups = DATA_DIR / "backups"
    backups.mkdir(exist_ok=True)
    dst = sqlite3.connect(backups / f"before-tasks-{datetime.now():%Y-%m-%d_%H-%M-%S}.db")
    with dst:
        con.backup(dst)
    dst.close()
    with con:
        for t in OLD_TABLES:
            con.execute(f'DROP TABLE IF EXISTS "{t}"')
        con.execute(f"DELETE FROM settings WHERE key IN ({','.join('?' * len(OLD_SETTINGS))})", OLD_SETTINGS)
    con.close()
    import shutil
    for d in ("workspaces", "kernelspec", "tmp"):  # папки старых эталонов и Jupyter
        shutil.rmtree(DATA_DIR / d, ignore_errors=True)
    print("CODE RECALL: эталоны-ноутбуки удалены, копия базы в data/backups/")


def add_missing_columns():
    """Простая миграция: колонки, появившиеся в новых версиях, добавляются в существующие таблицы."""
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            have = {r[1] for r in conn.exec_driver_sql(f'PRAGMA table_info("{table.name}")')}
            for col in table.columns:
                if col.name in have:
                    continue
                default = col.default.arg if col.default is not None and not callable(col.default.arg) else None
                sql_default = f" DEFAULT {default!r}" if isinstance(default, (int, str)) else ""
                conn.exec_driver_sql(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" '
                                     f"{col.type.compile(engine.dialect)}{sql_default}")


def init_db():
    drop_notebook_era()
    Base.metadata.create_all(engine)
    add_missing_columns()


def get_setting(db, key, default=""):
    row = db.get(Setting, key)
    return row.value if row else default


def set_setting(db, key, value):
    row = db.get(Setting, key)
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))
