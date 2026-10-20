"""conftest.py, который CODE RECALL кладёт в корень каждого прогона тестов.

Фикстуры для ML (доступны во всех тестах):
    device   — "cuda", "mps" или "cpu"
    seed     — фиксирует random / numpy / torch и возвращает 0
    data_dir — pathlib.Path к data/ задачи
"""
import os
import pathlib
import random

import pytest

os.environ.setdefault("MPLBACKEND", "Agg")


@pytest.fixture
def seed():
    random.seed(0)
    try:
        import numpy as np
        np.random.seed(0)
    except ImportError:
        pass
    try:
        import torch
        torch.manual_seed(0)
    except ImportError:
        pass
    return 0


@pytest.fixture(scope="session")
def device():
    try:
        import torch
    except ImportError:
        return "cpu"
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


@pytest.fixture(scope="session")
def data_dir():
    return pathlib.Path("data").resolve()
