"""어댑터 등록부.

- 코드 어댑터: lolypoly, maru (adapters/ 패키지)
- 파일 어댑터: data/domains/*.json — 문서 목록만 있는 도메인은 코드 없이 등록된다(기본 문서 검색만 지원).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .adapter import Adapter, SyncBatch
from .chunking import split_sections
from .models import Document

ROOT = Path(__file__).resolve().parents[2]


class JsonDomainAdapter(Adapter):
    def __init__(self, path: Path):
        spec = json.loads(path.read_text(encoding="utf-8"))
        self.spec = spec
        self.project = spec["project"]
        self.allowed_collections = set(spec["collections"])
        self.aliases = spec.get("aliases", {})

    def load(self) -> SyncBatch:
        docs = []
        for d in self.spec["documents"]:
            doc = Document(project=self.project, source_id=d["source_id"], collection=d["collection"], title=d["title"],
                           body=d["body"], url=d.get("url"), language=d.get("language", "ko"), content_level="body",
                           source_type=d.get("source_type", "synthetic"))
            doc.chunks = split_sections(doc.title, doc.body)
            docs.append(doc)
        return SyncBatch(docs, {c: "complete" for c in self.allowed_collections})


def build_adapters(data_dir: Path | None = None) -> dict[str, Adapter]:
    data_dir = data_dir or ROOT / "data"
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from adapters.lolypoly.adapter import LolypolyAdapter
    from adapters.maru.adapter import MaruAdapter

    out: dict[str, Adapter] = {
        "lolypoly": LolypolyAdapter(data_dir / "lolypoly"),
        "maru": MaruAdapter(data_dir / "maru"),
    }
    for f in sorted((data_dir / "domains").glob("*.json")):
        a = JsonDomainAdapter(f)
        out[a.project] = a
    return out
