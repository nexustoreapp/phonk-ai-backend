from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import os
import uuid
import shutil

# ===== CONFIG =====
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="Phonk AI API")


# ===== ROOT =====
@app.get("/")
def root():
    return {"status": "ok", "service": "phonk-ai"}


# ===== UPLOAD AUDIO =====
@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    file_id = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, file_id)

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "message": "upload ok",
        "file_id": file_id,
        "path": file_path
    }


# ===== ANALYZE AUDIO =====
@app.post("/analyze-audio")
async def analyze_audio(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    temp_id = f"{uuid.uuid4()}_{file.filename}"
    temp_path = os.path.join(UPLOAD_DIR, temp_id)

    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # STUB DE ANÁLISE (sem librosa por enquanto)
    result = {
        "status": "ok",
        "message": "audio received",
        "analysis_stage": "stub",
        "file": temp_id
    }

    return JSONResponse(content=result)