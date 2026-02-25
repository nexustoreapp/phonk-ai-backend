import os
import io
import json
import time
import shutil
import zipfile
import tempfile

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse

from flp_corpus.extractor_v1 import build_corpus, safe_mkdir

router = APIRouter(prefix="/flp", tags=["FLP Corpus"])

CORPUS_OUT_DIR = "corpus_out"


def zip_folder(folder_path: str) -> str:
    """
    Zip uma pasta inteira e retorna o caminho do zip gerado.
    """
    folder_path = os.path.abspath(folder_path)
    base_dir = os.path.dirname(folder_path)
    folder_name = os.path.basename(folder_path)
    zip_path = os.path.join(base_dir, f"{folder_name}.zip")

    # recria sempre (evita zip velho)
    if os.path.isfile(zip_path):
        os.remove(zip_path)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(folder_path):
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, folder_path)
                z.write(full, arcname=os.path.join(folder_name, rel))

    return zip_path


@router.post("/ingest")
async def ingest_flp_archives(file: UploadFile = File(...)):
    """
    Recebe um ZIP (batch_XX.zip).
    Extrai, builda corpus, e DEVOLVE um zip do corpus pra você baixar (FREE friendly).
    """
    safe_mkdir("flp_uploads")
    safe_mkdir(CORPUS_OUT_DIR)

    # salva upload
    upload_path = os.path.join("flp_uploads", file.filename)
    with open(upload_path, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)

    # extrai para pasta temporária de archives
    ts = int(time.time())
    archives_dir = os.path.join("flp_uploads", f"batch_{ts}")
    safe_mkdir(archives_dir)

    try:
        with zipfile.ZipFile(upload_path, "r") as z:
            z.extractall(archives_dir)
    except Exception:
        # se não for zip válido, move como archive unitário
        shutil.move(upload_path, os.path.join(archives_dir, os.path.basename(upload_path)))

    # build corpus
    corpus_path = build_corpus(archives_dir=archives_dir, output_dir=CORPUS_OUT_DIR)

    # cria zip do corpus para download
    corpus_zip = zip_folder(corpus_path)

    # limpeza: mantém só o zip do corpus (evita encher o servidor)
    shutil.rmtree(archives_dir, ignore_errors=True)
    if os.path.isfile(upload_path):
        try:
            os.remove(upload_path)
        except Exception:
            pass

    # devolve o zip
    return FileResponse(
        corpus_zip,
        filename=os.path.basename(corpus_zip),
        media_type="application/zip"
    )


@router.post("/master/merge")
async def master_merge(files: list[UploadFile] = File(...)):
    """
    Recebe vários corpus zips (baixados do /ingest) e devolve um MASTER zip.
    Não depende de disco persistente.
    """
    if not files or len(files) < 2:
        raise HTTPException(status_code=400, detail="Envie pelo menos 2 corpus zips.")

    tmp_root = tempfile.mkdtemp(prefix="phonk_master_")
    packs_dir = os.path.join(tmp_root, "packs")
    out_dir = os.path.join(tmp_root, "master_out")
    os.makedirs(packs_dir, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)

    # extrai todos os packs
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

    # junta projects deduplicando por (sha256 FLP principal + title)
    projects_out = os.path.join(tmp_root, "master_projects")
    os.makedirs(projects_out, exist_ok=True)

    seen = set()
    kept = 0
    dropped = 0

    # procura todos os projects/*.json dentro do out_dir
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

    # move projects pro master
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

    # devolve zip e limpa o resto
    # (não apaga o master_zip antes do FileResponse enviar)
    return FileResponse(
        master_zip,
        filename=os.path.basename(master_zip),
        media_type="application/zip"
    )