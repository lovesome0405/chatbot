"""intfloat/multilingual-e5-small ONNX 파일을 고정 리비전으로 내려받고 sha256을 HF 메타데이터와 대조한다.

    python scripts/fetch_e5.py [--dir models/multilingual-e5-small] [--revision <sha>]

모델 라이선스: MIT (모델 카드 기준). 파일은 Git에 넣지 않는다(.gitignore: models/).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

REPO = "intfloat/multilingual-e5-small"
DEFAULT_REV = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
FILES = ["onnx/model.onnx", "onnx/tokenizer.json", "onnx/config.json", "1_Pooling/config.json"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="models/multilingual-e5-small")
    ap.add_argument("--revision", default=DEFAULT_REV)
    args = ap.parse_args()
    out = Path(args.dir)
    out.mkdir(parents=True, exist_ok=True)

    meta_url = f"https://huggingface.co/api/models/{REPO}/revision/{args.revision}?blobs=true"
    meta = json.load(urllib.request.urlopen(meta_url, timeout=60))
    blobs = {s["rfilename"]: s for s in meta["siblings"]}
    manifest = {"repo": REPO, "revision": meta.get("sha", args.revision), "files": {}}
    for name in FILES:
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        expected = (blobs.get(name, {}).get("lfs") or {}).get("sha256")
        if not target.exists() or (expected and _sha256(target) != expected):
            url = f"https://huggingface.co/{REPO}/resolve/{args.revision}/{name}"
            print(f"download {name}", file=sys.stderr)
            urllib.request.urlretrieve(url, target)
        actual = _sha256(target)
        if expected and actual != expected:
            print(f"sha256 mismatch for {name}: {actual} != {expected}", file=sys.stderr)
            return 1
        manifest["files"][name] = {"sha256": actual, "lfs_sha256_expected": expected, "bytes": target.stat().st_size}
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
