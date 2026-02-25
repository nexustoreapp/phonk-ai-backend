import os
import json
import time
import hashlib
import zipfile
from typing import Dict, List, Tuple, Optional

CORPUS_OUT_DIR = "corpus_out"


def _safe_mkdir(path: str):
    os.makedirs(path, exist_ok=True)


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, payload: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def list_corpora(base_dir: str = CORPUS_OUT_DIR) -> List[dict]:
    """
    Lista corpus_out/flp_corpus_* que existirem no disco.
    """
    if not os.path.isdir(base_dir):
        return []

    out = []
    for name in os.listdir(base_dir):
        full = os.path.join(base_dir, name)
        if os.path.isdir(full) and name.startswith("flp_corpus_"):
            idx = os.path.join(full, "corpus_index.json")
            out.append({
                "corpus_id": name,
                "path": full,
                "has_index": os.path.isfile(idx),
                "mtime": int(os.path.getmtime(full)),
            })

    out.sort(key=lambda x: x["mtime"])
    return out


def _project_dedupe_key(project_json: dict) -> Tuple[str, str]:
    """
    Chave de dedupe: (flp_sha, title_norm)
    - Se tiver FLP sha, usa
    - Senão usa sha do archive (quando disponível)
    """
    title = (project_json.get("title") or "").strip().lower()

    flps = project_json.get("flp_files") or []
    if flps and isinstance(flps, list) and flps[0].get("sha256"):
        return (flps[0]["sha256"], title)

    # fallback: tenta usar hash do source_archive (não garante, mas ajuda)
    src = (project_json.get("source_archive") or "").strip().lower()
    return (src, title)


def build_master_corpus(
    base_dir: str = CORPUS_OUT_DIR,
    master_prefix: str = "flp_master_",
) -> dict:
    """
    Junta todos os corpus_out/flp_corpus_* em um MASTER único:
      corpus_out/flp_master_<ts>/
        master_index.json
        projects/*.json

    Dedup:
      - remove projetos com mesma chave (flp_sha + title)
    """
    corpora = list_corpora(base_dir)
    ts = int(time.time())
    master_id = f"{master_prefix}{ts}"
    master_path = os.path.join(base_dir, master_id)
    projects_out = os.path.join(master_path, "projects")
    _safe_mkdir(projects_out)

    merged_projects = []
    seen = {}  # key -> master_project_id
    duplicates = []  # registros descartados

    for c in corpora:
        cpath = c["path"]
        pdir = os.path.join(cpath, "projects")
        if not os.path.isdir(pdir):
            continue

        for fn in os.listdir(pdir):
            if not fn.endswith(".json"):
                continue
            src_path = os.path.join(pdir, fn)
            try:
                pj = _read_json(src_path)
            except Exception:
                continue

            key = _project_dedupe_key(pj)
            if key in seen:
                duplicates.append({
                    "dropped_project_id": pj.get("project_id"),
                    "kept_project_id": seen[key],
                    "reason": "duplicate_flp_sha_or_source+title",
                    "source_corpus": c["corpus_id"],
                })
                continue

            # mantém
            seen[key] = pj.get("project_id") or fn.replace(".json", "")
            merged_projects.append({
                "project_id": pj.get("project_id"),
                "title": pj.get("title"),
                "stats": pj.get("stats", {}),
                "source_corpus": c["corpus_id"],
                "file": fn,
            })

            # copia o json do projeto pro master
            out_path = os.path.join(projects_out, fn)
            _write_json(out_path, pj)

    totals = {
        "source_corpora": len(corpora),
        "projects_kept": len(merged_projects),
        "duplicates_dropped": len(duplicates),
    }

    master_index = {
        "status": "ok",
        "master_id": master_id,
        "master_path": master_path,
        "created_at": ts,
        "sources": corpora,
        "projects": merged_projects,
        "duplicates": duplicates,
        "totals": totals,
    }

    _write_json(os.path.join(master_path, "master_index.json"), master_index)

    # ponte pro “último master”
    _write_json(os.path.join(base_dir, "LATEST_MASTER.json"), {
        "master_id": master_id,
        "master_path": master_path,
        "created_at": ts,
    })

    return master_index


def zip_master(master_path: str) -> str:
    """
    Gera um zip do master pra download.
    Retorna caminho do zip.
    """
    master_id = os.path.basename(master_path.rstrip("/"))
    zip_path = os.path.join(os.path.dirname(master_path), f"{master_id}.zip")

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for base, _, files in os.walk(master_path):
            for fn in files:
                full = os.path.join(base, fn)
                rel = os.path.relpath(full, master_path)
                z.write(full, arcname=os.path.join(master_id, rel))

    return zip_path
