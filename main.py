from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uuid
import os
import tempfile
import numpy as np
import soundfile as sf
import math

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# CONFIGURAÇÕES GLOBAIS
# =========================
MAX_DURATION_SECONDS = 7 * 60  # 7 minutos
SUPPORTED_FORMATS = {".wav", ".mp3", ".ogg", ".flac"}

FILES_DB = {}  # memória simples (depois vira banco)

# =========================
# UTILIDADES
# =========================

def load_audio(path: str):
    data, sr = sf.read(path)
    if data.ndim > 1:
        data = np.mean(data, axis=1)  # mono
    duration = len(data) / sr
    return data.astype(np.float32), sr, duration


def detect_onsets(signal, sr):
    frame_size = int(0.02 * sr)
    energy = np.array([
        np.sum(signal[i:i+frame_size]**2)
        for i in range(0, len(signal) - frame_size, frame_size)
    ])
    diff = np.diff(energy)
    onsets = np.where(diff > np.percentile(diff, 85))[0]
    return onsets, frame_size


def estimate_bpm_from_onsets(onsets, frame_size, sr):
    if len(onsets) < 4:
        return None, 0.0

    intervals = np.diff(onsets) * (frame_size / sr)
    intervals = intervals[(intervals > 0.25) & (intervals < 2.5)]

    if len(intervals) < 3:
        return None, 0.0

    median_interval = np.median(intervals)
    bpm = 60.0 / median_interval

    confidence = min(1.0, len(intervals) / 20.0)
    return round(bpm, 2), round(confidence, 2)


def normalize_bpm(bpm):
    if bpm is None:
        return None
    while bpm < 60:
        bpm *= 2
    while bpm > 200:
        bpm /= 2
    return round(bpm, 2)


# =========================
# ENDPOINTS
# =========================

@app.get("/")
def root():
    return {"status": "ok", "service": "phonk-ai-backend"}


@app.post("/upload")
async def upload_audio(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename)[1].lower()

    if ext not in SUPPORTED_FORMATS:
        raise HTTPException(status_code=400, detail="Formato não suportado")

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        signal, sr, duration = load_audio(tmp_path)
    except Exception:
        os.unlink(tmp_path)
        raise HTTPException(status_code=400, detail="Erro ao ler o áudio")

    if duration > MAX_DURATION_SECONDS:
        os.unlink(tmp_path)
        raise HTTPException(status_code=400, detail="Áudio excede 7 minutos")

    file_id = str(uuid.uuid4())

    FILES_DB[file_id] = {
        "path": tmp_path,
        "sr": sr,
        "duration": round(duration, 2),
        "analyzed": False,
        "analysis": None
    }

    return {
        "file_id": file_id,
        "duration": round(duration, 2),
        "sample_rate": sr
    }


@app.post("/analyze")
def analyze_audio(file_id: str):
    if file_id not in FILES_DB:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    record = FILES_DB[file_id]

    if record["analyzed"]:
        return record["analysis"]

    signal, sr, _ = load_audio(record["path"])
    onsets, frame_size = detect_onsets(signal, sr)

    raw_bpm, confidence = estimate_bpm_from_onsets(onsets, frame_size, sr)

    bpm_structural = normalize_bpm(raw_bpm)
    bpm_performance = normalize_bpm(raw_bpm * 0.98) if raw_bpm else None
    bpm_grid = normalize_bpm(raw_bpm * 1.02) if raw_bpm else None

    analysis = {
        "bpm": {
            "structural": bpm_structural,
            "performance": bpm_performance,
            "grid": bpm_grid,
            "confidence": confidence
        },
        "onsets_detected": int(len(onsets)),
        "analysis_type": (
            "low_confidence"
            if confidence < 0.4
            else "reliable"
        )
    }

    record["analysis"] = analysis
    record["analyzed"] = True

    return analysis