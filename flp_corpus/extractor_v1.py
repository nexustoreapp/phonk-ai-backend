import os
import re
import json
import time
import shutil
import zipfile
import hashlib
import tempfile
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple

import numpy as np
import soundfile as sf


AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".aif", ".aiff", ".m4a"}
PROJECT_EXTS = {".flp"}
ARCHIVE_EXTS = {".zip", ".rar"}

# --------- helpers ---------

def sha256_file(path: str, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def safe_mkdir(path: str):
    os.makedirs(path, exist_ok=True)

def norm_name(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s

def now_ts() -> int:
    return int(time.time())

def is_suspicious_filename(name: str) -> bool:
    bad = (".exe", ".bat", ".cmd", ".scr", ".msi", ".apk", ".ps1", ".vbs", ".js")
    ln = name.lower()
    return ln.endswith(bad)

def audio_stats(path: str) -> Optional[Dict]:
    try:
        info = sf.info(path)
        sr = int(info.samplerate)
        frames = int(info.frames)
        ch = int(info.channels)
        dur = frames / sr if sr > 0 else None

        max_frames = min(frames, sr * 60)  # até 60s
        data, _ = sf.read(path, frames=max_frames, dtype="float32", always_2d=True)
        peak = float(np.max(np.abs(data))) if data.size else 0.0
        rms = float(np.sqrt(np.mean(np.square(data)))) if data.size else 0.0

        return {
            "path": path,
            "duration_seconds": float(dur) if dur is not None else None,
            "sample_rate": sr,
            "channels": ch,
            "frames": frames,
            "peak": peak,
            "rms": rms,
        }
    except Exception:
        return None

# --------- dataclasses ---------

@dataclass
class ProjectRef:
    project_id: str
    title: str
    source_archive: str
    flp_files: List[Dict]
    audio_files: List[Dict]
    other_files: List[Dict]
    suspicious_files: List[str]
    stats: Dict
    created_at: int

@dataclass
class CorpusIndex:
    corpus_id: str
    created_at: int
    projects: List[Dict]
    duplicates: Dict[str, List[str]]
    pending_archives: List[Dict]
    totals: Dict

# --------- archive extraction ---------

def extract_archive(archive_path: str, out_dir: str) -> Tuple[bool, str]:
    ext = os.path.splitext(archive_path)[1].lower()

    if ext == ".zip":
        try:
            with zipfile.ZipFile(archive_path, "r") as z:
                z.extractall(out_dir)
            return True, "ok"
        except Exception as e:
            return False, f"zip_error: {e}"

    if ext == ".rar":
        try:
            import rarfile  # opcional
            with rarfile.RarFile(archive_path) as rf:
                rf.extractall(out_dir)
            return True, "ok"
        except Exception as e:
            return False, f"rar_error: {e} (no Render free pode faltar suporte; recompacta em .zip)"

    return False, f"unsupported_archive: {ext}"

# --------- core extractor ---------

def scan_dir_for_files(root: str) -> Dict[str, List[str]]:
    buckets = {"flp": [], "audio": [], "other": [], "suspicious": []}
    for base, _, files in os.walk(root):
        for fn in files:
            full = os.path.join(base, fn)
            rel = os.path.relpath(full, root)
            if is_suspicious_filename(fn):
                buckets["suspicious"].append(rel)
                continue
            ext = os.path.splitext(fn)[1].lower()
            if ext in PROJECT_EXTS:
                buckets["flp"].append(rel)
            elif ext in AUDIO_EXTS:
                buckets["audio"].append(rel)
            else:
                buckets["other"].append(rel)
    return buckets

def build_project_id(title: str, flp_hash: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", norm_name(title)).strip("-")
    return f"{slug[:60]}-{flp_hash[:8]}"

def extract_project_from_archive(
    archive_path: str,
    work_dir: str,
    output_projects_dir: str,
) -> Tuple[Optional[ProjectRef], Optional[Dict]]:
    arc_name = os.path.basename(archive_path)
    tmp = os.path.join(work_dir, f"tmp_{now_ts()}_{hashlib.md5(arc_name.encode()).hexdigest()[:8]}")
    safe_mkdir(tmp)

    ok, msg = extract_archive(archive_path, tmp)
    if not ok:
        shutil.rmtree(tmp, ignore_errors=True)
        return None, {"archive": archive_path, "status": "pending", "reason": msg}

    buckets = scan_dir_for_files(tmp)

    flp_infos = []
    for rel in buckets["flp"]:
        p = os.path.join(tmp, rel)
        flp_infos.append({
            "rel_path": rel,
            "size_bytes": os.path.getsize(p),
            "sha256": sha256_file(p),
        })

    title = os.path.splitext(arc_name)[0]

    main_flp = None
    if flp_infos:
        main_flp = sorted(flp_infos, key=lambda x: x["size_bytes"], reverse=True)[0]

    project_id = build_project_id(
        title,
        main_flp["sha256"] if main_flp else sha256_file(archive_path)
    )

    audio_infos = []
    total_audio_dur = 0.0
    sr_hist = {}

    for rel in buckets["audio"]:
        p = os.path.join(tmp, rel)
        st = audio_stats(p)
        if st:
            st_out = dict(st)
            st_out["rel_path"] = rel
            st_out.pop("path", None)
            audio_infos.append(st_out)

            if st_out.get("duration_seconds"):
                total_audio_dur += float(st_out["duration_seconds"])

            sr = st_out.get("sample_rate")
            if sr:
                sr_hist[str(sr)] = sr_hist.get(str(sr), 0) + 1

    other_infos = []
    for rel in buckets["other"]:
        p = os.path.join(tmp, rel)
        other_infos.append({
            "rel_path": rel,
            "size_bytes": os.path.getsize(p),
            "ext": os.path.splitext(rel)[1].lower(),
        })

    stats = {
        "has_flp": bool(flp_infos),
        "flp_count": len(flp_infos),
        "audio_count": len(audio_infos),
        "other_count": len(other_infos),
        "suspicious_count": len(buckets["suspicious"]),
        "total_audio_duration_seconds_est": float(total_audio_dur),
        "sample_rate_histogram": sr_hist,
        "archive_size_bytes": os.path.getsize(archive_path),
    }

    proj = ProjectRef(
        project_id=project_id,
        title=title,
        source_archive=archive_path,
        flp_files=flp_infos,
        audio_files=audio_infos,
        other_files=other_infos,
        suspicious_files=buckets["suspicious"],
        stats=stats,
        created_at=now_ts(),
    )

    safe_mkdir(output_projects_dir)
    out_path = os.path.join(output_projects_dir, f"{project_id}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(asdict(proj), f, ensure_ascii=False, indent=2)

    shutil.rmtree(tmp, ignore_errors=True)
    return proj, None

def _collect_archives_recursive(archives_dir: str) -> List[str]:
    """
    Acha .zip/.rar em qualquer subpasta.
    """
    found = []
    for base, _, files in os.walk(archives_dir):
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext in ARCHIVE_EXTS:
                found.append(os.path.join(base, fn))
    return sorted(found)

def build_corpus(
    archives_dir: str,
    output_dir: str = "corpus_out",
) -> str:
    corpus_id = f"flp_corpus_{now_ts()}"
    corpus_path = os.path.join(output_dir, corpus_id)
    projects_dir = os.path.join(corpus_path, "projects")
    safe_mkdir(projects_dir)

    work_dir = tempfile.mkdtemp(prefix="flp_corpus_work_")

    projects: List[ProjectRef] = []
    pending: List[Dict] = []

    archives = _collect_archives_recursive(archives_dir)

    for arc in archives:
        proj, pend = extract_project_from_archive(
            archive_path=arc,
            work_dir=work_dir,
            output_projects_dir=projects_dir,
        )
        if proj:
            projects.append(proj)
        if pend:
            pending.append(pend)

    dup_map: Dict[str, List[str]] = {}
    for p in projects:
        if p.flp_files:
            key = p.flp_files[0]["sha256"]
        else:
            key = sha256_file(p.source_archive)
        dup_map.setdefault(key, []).append(p.project_id)

    duplicates = {h: ids for h, ids in dup_map.items() if len(ids) > 1}

    totals = {
        "archives_found": len(archives),
        "projects_built": len(projects),
        "pending_archives": len(pending),
        "projects_with_flp": sum(1 for p in projects if p.stats.get("has_flp")),
        "projects_without_flp": sum(1 for p in projects if not p.stats.get("has_flp")),
        "total_audio_files": sum(p.stats.get("audio_count", 0) for p in projects),
        "total_est_audio_duration_seconds": float(sum(p.stats.get("total_audio_duration_seconds_est", 0.0) for p in projects)),
    }

    index = CorpusIndex(
        corpus_id=corpus_id,
        created_at=now_ts(),
        projects=[{"project_id": p.project_id, "title": p.title, "stats": p.stats} for p in projects],
        duplicates=duplicates,
        pending_archives=pending,
        totals=totals,
    )

    with open(os.path.join(corpus_path, "corpus_index.json"), "w", encoding="utf-8") as f:
        json.dump(asdict(index), f, ensure_ascii=False, indent=2)

    shutil.rmtree(work_dir, ignore_errors=True)
    return corpus_path


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--archives_dir", required=True, help="Pasta com ZIP/RAR de FLP refs")
    ap.add_argument("--output_dir", default="corpus_out", help="Saída do corpus")
    args = ap.parse_args()

    out = build_corpus(args.archives_dir, args.output_dir)
    print(f"[OK] corpus gerado em: {out}")