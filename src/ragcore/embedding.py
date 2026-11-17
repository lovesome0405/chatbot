"""임베딩 인터페이스.

- FakeEmbedder: 토큰 해시 기반 결정적 벡터. CI 제어 흐름 검증용이며 **의미 검색 품질을 나타내지 않는다**.
- E5OnnxEmbedder: intfloat/multilingual-e5-small (모델 카드 기준)
    * 입력 접두사: 질의 "query: ", 문서 "passage: "
    * 평균 풀링(attention mask) 후 L2 정규화, 최대 512 토큰, 384차원
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Protocol

import numpy as np

from . import textnorm

DIM = 384
QUERY_PREFIX = "query: "
PASSAGE_PREFIX = "passage: "


class Embedder(Protocol):
    name: str
    dim: int

    def embed_queries(self, texts: list[str]) -> np.ndarray: ...
    def embed_passages(self, texts: list[str]) -> np.ndarray: ...


class FakeEmbedder:
    name = "fake-hash-v1"
    dim = DIM

    def _one(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        for t in textnorm.tokens(text):
            h = int(hashlib.md5(t.encode()).hexdigest(), 16)
            v[h % self.dim] += 1.0 if (h >> 9) & 1 else -1.0
        n = np.linalg.norm(v)
        return v / n if n else v

    def embed_queries(self, texts):
        return np.stack([self._one(t) for t in texts]) if texts else np.zeros((0, self.dim), np.float32)

    def embed_passages(self, texts):
        return self.embed_queries(texts)


class E5OnnxEmbedder:
    dim = DIM
    max_tokens = 512

    def __init__(self, model_dir: str, revision: str, threads: int = 0):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        d = Path(model_dir)
        manifest = json.loads((d / "MANIFEST.json").read_text()) if (d / "MANIFEST.json").exists() else {}
        if manifest and manifest.get("revision") != revision:
            raise RuntimeError(f"e5 모델 리비전 불일치: {manifest.get('revision')} != {revision} (재다운로드·재색인 필요)")
        self.name = f"multilingual-e5-small@{revision[:7]}"
        self.tok = Tokenizer.from_file(str(d / "onnx" / "tokenizer.json"))
        self.tok.enable_truncation(self.max_tokens)
        self.tok.enable_padding(pad_id=1, pad_token="<pad>")
        so = ort.SessionOptions()
        if threads:
            so.intra_op_num_threads = threads
        self.sess = ort.InferenceSession(str(d / "onnx" / "model.onnx"), so, providers=["CPUExecutionProvider"])
        self.input_names = {i.name for i in self.sess.get_inputs()}

    def _encode(self, texts: list[str], batch: int = 16) -> np.ndarray:
        outs = []
        for i in range(0, len(texts), batch):
            enc = self.tok.encode_batch(texts[i : i + batch])
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self.input_names:
                feed["token_type_ids"] = np.zeros_like(ids)
            hidden = self.sess.run(None, feed)[0]  # last_hidden_state [b, t, 384]
            m = mask[..., None].astype(np.float32)
            pooled = (hidden * m).sum(axis=1) / np.clip(m.sum(axis=1), 1e-9, None)
            pooled /= np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12, None)
            outs.append(pooled.astype(np.float32))
        return np.concatenate(outs) if outs else np.zeros((0, self.dim), np.float32)

    def embed_queries(self, texts):
        return self._encode([QUERY_PREFIX + t for t in texts])

    def embed_passages(self, texts):
        return self._encode([PASSAGE_PREFIX + t for t in texts])


def build_embedder(settings) -> Embedder:
    if settings.embedder == "e5-onnx":
        return E5OnnxEmbedder(settings.e5_model_dir, settings.e5_revision)
    if settings.embedder == "fake":
        return FakeEmbedder()
    raise ValueError(f"unknown embedder {settings.embedder}")
