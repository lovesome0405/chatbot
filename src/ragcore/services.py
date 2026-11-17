"""설정에서 엔진 구성요소를 만든다. .env가 있으면 읽는다(이미 있는 환경변수는 덮어쓰지 않음)."""

from __future__ import annotations

import os
from pathlib import Path

from .config import Settings
from .embedding import build_embedder
from .engine import Engine
from .generation import build_generator
from .registry import ROOT, build_adapters
from .store import PgStore


def load_dotenv(path: Path = ROOT / ".env"):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def build(settings: Settings | None = None, **overrides) -> Engine:
    load_dotenv()
    settings = settings or Settings()
    for k, v in overrides.items():
        setattr(settings, k, v)
    if not Path(settings.e5_model_dir).is_absolute():
        settings.e5_model_dir = str(ROOT / settings.e5_model_dir)
    store = PgStore(settings.database_url)
    store.init_schema()
    return Engine(settings, store, build_embedder(settings), build_generator(settings), build_adapters())
