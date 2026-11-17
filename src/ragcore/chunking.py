"""제목/절/문단 단위 분할과 표 행 분할.

- 문단이 MAX_CHARS를 넘으면 문장 경계에서 자른다(e5-small 최대 512토큰 안쪽 유지).
- 표는 한 행 = 한 조각. 열 제목과 행 값을 "열: 값" 형태로 함께 둔다. 병합 셀(rowspan)은 호출 측에서 펼쳐 전달한다.
- CHUNKER_VERSION을 바꾸면 적재 시 해당 프로젝트 문서를 다시 분할·임베딩한다.
"""

from __future__ import annotations

import re

from .models import Chunk

CHUNKER_VERSION = "v1-2026-11-17"
MAX_CHARS = 600
_SENT = re.compile(r"(?<=[.!?。다요])\s+")


def _split_long(text: str) -> list[str]:
    if len(text) <= MAX_CHARS:
        return [text]
    parts, buf = [], ""
    for sent in _SENT.split(text):
        if buf and len(buf) + len(sent) + 1 > MAX_CHARS:
            parts.append(buf.strip())
            buf = ""
        buf += sent + " "
    if buf.strip():
        parts.append(buf.strip())
    return parts


def split_sections(title: str, body: str) -> list[Chunk]:
    """'# 제목' / '## 절' 마크다운식 머리말과 빈 줄 문단을 기준으로 나눈다."""
    chunks: list[Chunk] = []
    section = title
    sec_no, para_no = 0, 0
    for block in re.split(r"\n\s*\n", body.strip()):
        block = block.strip()
        if not block:
            continue
        m = re.match(r"^(#{1,6})\s+(.+?)\s*(?:\n|$)", block)
        if m:
            sec_no += 1
            para_no = 0
            section = m.group(2)
            block = block[m.end():].strip()
            if not block:
                continue
        for piece in _split_long(block):
            para_no += 1
            chunks.append(Chunk(
                chunk_key=f"s{sec_no:02d}-p{para_no:02d}",
                locator=f"{title} > {section} > 문단 {para_no}" if section != title else f"{title} > 문단 {para_no}",
                text=piece,
            ))
    return chunks


def table_row_chunks(caption: str, headers: list[str], rows: list[list[str]], key_prefix: str = "row",
                     row_meta: list[dict] | None = None) -> list[Chunk]:
    chunks = []
    for i, row in enumerate(rows, start=1):
        cells = [f"{h}: {v}" for h, v in zip(headers, row) if v and v.strip()]
        label = " / ".join(v for v in row[:2] if v)
        chunks.append(Chunk(
            chunk_key=f"{key_prefix}-{i:02d}",
            locator=f"{caption} > 행 {i} ({label})",
            text=f"[{caption}] " + " | ".join(cells),
            structured={"row": i, "cells": dict(zip(headers, row))} | ((row_meta or [{}] * len(rows))[i - 1]),
        ))
    return chunks
