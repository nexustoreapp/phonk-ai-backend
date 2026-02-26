import os
import json
import time
import shutil
import zipfile
import base64
import requests

from fastapi import APIRouter, UploadFile, File, HTTPException
from flp_corpus.extractor_v1 import build_corpus, safe_mkdir

router = APIRouter(prefix="/flp", tags=["FLP Corpus"])

CORPUS_OUT_DIR = "corpus_out"


def _gh_headers(token: str):
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "PHONK-AI",
    }


def github_put_file(repo: str, token: str, repo_path: str, content_bytes: bytes, message: str):
    url = f"https://api.github.com/repos/{repo}/contents/{repo_path}"
    headers = _gh_headers(token)

    r = requests.get(url, headers=headers)
    sha = None
    if r.status_code == 200:
        try:
            sha = r.json().get("sha")
        except Exception:
            sha = None

    payload = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode("utf-8"),
    }
    if sha:
        payload["sha"] = sha

    w = requests.put(url, headers=headers, json=payload)
    if w.status_code not in (200, 201):
        raise HTTPException(
            status_code=500,
            detail={
                "error": "github_put_failed",
                "status_code": w.status_code,
                "response": w.text[:4000],
                "repo_path": repo_path,
            },
        )

    return w.json()


def upload_corpus_jsons_to_github(corpus_path: str):
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPO")

    if not token or not repo:
        return {"status": "skipped", "reason": "missing_GITHUB_TOKEN_or_GITHUB_REPO"}

    corpus_id = os.path.basename(corpus_path.rstrip("/"))
    base_repo_dir = f"flp_corpus_storage/{corpus_id}"

    index_path = os.path.join(corpus_path, "corpus_index.json")
    if os.path.isfile(index_path):
        with open(index_path, "rb") as f:
            github_put_file(
                repo=repo,
                token=token,
                repo_path=f"{base_repo_dir}/corpus_index.json",
                content_bytes=f.read(),
                message=f"PHONK AI: add corpus index {corpus_id}",
            )

    projects_dir = os.path.join(corpus_path, "projects")
    uploaded = 0
    skipped_big = 0

    if os.path.isdir(projects_dir):
        for fn in os.listdir(projects_dir):
            if not fn.endswith(".json"):
                continue

            fp = os.path.join(projects_dir, fn)
            if not os.path.isfile(fp):
                continue

            if os.path.getsize(fp) > 5 * 1024 * 1024:
                skipped_big += 1
                continue

            with open(fp, "rb") as f:
                github_put_file(
                    repo=repo,
                    token=token,
                    repo_path=f"{base_repo_dir}/projects/{fn}",
                    content_bytes=f.read(),
                    message=f"PHONK AI: add project {fn} ({corpus_id})",
                )
            uploaded += 1

    return {
        "status": "ok",
        "repo": repo,
        "github_path": base_repo_dir,
        "projects_uploaded": uploaded,
        "projects_skipped_big": skipped_big,
    }


@router.post("/ingest")
async def ingest_flp_archives(file: UploadFile = File(...)):
    safe_mkdir("flp_uploads")
    safe_mkdir(CORPUS_OUT_DIR)

    upload_path = os.path.join("flp_uploads", file.filename)
    with open(upload_path, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)

    ts = int(time.time())
    archives_dir = os.path.join("flp_uploads", f"batch_{ts}")
    safe_mkdir(archives_dir)

    try:
        with zipfile.ZipFile(upload_path, "r") as z:
            z.extractall(archives_dir)
    except Exception:
        shutil.move(upload_path, os.path.join(archives_dir, os.path.basename(upload_path)))

    corpus_path = build_corpus(archives_dir=archives_dir, output_dir=CORPUS_OUT_DIR)

    # lê o index pra te mostrar a verdade no response
    index_path = os.path.join(corpus_path, "corpus_index.json")
    index_payload = {}
    if os.path.isfile(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            index_payload = json.load(f)

    gh = upload_corpus_jsons_to_github(corpus_path)

    shutil.rmtree(archives_dir, ignore_errors=True)
    try:
        if os.path.isfile(upload_path):
            os.remove(upload_path)
    except Exception:
        pass

    return {
        "status": "ok",
        "corpus_path": corpus_path,
        "totals": (index_payload.get("totals") if isinstance(index_payload, dict) else {}),
        "pending_archives": (index_payload.get("pending_archives") if isinstance(index_payload, dict) else []),
        "github": gh,
    }