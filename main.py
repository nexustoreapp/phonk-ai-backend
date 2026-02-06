from fastapi import FastAPI, UploadFile, File, HTTPException
import uuid
import os
import soundfile as sf
import numpy as np
import math

app = FastAPI()

UPLOAD_DIR = "uploads"
MAX_DURATION_SECONDS = 7 * 60  # 7 minutos

os.makedirs(UPLOAD_DIR, exist_ok=True)

# ======================================================
# Utils
# ======================================================

def get_audio_duration(file_path: str) -> float:
    info = sf.info(file_path)
    return info.frames / info.samplerate


def estimate_bpm(signal: np.ndarray, sr: int):
    if signal.ndim > 1:
        signal = signal.mean(axis=1)

    energy = np.abs(signal)
    max_energy = np.max(energy)

    if max_energy == 0:
        return None

    energy = energy / max_energy
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

    return round(bpm, 3)


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


# ======================================================
# Time Base (REAL)
# ======================================================

def build_timebase(bpm_real: float, duration_seconds: float, beats_per_bar: int = 4):
    seconds_per_beat = 60.0 / bpm_real
    seconds_per_bar = seconds_per_beat * beats_per_bar
    total_bars = math.ceil(duration_seconds / seconds_per_bar)

    return {
        "bpm": round(bpm_real, 3),
        "beats_per_bar": beats_per_bar,
        "seconds_per_beat": round(seconds_per_beat, 6),
        "seconds_per_bar": round(seconds_per_bar, 6),
        "total_bars": total_bars,
        "total_seconds": round(duration_seconds, 3),
        "grid": "4/4",
        "fl_studio": {
            "tempo": round(bpm_real, 3),
            "time_signature": "4/4",
            "snap": "line",
            "stretch_mode": "resample"
        }
    }


# ======================================================
# Upload
# ======================================================

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
        "duration_seconds": round(duration, 2)
    }


# ======================================================
# Analyze
# ======================================================

@app.post("/analyze")
async def analyze_audio(file_id: str):
    matches = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(file_id)]
    if not matches:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    file_path = os.path.join(UPLOAD_DIR, matches[0])

    signal, sr = sf.read(file_path)
    duration = get_audio_duration(file_path)
    bpm = estimate_bpm(signal, sr)
    audio_type = classify_audio(signal)

    return {
        "file_id": file_id,
        "duration_seconds": round(duration, 2),
        "sample_rate": sr,
        "bpm_real": bpm,
        "audio_type": audio_type
    }


# ======================================================
# Time Base Endpoint (FL Sync)
# ======================================================

@app.post("/timebase")
async def generate_timebase(file_id: str):
    matches = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(file_id)]
    if not matches:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    file_path = os.path.join(UPLOAD_DIR, matches[0])
    signal, sr = sf.read(file_path)

    bpm = estimate_bpm(signal, sr)
    if bpm is None:
        raise HTTPException(
            status_code=422,
            detail="BPM real não detectável. Necessita referência externa."
        )

    duration = get_audio_duration(file_path)
    timebase = build_timebase(bpm, duration)

    return {
        "file_id": file_id,
        "timebase": timebase,
        "status": "timebase_pronta"
    }


# ======================================================
# Root
# ======================================================

@app.get("/")
def root():
    return {"status": "online"}