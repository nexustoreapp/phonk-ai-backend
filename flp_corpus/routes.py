import os
import shutil
from fastapi import APIRouter, UploadFile, File
from flp_corpus.extractor_v1 import build_corpus, safe_mkdir

router = APIRouter(prefix="/flp", tags=["FLP Corpus"])

@router.post("/ingest")
async def ingest_flp_archives(file: UploadFile = File(...)):
    # recebe um ZIP com vários zips dentro, OU um zip de 10 em 10, etc.
    safe_mkdir("flp_uploads")
    path = os.path.join("flp_uploads", file.filename)

    with open(path, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)

    # extrai o zip recebido para uma pasta temporária de "archives"
    import zipfile, time
    ts = int(time.time())
    archives_dir = os.path.join("flp_uploads", f"batch_{ts}")
    safe_mkdir(archives_dir)

    try:
        with zipfile.ZipFile(path, "r") as z:
            z.extractall(archives_dir)
    except Exception:
        # se não for zip, assume que já é um archive unitário
        shutil.move(path, os.path.join(archives_dir, os.path.basename(path)))

    corpus_path = build_corpus(archives_dir=archives_dir, output_dir="corpus_out")

    return {
        "status": "ok",
        "corpus_path": corpus_path
    }
from fastapi.responses import FileResponse

from flp_corpus.master_builder import (
    list_corpora,
    build_master_corpus,
    zip_master,
    CORPUS_OUT_DIR,
)

@router.get("/corpora")
def corpora_list():
    """
    Lista todos os corpus flp_corpus_* criados (os 1–14).
    """
    return {
        "status": "ok",
        "base_dir": CORPUS_OUT_DIR,
        "corpora": list_corpora(CORPUS_OUT_DIR),
    }

@router.post("/master/build")
def master_build():
    """
    Constrói o MASTER juntando todos os corpora existentes.
    """
    idx = build_master_corpus(CORPUS_OUT_DIR)
    return idx

@router.get("/master/latest")
def master_latest():
    """
    Mostra qual é o último MASTER criado.
    """
    path = os.path.join(CORPUS_OUT_DIR, "LATEST_MASTER.json")
    if not os.path.isfile(path):
        return {"status": "empty", "detail": "Nenhum master criado ainda."}
    with open(path, "r", encoding="utf-8") as f:
        return {"status": "ok", "latest": json.load(f)}

@router.get("/master/download")
def master_download():
    """
    Gera ZIP do último master e devolve pra download.
    """
    latest_path = os.path.join(CORPUS_OUT_DIR, "LATEST_MASTER.json")
    if not os.path.isfile(latest_path):
        raise HTTPException(status_code=404, detail="Nenhum master criado ainda.")

    with open(latest_path, "r", encoding="utf-8") as f:
        latest = json.load(f)

    master_path = latest["master_path"]
    if not os.path.isdir(master_path):
        raise HTTPException(status_code=404, detail="Pasta do master não encontrada no servidor.")

    zip_path = zip_master(master_path)
    return FileResponse(zip_path, filename=os.path.basename(zip_path), media_type="application/zip")