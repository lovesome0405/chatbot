-- RAG 공통 엔진 스키마 (PostgreSQL 15+ / pgvector 0.5+). 로컬 Docker 또는 Supabase의 별도 DB에서 동일하게 실행.
-- 참고: Supabase hybrid search 가이드(FTS + pgvector + RRF), pgvector-python 예제. SQL은 이 프로젝트용으로 새로 작성.
-- 코퍼스가 작아 ANN 인덱스 없이 정확 검색(순차 스캔 + <=>)을 사용한다. 수만 조각 이상이면 HNSW 인덱스를 추가한다.

create extension if not exists vector;

create table if not exists rag_document (
    id              bigint generated always as identity primary key,
    project         text        not null,
    source_id       text        not null,
    collection      text        not null,
    title           text        not null,
    body            text,
    url             text,
    language        text        not null,
    content_level   text        not null check (content_level in ('body', 'title_only')),
    source_type     text        not null check (source_type in ('public_original', 'repository_data', 'synthetic')),
    published_at    date,
    checked_at      timestamptz,
    valid_from      date,
    valid_to        date,
    is_public       boolean     not null default true,
    metadata        jsonb       not null default '{}'::jsonb,
    version         text        not null,
    content_hash    text        not null,
    meta_hash       text        not null,
    embed_model     text        not null,
    chunker_version text        not null,
    last_seen_run   bigint,
    updated_at      timestamptz not null default now(),
    unique (project, source_id)
);

create table if not exists rag_chunk (
    id           bigint generated always as identity primary key,
    document_id  bigint not null references rag_document (id) on delete cascade,
    project      text   not null,
    chunk_key    text   not null,
    locator      text   not null,
    text         text   not null,
    search_text  text   not null,
    tsv          tsvector generated always as (to_tsvector('simple', search_text)) stored,
    structured   jsonb  not null default '{}'::jsonb,
    embedding    vector(384) not null,
    unique (document_id, chunk_key)
);

create index if not exists rag_chunk_project_idx on rag_chunk (project);
create index if not exists rag_chunk_document_idx on rag_chunk (document_id);
create index if not exists rag_chunk_tsv_idx on rag_chunk using gin (tsv);
create index if not exists rag_document_scope_idx on rag_document (project, is_public);
-- 정형 조회(metadata @> '{...}')용. @>만 쓰므로 더 작은 jsonb_path_ops (Supabase best practices: advanced-jsonb-indexing)
create index if not exists rag_document_meta_idx on rag_document using gin (metadata jsonb_path_ops);

create table if not exists rag_sync_run (
    id           bigint generated always as identity primary key,
    project      text        not null,
    started_at   timestamptz not null default now(),
    finished_at  timestamptz,
    status       text        not null default 'running' check (status in ('running', 'success', 'partial', 'failed')),
    collections  jsonb       not null default '{}'::jsonb,
    stats        jsonb       not null default '{}'::jsonb
);

-- v0.5.0: 미리 만든 답(자주 묻는 질문). 자료가 바뀌면(data_version) 쓰지 않는다. 시점에 따라 달라지는 답은 저장하지 않는다
create table if not exists rag_answer_cache (
    project      text        not null,
    cache_key    text        not null,
    data_version text        not null,
    payload      jsonb       not null,
    source       text        not null default 'live',      -- live | warm
    created_at   timestamptz not null default now(),
    hits         integer     not null default 0,
    primary key (project, cache_key)
);
