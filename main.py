from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os
import uuid
import shutil

app = FastAPI()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# =========================
# MODELS
# =========================

class AnalyzeRequest(BaseModel):
    file_id: str


# =========================
# HEALTH CHECK
# =========================

@app.get("/")
def root():
    return {"status": "ok", "service": "phonk-ai"}


# =========================
# UPLOAD AUDIO
# =========================

@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".wav", ".mp3", ".ogg"]:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    file_id = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, file_id)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {
        "message": "upload ok",
        "file_id": file_id,
        "path": file_path
    }


# =========================
# ANALYZE AUDIO
# =========================

@app.post("/analyze-audio")
async def analyze_audio(data: AnalyzeRequest):
    file_path = os.path.join(UPLOAD_DIR, data.file_id)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    # 🔹 STUB DE ANÁLISE (por enquanto)
    # Aqui depois entra BPM, key, energia, etc.

    return {
        "status": "ok",
        "message": "audio received",
        "analysis_stage": "stub",
        "file_id": data.file_id
    }