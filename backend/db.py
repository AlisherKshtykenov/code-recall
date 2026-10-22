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
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=True)  # узел дерева тем
    tags = Column(Text, default="[]")  # JSON: свободные теги
    broken = Column(Text, default="")  # «сломано зависимостью»: что упало на эталоне после смены эталона кирпичика
    last_assembly = Column(Text, default="{}")  # JSON: последняя сборка (для «как в прошлый раз»)
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


class Topic(Base):
    """Узел дерева тем любой глубины."""
    __tablename__ = "topics"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    parent_id = Column(Integer, ForeignKey("topics.id"), nullable=True)
    position = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)


class Slot(Base):
    """Слот: интерфейс (имя, сигнатура, описание) + контрактные тесты, верные для любой реализации.
    Задача-кирпичик объявляет «реализую слот X» в task.json ("implements": "X")."""
    __tablename__ = "slots"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)  # имя для импорта: from slots.<name> import <symbol>
    symbol = Column(String, default="")  # что реэкспортируется (по умолчанию = name)
    title = Column(String, default="")
    signature = Column(Text, default="")
    description = Column(Text, default="")
    tests = Column(Text, default="{}")  # JSON {tests/test_x.py: текст} — контрактные тесты
    default_impl = Column(String, default="")  # имя задачи-реализации по умолчанию
    created_at = Column(DateTime, default=datetime.now)


class BrickEvent(Base):
    """Кирпичик, написанный самому внутри составной задачи: прошёл / упал. Идёт в FSRS кирпичика."""
    __tablename__ = "brick_events"
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)  # кирпичик
    parent_task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)  # составная задача
    attempt_id = Column(Integer, ForeignKey("attempts.id"), nullable=False)
    dep_name = Column(String, default="")
    at = Column(DateTime, default=datetime.now)
    passed = Column(Integer, default=0)
    grade = Column(Integer, default=3)
    code = Column(Text, default="")  # код кирпичика — для «моя последняя версия»
    note = Column(Text, default="")  # что упало


class MapRow(Base):
    """Строка карты навыков (тип задачи из combinations.csv): ячейки по категориям — список кирпичиков."""
    __tablename__ = "map_rows"
    key = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    position = Column(Integer, default=0)
    cells = Column(Text, default="{}")  # JSON {категория: [{name, raw, note, slot_group, together}]}
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=True)  # узел «Проекты/<строка>»


class MapBrick(Base):
    """Кирпичик карты. Пока задачи нет — «запланирован» (лежит в дереве без файлов).
    Задача кирпичика — Task с name == имя кирпичика."""
    __tablename__ = "map_bricks"
    name = Column(String, primary_key=True)
    kind = Column(String, default="brick")  # brick | model | concept
    categories = Column(Text, default="[]")
    rows = Column(Text, default="[]")  # ключи строк, где используется
    raw = Column(Text, default="[]")  # исходные написания в CSV
    note = Column(Text, default="")
    related = Column(Text, default="[]")
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=True)


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
    assembly = Column(Text, default="{}")  # JSON {имя зависимости: {source: self|ref|last, impl}} — сборка составной задачи

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
    backups = DATA_DIR / "backups" / "manual"  # предмиграционная копия — вне ротации автобэкапов
    backups.mkdir(parents=True, exist_ok=True)
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


def migrate_topics():
    """Разово: старое поле «тема» (tag) -> узел дерева; без темы — «Алгоритмы» или «ML» по типу."""
    with SessionLocal() as db:
        if get_setting(db, "topics_migrated") == "1":
            return
        nodes = {}

        def node(name):
            if name not in nodes:
                t = db.query(Topic).filter_by(name=name, parent_id=None).first() or Topic(name=name)
                db.add(t)
                db.flush()
                nodes[name] = t
            return nodes[name]
        for t in db.query(Task).all():
            if t.topic_id is None:
                t.topic_id = node(t.tag.strip() or ("Алгоритмы" if t.kind == "algo" else "ML")).id
        set_setting(db, "topics_migrated", "1")
        db.commit()


def init_db():
    drop_notebook_era()
    Base.metadata.create_all(engine)
    add_missing_columns()
    migrate_topics()


def get_setting(db, key, default=""):
    row = db.get(Setting, key)
    return row.value if row else default


def set_setting(db, key, value):
    row = db.get(Setting, key)
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))
