from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import uuid
import os
import soundfile as sf
import numpy as np
import math

app = FastAPI()

UPLOAD_DIR = "uploads"
MAX_DURATION_SECONDS = 7 * 60  # 7 minutos
DEFAULT_BPM_FALLBACK = 130.0  # usado só para time-base quando BPM não é detectável

os.makedirs(UPLOAD_DIR, exist_ok=True)

# =========================
# Utils
# =========================

def get_audio_duration(file_path: str) -> float:
    info = sf.info(file_path)
    return info.frames / info.samplerate


def estimate_bpm(signal: np.ndarray, sr: int) -> float | None:
    if signal.ndim > 1:
        signal = signal.mean(axis=1)

    energy = np.abs(signal)
    if np.max(energy) == 0:
        return None

    energy = energy / np.max(energy)
    peaks = np.where(energy > 0.9)[0]

    if len(peaks) < 2:
        return None

    intervals = np.diff(peaks) / sr
    avg_interval = np.mean(intervals)

    if avg_interval <= 0:
        return None

    bpm = 60.0 / avg_interval
    if bpm < 40 or bpm > 240:
        return None

    return round(bpm, 2)


def classify_audio(signal: np.ndarray) -> str:
    if signal.ndim > 1:
        signal = signal.mean(axis=1)

    rms = np.sqrt(np.mean(signal ** 2))

    if rms < 0.02:
        return "vocal"
    elif rms < 0.06:
        return "melody"
    else:
        return "beat"


def build_time_base(duration_sec: float, bpm: float) -> dict:
    seconds_per_beat = 60.0 / bpm
    beats_total = duration_sec / seconds_per_beat
    bars_4_4 = beats_total / 4

    return {
        "bpm": bpm,
        "seconds_per_beat": round(seconds_per_beat, 6),
        "total_beats": round(beats_total, 3),
        "total_bars_4_4": round(bars_4_4, 3),
        "time_signature": "4/4",
        "grid_recommendation": "1 beat",
        "fl_studio_ready": True
    }

# =========================
# Upload
# =========================

@app.post("/upload")
async def upload_audio(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1].lower()
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}{ext}")

    with open(file_path, "wb") as f:
        f.write(await file.read())

    duration = get_audio_duration(file_path)

    if duration > MAX_DURATION_SECONDS:
        os.remove(file_path)
        raise HTTPException(status_code=400, detail="Áudio excede 7 minutos")

    return {
        "file_id": file_id,
        "duration_seconds": round(duration, 2),
        "status": "uploaded"
    }

# =========================
# Analyze
# =========================

@app.post("/analyze")
async def analyze_audio(file_id: str):
    matches = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(file_id)]
    if not matches:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    file_path = os.path.join(UPLOAD_DIR, matches[0])

    signal, sr = sf.read(file_path)
    duration = get_audio_duration(file_path)

    bpm_real = estimate_bpm(signal, sr)
    audio_type = classify_audio(signal)

    bpm_for_timebase = bpm_real if bpm_real else DEFAULT_BPM_FALLBACK
    time_base = build_time_base(duration, bpm_for_timebase)

    return {
        "file_id": file_id,
        "duration_seconds": round(duration, 2),
        "sample_rate": sr,
        "audio_type": audio_type,
        "bpm_real": bpm_real,
        "time_base": time_base
    }

# =========================
# Orchestrate (FL Ready)
# =========================

@app.post("/orchestrate")
async def orchestrate(file_id: str):
    matches = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(file_id)]
    if not matches:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    file_path = os.path.join(UPLOAD_DIR, matches[0])
    signal, sr = sf.read(file_path)
    duration = get_audio_duration(file_path)

    bpm_real = estimate_bpm(signal, sr)
    audio_type = classify_audio(signal)

    bpm_for_timebase = bpm_real if bpm_real else DEFAULT_BPM_FALLBACK
    time_base = build_time_base(duration, bpm_for_timebase)

    decisions = []

    if audio_type == "vocal":
        decisions.append("usar vocal como referência de grid")
        decisions.append("sincronizar beat ao vocal")
    elif audio_type == "beat":
        decisions.append("beat pronto para receber vocal")
    else:
        decisions.append("elemento melódico — alinhar ao grid")

    decisions.append("time base compatível com FL Studio")

    return {
        "file_id": file_id,
        "audio_type": audio_type,
        "bpm_real": bpm_real,
        "time_base": time_base,
        "decisions": decisions,
        "status": "fl_time_base_ready"
    }

# =========================
# Health
# =========================

@app.get("/")
def root():
    return {"status": "online", "engine": "phonk-ai-backend"}