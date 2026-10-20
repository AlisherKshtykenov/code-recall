"""SQLite-база через SQLAlchemy. Все модели в одном файле."""
from datetime import datetime
from pathlib import Path

from sqlalchemy import (Column, DateTime, Float, ForeignKey, Integer, String,
                        Text, create_engine)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

import os

# CODE_RECALL_DATA — другая папка данных (например, для отдельной тестовой копии)
DATA_DIR = Path(os.getenv("CODE_RECALL_DATA") or Path(__file__).resolve().parent.parent / "data")
DATA_DIR.mkdir(exist_ok=True)

engine = create_engine(f"sqlite:///{DATA_DIR / 'recall.db'}",
                       connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()


class Reference(Base):
    """Эталон: то, что учим. Код хранится в версиях."""
    __tablename__ = "references"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    filename = Column(String, nullable=False, index=True)
    tag = Column(String, default="")
    difficulty = Column(Integer, default=3)  # 1..5
    notes = Column(Text, default="")
    task = Column(Text, default="")  # описание задачи «с нуля» (словами, без кода)
    due_at = Column(DateTime, nullable=True)  # следующее повторение; None = новый
    # состояние FSRS (пересчитывается по истории попыток, см. review.replay)
    fsrs_s = Column(Float, nullable=True)  # стабильность, дни
    fsrs_d = Column(Float, nullable=True)  # сложность 1..10
    last_review = Column(DateTime, nullable=True)
    reps = Column(Integer, default=0)
    lapses = Column(Integer, default=0)
    block_states = Column(Text, default="{}")  # JSON: прогресс FSRS по каждому блоку
    python = Column(Text, default="")  # окружение для ядра: путь к .venv / python; "" — окружение приложения
    heavy = Column(Text, default="[]")  # JSON: названия тяжёлых блоков (пропуск/кэш при автозапуске)
    block_times = Column(Text, default="{}")  # JSON: {блок: мс последнего запуска кода эталона}
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    versions = relationship("RefVersion", back_populates="reference",
                            order_by="RefVersion.number",
                            cascade="all, delete-orphan")
    tests = relationship("Test", back_populates="reference", order_by="Test.id",
                         cascade="all, delete-orphan")
    attempts = relationship("Attempt", back_populates="reference",
                            order_by="Attempt.started_at",
                            cascade="all, delete-orphan")

    @property
    def current(self):
        return self.versions[-1] if self.versions else None


class RefVersion(Base):
    """Версия эталона: повторная загрузка того же файла создаёт новую."""
    __tablename__ = "ref_versions"
    id = Column(Integer, primary_key=True)
    reference_id = Column(Integer, ForeignKey("references.id"), nullable=False)
    number = Column(Integer, nullable=False)
    source = Column(Text, nullable=False)
    content_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    reference = relationship("Reference", back_populates="versions")
    cells = relationship("RefCell", back_populates="version",
                         order_by="RefCell.position",
                         cascade="all, delete-orphan")


class RefCell(Base):
    """Логический блок эталона (ячейка). Название уникально в версии."""
    __tablename__ = "ref_cells"
    id = Column(Integer, primary_key=True)
    version_id = Column(Integer, ForeignKey("ref_versions.id"), nullable=False)
    position = Column(Integer, nullable=False)
    kind = Column(String, default="code")  # imports/class/function/train/code/main/markdown
    title = Column(String, default="")
    code = Column(Text, default="")
    description = Column(Text, default="")  # словесное описание (без кода)

    version = relationship("RefVersion", back_populates="cells")


class Test(Base):
    """Тест привязан к эталону и к блоку по названию — так он переживает версии.
    Если блока с таким названием в текущей версии нет, тест «без блока»."""
    __tablename__ = "tests"
    id = Column(Integer, primary_key=True)
    reference_id = Column(Integer, ForeignKey("references.id"), nullable=False)
    block = Column(String, default="")  # название блока; "" = тест на весь код
    name = Column(String, default="")
    code = Column(Text, default="")  # Python; результат — значение последнего выражения
    mode = Column(String, default="match")  # match: как у эталона; assert: должно быть True
    approved = Column(Integer, default=1)  # 0 — предложен LLM, ждёт подтверждения
    broken = Column(Text, default="")  # не проходит на эталоне: текст ошибки

    reference = relationship("Reference", back_populates="tests")


class Attempt(Base):
    """Попытка решения задания."""
    __tablename__ = "attempts"
    id = Column(Integer, primary_key=True)
    reference_id = Column(Integer, ForeignKey("references.id"), nullable=False)
    version_id = Column(Integer, ForeignKey("ref_versions.id"), nullable=False)
    mode = Column(String, default="cells")  # scratch | cells | gaps | block
    status = Column(String, default="active")  # active | checking | submitted | abandoned
    started_at = Column(DateTime, default=datetime.now)
    finished_at = Column(DateTime, nullable=True)
    total_ms = Column(Integer, default=0)
    cells = Column(Text, default="[]")  # JSON: [{block, given, code, time_ms, hint}]
    task = Column(Text, default="{}")  # JSON: что показали пользователю
    score = Column(Integer, nullable=True)  # 0..100 (этап 3–4)
    report = Column(Text, default="")  # JSON-отчёт
    grade_auto = Column(Integer, nullable=True)  # 1 забыл, 2 трудно, 3 нормально, 4 легко
    grade = Column(Integer, nullable=True)  # итоговый уровень (идёт в расписание)
    grade_manual = Column(Integer, default=0)  # 1 — уровень поставлен вручную

    reference = relationship("Reference", back_populates="attempts")


class Setting(Base):
    __tablename__ = "settings"
    key = Column(String, primary_key=True)
    value = Column(Text, default="")


def init_db():
    Base.metadata.create_all(engine)
    # Простая миграция: добавляем колонки, появившиеся в новых этапах.
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            have = {r[1] for r in conn.exec_driver_sql(f'PRAGMA table_info("{table.name}")')}
            for col in table.columns:
                if col.name not in have:
                    default = col.default.arg if col.default is not None and not callable(col.default.arg) else None
                    sql_default = f" DEFAULT {default!r}" if isinstance(default, (int, str)) else ""
                    conn.exec_driver_sql(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" '
                                         f'{col.type.compile(engine.dialect)}{sql_default}')


def get_setting(db, key, default=""):
    row = db.get(Setting, key)
    return row.value if row else default


def set_setting(db, key, value):
    row = db.get(Setting, key)
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))
