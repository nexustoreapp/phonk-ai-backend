import os
import json
import time
import shutil
import zipfile
import base64
import tempfile
import re
import requests

from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from flp_corpus.extractor_v1 import build_corpus, safe_mkdir

router = APIRouter(prefix="/flp", tags=["FLP Corpus"])

CORPUS_OUT_DIR = "corpus_out"


# =========================
# GitHub Upload (Contents API)
# =========================

def _gh_headers(token: str):
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "PHONK-AI",
    }


def github_put_file(repo: str, token: str, repo_path: str, content_bytes: bytes, message: str):
    url = f"https://api.github.com/repos/{repo}/contents/{repo_path}"
    headers = _gh_headers(token)

    # Se já existe, pega sha
    r = requests.get(url, headers=headers, timeout=30)
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

    w = requests.put(url, headers=headers, json=payload, timeout=60)
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
    repo = os.getenv("GITHUB_REPO")  # "user/repo"

    if not token or not repo:
        return {"status": "skipped", "reason": "missing_GITHUB_TOKEN_or_GITHUB_REPO"}

    corpus_id = os.path.basename(corpus_path.rstrip("/"))
    base_repo_dir = f"flp_corpus_storage/{corpus_id}"

    # index
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

    # projects
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
            if os.path.getsize(fp) > 5 * 1024 * 1024:  # 5MB
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


# =========================
# Google Drive URL helpers
# =========================

_GDRIVE_FILE_ID_RE = re.compile(r"(?:/d/|id=)([a-zA-Z0-9_-]{10,})")


def extract_gdrive_file_id(url: str) -> str | None:
    m = _GDRIVE_FILE_ID_RE.search(url)
    return m.group(1) if m else None


def download_from_url(url: str, dst_path: str, max_bytes: int = 2 * 1024**3):
    """
    Baixa arquivo via HTTP stream.
    max_bytes: segurança (default 2GB).
    """
    with requests.get(url, stream=True, timeout=(30, 1800)) as r:
        r.raise_for_status()
        total = 0
        with open(dst_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(status_code=413, detail="Arquivo muito grande (limite interno).")


def download_google_drive_share(url: str, dst_path: str, max_bytes: int = 2 * 1024**3):
    """
    Suporta links do Drive tipo:
    - https://drive.google.com/file/d/FILE_ID/view?...
    - https://drive.google.com/open?id=FILE_ID
    - https://drive.google.com/uc?id=FILE_ID&export=download
    Para arquivo grande, o Drive pede confirmação. A gente pega o token e continua.
    """
    file_id = extract_gdrive_file_id(url)
    if not file_id:
        raise HTTPException(status_code=400, detail="Link do Google Drive inválido (não achei o FILE_ID).")

    session = requests.Session()
    base = "https://drive.google.com/uc"
    params = {"id": file_id, "export": "download"}

    r = session.get(base, params=params, stream=True, timeout=(30, 180))
    if r.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Falha ao acessar Google Drive (status {r.status_code}).")

    # Se vier arquivo direto, terá header de download
    if "content-disposition" in r.headers:
        total = 0
        with open(dst_path, "wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(status_code=413, detail="Arquivo muito grande (limite interno).")
        return

    # Se não veio direto, o Drive devolveu HTML pedindo confirmação.
    # Pegamos o confirm token pelo cookie.
    confirm = None
    for k, v in session.cookies.items():
        if k.startswith("download_warning"):
            confirm = v
            break

    if not confirm:
        # fallback: tenta achar confirm= no HTML
        try:
            text = r.text
            m = re.search(r"confirm=([0-9A-Za-z_]+)", text)
            if m:
                confirm = m.group(1)
        except Exception:
            confirm = None

    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Google Drive pediu confirmação mas não consegui obter token. "
                   "Tenta gerar link direto (uc?id=...&export=download) ou deixa o arquivo público.",
        )

    params2 = {"id": file_id, "export": "download", "confirm": confirm}
    r2 = session.get(base, params=params2, stream=True, timeout=(30, 1800))
    r2.raise_for_status()

    total = 0
    with open(dst_path, "wb") as f:
        for chunk in r2.iter_content(1024 * 1024):
            if not chunk:
                continue
            f.write(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise HTTPException(status_code=413, detail="Arquivo muito grande (limite interno).")


# =========================
# Request body model
# =========================

class IngestUrlBody(BaseModel):
    url: str


# =========================
# Endpoints
# =========================

@router.post("/ingest")
async def ingest_flp_archives(file: UploadFile = File(...)):
    """
    Upload normal (se você quiser usar).
    """
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

    # lê totals/pending (debug)
    index_path = os.path.join(corpus_path, "corpus_index.json")
    totals = {}
    pending = []
    if os.path.isfile(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            idx = json.load(f)
            totals = idx.get("totals", {})
            pending = idx.get("pending_archives", [])

    gh = upload_corpus_jsons_to_github(corpus_path)

    shutil.rmtree(archives_dir, ignore_errors=True)
    try:
        if os.path.isfile(upload_path):
            os.remove(upload_path)
    except Exception:
        pass

    return {
        "status": "ok",
        "mode": "upload",
        "corpus_path": corpus_path,
        "totals": totals,
        "pending_archives": pending,
        "github": gh,
    }


@router.post("/ingest/url")
def ingest_flp_from_url(body: IngestUrlBody):
    """
    NOVO: Você manda só o LINK (Google Drive recomendado).
    O servidor baixa o zip grande por trás e processa.
    """
    url = (body.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL vazia.")

    safe_mkdir("flp_uploads")
    safe_mkdir(CORPUS_OUT_DIR)

    ts = int(time.time())
    tmp_zip = os.path.join("flp_uploads", f"remote_{ts}.zip")

    # Baixa (Drive ou URL direta)
    try:
        if "drive.google.com" in url:
            download_google_drive_share(url, tmp_zip)
        else:
            download_from_url(url, tmp_zip)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Falha ao baixar URL: {e}")

    # Extrai
    archives_dir = os.path.join("flp_uploads", f"batch_{ts}")
    safe_mkdir(archives_dir)

    try:
        with zipfile.ZipFile(tmp_zip, "r") as z:
            z.extractall(archives_dir)
    except Exception as e:
        shutil.rmtree(archives_dir, ignore_errors=True)
        try:
            os.remove(tmp_zip)
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=f"O arquivo baixado não é um ZIP válido: {e}")

    # Build corpus
    corpus_path = build_corpus(archives_dir=archives_dir, output_dir=CORPUS_OUT_DIR)

    # lê totals/pending (debug)
    index_path = os.path.join(corpus_path, "corpus_index.json")
    totals = {}
    pending = []
    if os.path.isfile(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            idx = json.load(f)
            totals = idx.get("totals", {})
            pending = idx.get("pending_archives", [])

    # GitHub persist
    gh = upload_corpus_jsons_to_github(corpus_path)

    # cleanup
    shutil.rmtree(archives_dir, ignore_errors=True)
    try:
        os.remove(tmp_zip)
    except Exception:
        pass

    return {
        "status": "ok",
        "mode": "url",
        "source_url": url,
        "corpus_path": corpus_path,
        "totals": totals,
        "pending_archives": pending,
        "github": gh,
    }