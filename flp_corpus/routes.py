import os
import json
import time
import shutil
import zipfile
import tempfile
import base64
import requests

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from flp_corpus.extractor_v1 import build_corpus, safe_mkdir

router = APIRouter(prefix="/flp", tags=["FLP Corpus"])

# No Render FREE o disco pode sumir. Por isso: persistimos no GitHub.
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
    """
    Cria/atualiza arquivo via GitHub Contents API.
    repo: "user/repo"
    repo_path: "pasta/arquivo.json"
    """
    url = f"https://api.github.com/repos/{repo}/contents/{repo_path}"
    headers = _gh_headers(token)

    # Se já existe, pega sha
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
    """
    Sobe apenas:
      - corpus_index.json
      - projects/*.json

    Não sobe áudio/zip/stems (pesado e não precisa).
    """
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPO")  # "user/repo"

    if not token or not repo:
        return {"status": "skipped", "reason": "missing_GITHUB_TOKEN_or_GITHUB_REPO"}

    corpus_id = os.path.basename(corpus_path.rstrip("/"))
    base_repo_dir = f"flp_corpus_storage/{corpus_id}"

    # 1) index
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

    # 2) projects
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

            # Segurança: não sobe json gigante
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
# Helpers
# =========================

def zip_folder(folder_path: str) -> str:
    """
    Zip uma pasta inteira e retorna o caminho do zip gerado.
    """
    folder_path = os.path.abspath(folder_path)
    base_dir = os.path.dirname(folder_path)
    folder_name = os.path.basename(folder_path)
    zip_path = os.path.join(base_dir, f"{folder_name}.zip")

    if os.path.isfile(zip_path):
        os.remove(zip_path)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(folder_path):
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, folder_path)
                z.write(full, arcname=os.path.join(folder_name, rel))

    return zip_path


# =========================
# Endpoints
# =========================

@router.post("/ingest")
async def ingest_flp_archives(file: UploadFile = File(...)):
    """
    Recebe um ZIP (batch_XX.zip) que contém vários zips FLP dentro.
    Gera corpus local (pode ser efêmero no Render FREE), e sobe o resultado (JSONs) pro GitHub.
    """
    safe_mkdir("flp_uploads")
    safe_mkdir(CORPUS_OUT_DIR)

    # 1) salva upload
    upload_path = os.path.join("flp_uploads", file.filename)

    with open(upload_path, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)

    # 2) extrai batch para pasta temporária de archives
    ts = int(time.time())
    archives_dir = os.path.join("flp_uploads", f"batch_{ts}")
    safe_mkdir(archives_dir)

    try:
        with zipfile.ZipFile(upload_path, "r") as z:
            z.extractall(archives_dir)
    except Exception:
        # se não for zip válido, move como archive unitário
        shutil.move(upload_path, os.path.join(archives_dir, os.path.basename(upload_path)))

    # 3) build corpus
    corpus_path = build_corpus(archives_dir=archives_dir, output_dir=CORPUS_OUT_DIR)

    # 4) sobe pro GitHub (persistência FREE)
    gh = upload_corpus_jsons_to_github(corpus_path)

    # 5) limpeza do batch (evita encher)
    shutil.rmtree(archives_dir, ignore_errors=True)
    try:
        if os.path.isfile(upload_path):
            os.remove(upload_path)
    except Exception:
        pass

    return {
        "status": "ok",
        "corpus_path": corpus_path,
        "github": gh,
    }


@router.post("/master/merge")
async def master_merge(files: list[UploadFile] = File(...)):
    """
    (Opcional) Junta vários corpus zips (se você tiver baixado) e devolve um MASTER zip.
    Obs: No seu fluxo atual com GitHub, você provavelmente nem vai precisar disso.
    """
    if not files or len(files) < 2:
        raise HTTPException(status_code=400, detail="Envie pelo menos 2 corpus zips.")

    tmp_root = tempfile.mkdtemp(prefix="phonk_master_")
    packs_dir = os.path.join(tmp_root, "packs")
    out_dir = os.path.join(tmp_root, "extracted")
    os.makedirs(packs_dir, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)

    extracted = []
    for up in files:
        pack_path = os.path.join(packs_dir, up.filename)
        with open(pack_path, "wb") as f:
            while True:
                chunk = await up.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)

        try:
            with zipfile.ZipFile(pack_path, "r") as z:
                z.extractall(out_dir)
            extracted.append(up.filename)
        except Exception as e:
            shutil.rmtree(tmp_root, ignore_errors=True)
            raise HTTPException(status_code=400, detail=f"ZIP inválido: {up.filename} ({e})")

    projects_out = os.path.join(tmp_root, "master_projects")
    os.makedirs(projects_out, exist_ok=True)

    seen = set()
    kept = 0
    dropped = 0

    for root, _, files2 in os.walk(out_dir):
        for fn in files2:
            if not fn.endswith(".json"):
                continue
            if os.path.basename(root) != "projects":
                continue

            src = os.path.join(root, fn)
            try:
                with open(src, "r", encoding="utf-8") as f:
                    pj = json.load(f)
            except Exception:
                continue

            title = (pj.get("title") or "").strip().lower()
            flps = pj.get("flp_files") or []
            flp_sha = None
            if flps and isinstance(flps, list) and flps[0].get("sha256"):
                flp_sha = flps[0]["sha256"]

            key = (flp_sha or pj.get("source_archive") or fn, title)

            if key in seen:
                dropped += 1
                continue

            seen.add(key)
            kept += 1

            dst = os.path.join(projects_out, fn)
            with open(dst, "w", encoding="utf-8") as f:
                json.dump(pj, f, ensure_ascii=False, indent=2)

    master_id = f"flp_master_{int(time.time())}"
    master_folder = os.path.join(tmp_root, master_id)
    os.makedirs(master_folder, exist_ok=True)

    shutil.move(projects_out, os.path.join(master_folder, "projects"))

    master_index = {
        "status": "ok",
        "master_id": master_id,
        "packs_received": extracted,
        "totals": {
            "projects_kept": kept,
            "duplicates_dropped": dropped
        }
    }

    with open(os.path.join(master_folder, "master_index.json"), "w", encoding="utf-8") as f:
        json.dump(master_index, f, ensure_ascii=False, indent=2)

    master_zip = zip_folder(master_folder)

    return FileResponse(
        master_zip,
        filename=os.path.basename(master_zip),
        media_type="application/zip"
    )