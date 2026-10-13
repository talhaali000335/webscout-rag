"""Tiny on-disk vector store (numpy). Replaces the ChromaDB server to save ~200-300 MB RAM.

A scraped page has at most a few hundred chunks, so a brute-force cosine search
(one matrix-vector product) takes well under a millisecond. No extra server needed.
"""
import json
import os
import time
from collections import OrderedDict
from pathlib import Path

import numpy as np

from .config import settings

_cache: "OrderedDict[str, tuple]" = OrderedDict()   # cid -> (mtime, emb, meta)
_MAX_CACHED = 3


def _dir() -> Path:
    d = Path(settings.data_dir) / "vectors"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(cid: str, embeddings, chunks: list) -> None:
    emb = np.asarray(embeddings, dtype=np.float32)
    emb /= np.linalg.norm(emb, axis=1, keepdims=True) + 1e-9
    d = _dir()
    tmp_npy, tmp_json = d / f"{cid}.npy.tmp", d / f"{cid}.json.tmp"
    with open(tmp_npy, "wb") as f:
        np.save(f, emb)
    tmp_json.write_text(json.dumps(chunks))
    os.replace(tmp_npy, d / f"{cid}.npy")
    os.replace(tmp_json, d / f"{cid}.json")
    _cache.pop(cid, None)
    cleanup()


def _load(cid: str):
    npy = _dir() / f"{cid}.npy"
    if not npy.exists():
        raise FileNotFoundError(cid)
    mtime = npy.stat().st_mtime
    hit = _cache.get(cid)
    if hit and hit[0] == mtime:
        _cache.move_to_end(cid)
        return hit[1], hit[2]
    emb = np.load(npy)
    meta = json.loads((_dir() / f"{cid}.json").read_text())
    _cache[cid] = (mtime, emb, meta)
    while len(_cache) > _MAX_CACHED:
        _cache.popitem(last=False)
    return emb, meta


def search(cid: str, query_vec, k: int):
    """Returns [(chunk_dict, cosine_similarity)] best first."""
    emb, meta = _load(cid)
    q = np.asarray(query_vec, dtype=np.float32)
    q /= np.linalg.norm(q) + 1e-9
    sims = emb @ q
    k = min(k, len(sims))
    idx = np.argpartition(-sims, k - 1)[:k]
    idx = idx[np.argsort(-sims[idx])]
    return [(meta[i], float(sims[i])) for i in idx]


def first_chunks(cid: str, n: int):
    """The first n chunks in page order (used for "summarize this page" style questions)."""
    _, meta = _load(cid)
    return meta[:n]


def cleanup() -> None:
    cutoff = time.time() - settings.vector_ttl_days * 86400
    for p in _dir().iterdir():
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
        except OSError:
            pass