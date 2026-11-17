"""엔진 설정. 모든 값은 환경변수로 덮어쓸 수 있다(.env.example 참고).

검색 시작값(RRF k=60, 각 목록 상위 10, 최종 4조각)은 평가 결과로 조정하기 위한 초기값이다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def _env_int(name: str, default: int) -> int:
    return int(_env(name, str(default)))


def _env_bool(name: str, default: bool) -> bool:
    return _env(name, "1" if default else "0").lower() in {"1", "true", "yes", "on"}


def _parse_keys(raw: str) -> dict[str, str]:
    """RAG_APP_KEYS="lolypoly:키1,maru:키2" → {키1: lolypoly, 키2: maru}. 키→프로젝트(서버가 범위 결정)."""
    out: dict[str, str] = {}
    for part in filter(None, (p.strip() for p in raw.split(","))):
        project, _, key = part.partition(":")
        if project and key:
            out[key] = project
    return out


@dataclass
class Settings:
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL", "postgresql://rag:rag@127.0.0.1:54329/rag"))
    # 임베딩: fake(결정적, CI용) | e5-onnx(실제 multilingual-e5-small)
    embedder: str = field(default_factory=lambda: _env("RAG_EMBEDDER", "fake"))
    e5_model_dir: str = field(default_factory=lambda: _env("RAG_E5_MODEL_DIR", "models/multilingual-e5-small"))
    e5_revision: str = field(default_factory=lambda: _env("RAG_E5_REVISION", "614241f622f53c4eeff9890bdc4f31cfecc418b3"))
    # 생성: fake(결정적 발췌형) | ollama
    generator: str = field(default_factory=lambda: _env("RAG_GENERATOR", "fake"))
    ollama_url: str = field(default_factory=lambda: _env("OLLAMA_URL", "http://127.0.0.1:11434"))
    ollama_model: str = field(default_factory=lambda: _env("OLLAMA_MODEL", "qwen2.5:3b"))
    ollama_format: str = field(default_factory=lambda: _env("OLLAMA_FORMAT", "json"))
    ollama_timeout_s: int = field(default_factory=lambda: _env_int("OLLAMA_TIMEOUT_S", 180))
    # 검색 시작값
    keyword_top_n: int = field(default_factory=lambda: _env_int("RAG_KEYWORD_TOP_N", 10))
    vector_top_n: int = field(default_factory=lambda: _env_int("RAG_VECTOR_TOP_N", 10))
    rrf_k: int = field(default_factory=lambda: _env_int("RAG_RRF_K", 60))
    final_top_k: int = field(default_factory=lambda: _env_int("RAG_FINAL_TOP_K", 4))
    max_chunks_per_source: int = field(default_factory=lambda: _env_int("RAG_MAX_CHUNKS_PER_SOURCE", 4))
    retrieval_mode: str = field(default_factory=lambda: _env("RAG_RETRIEVAL_MODE", "hybrid"))  # keyword|vector|hybrid
    # 범위: 앱 자격 → 프로젝트. 요청 본문으로 범위를 넓힐 수 없다.
    app_keys: dict[str, str] = field(default_factory=lambda: _parse_keys(_env("RAG_APP_KEYS", "")))
    # 정적 웹(MARU) 공개 중계 엔드포인트: 고정 프로젝트 1개에만 묶인다.
    public_project: str = field(default_factory=lambda: _env("RAG_PUBLIC_PROJECT", "maru"))
    public_origins: list[str] = field(default_factory=lambda: [o for o in _env("RAG_PUBLIC_ORIGINS", "http://127.0.0.1:8765").split(",") if o])
    # 평가·데모에서만 기준 시각을 요청으로 받는다(운영 기본 off)
    allow_reference_time: bool = field(default_factory=lambda: _env_bool("RAG_ALLOW_REFERENCE_TIME", False))
    timezone: str = "Asia/Seoul"


def get_settings() -> Settings:
    return Settings()
