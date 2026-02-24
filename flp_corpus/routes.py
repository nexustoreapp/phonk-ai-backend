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