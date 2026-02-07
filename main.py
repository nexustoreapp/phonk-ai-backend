from fastapi import FastAPI, UploadFile, File, HTTPException
import uuid
import os
import soundfile as sf
import numpy as np
import math

app = FastAPI(title="PHONK AI")

UPLOAD_DIR = "uploads"
MAX_DURATION_SECONDS = 7 * 60  # 7 minutos
os.makedirs(UPLOAD_DIR, exist_ok=True)

# =========================
# Utils
# =========================

def get_audio_duration(file_path: str) -> float:
    info = sf.info(file_path)
    return info.frames / info.samplerate


def estimate_bpm(signal: np.ndarray, sr: int):
    if signal.ndim > 1:
        signal = signal.mean(axis=1)

    energy = np.abs(signal)
    if np.max(energy) == 0:
        return None

    energy /= np.max(energy)
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


def fl_time_base_sync(duration_sec: float, bpm: float):
    if not bpm:
        return None

    seconds_per_beat = 60.0 / bpm
    total_beats = duration_sec / seconds_per_beat
    bars_4_4 = total_beats / 4

    return {
        "bpm": bpm,
        "seconds_per_beat": round(seconds_per_beat, 4),
        "total_beats": round(total_beats, 2),
        "bars_4_4": round(bars_4_4, 2),
        "time_signature": "4/4",
        "fl_grid": {
            "beats_per_bar": 4,
            "snap": "line",
            "ppq_reference": 96
        }
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
        "duration_seconds": round(duration, 2)
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
    bpm = estimate_bpm(signal, sr)
    audio_type = classify_audio(signal)
    fl_sync = fl_time_base_sync(duration, bpm)

    return {
        "file_id": file_id,
        "duration_seconds": round(duration, 2),
        "sample_rate": sr,
        "bpm_real": bpm,
        "audio_type": audio_type,
        "fl_time_base": fl_sync
    }

# =========================
# Orchestrate
# =========================

@app.post("/orchestrate")
async def orchestrate(file_id: str):
    matches = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(file_id)]
    if not matches:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    file_path = os.path.join(UPLOAD_DIR, matches[0])
    signal, sr = sf.read(file_path)
    duration = get_audio_duration(file_path)

    bpm = estimate_bpm(signal, sr)
    audio_type = classify_audio(signal)
    fl_sync = fl_time_base_sync(duration, bpm)

    decisions = []

    if audio_type == "vocal":
        decisions += [
            "vocal_detectado",
            "alinhar vocal ao grid",
            "time_stretch_permitido"
        ]
    elif audio_type == "beat":
        decisions += [
            "beat_detectado",
            "grid_fixo_no_bpm"
        ]
    else:
        decisions += [
            "elemento_melodico",
            "seguir_bpm_referencia"
        ]

    if bpm:
        decisions.append(f"BPM_confirmado_{bpm}")
    else:
        decisions.append("BPM_indeterminado")

    return {
        "file_id": file_id,
        "audio_type": audio_type,
        "bpm_real": bpm,
        "fl_time_base": fl_sync,
        "decisions": decisions,
        "status": "orquestrado"
    }

# =========================
# FL Studio Time Base Sync
# =========================

@app.post("/fl/timebase")
async def fl_timebase(file_id: str):
    matches = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(file_id)]
    if not matches:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    file_path = os.path.join(UPLOAD_DIR, matches[0])
    signal, sr = sf.read(file_path)

    duration = get_audio_duration(file_path)
    bpm = estimate_bpm(signal, sr)

    if not bpm:
        raise HTTPException(status_code=422, detail="BPM não detectado")

    seconds_per_beat = 60 / bpm
    total_beats = math.floor(duration / seconds_per_beat)
    total_bars = math.floor(total_beats / 4)

    tempo_map = []
    current_time = 0.0

    for bar in range(1, total_bars + 1):
        tempo_map.append({
            "bar": bar,
            "time_seconds": round(current_time, 3),
            "bpm": bpm
        })
        current_time += seconds_per_beat * 4

    return {
        "app": "PHONK AI",
        "file_id": file_id,
        "bpm": bpm,
        "time_signature": "4/4",
        "bars": total_bars,
        "tempo_map": tempo_map,
        "fl_import_mode": "tempo_markers",
        "status": "timebase_ready"
    }

@app.get("/")
def root():
    return {"status": "online"}