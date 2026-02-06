from fastapi import FastAPI, UploadFile, File, HTTPException
import uuid
import os
import soundfile as sf
import numpy as np

app = FastAPI()

UPLOAD_DIR = "uploads"
MAX_DURATION_SECONDS = 7 * 60  # 7 minutos

os.makedirs(UPLOAD_DIR, exist_ok=True)

# =====================================================
# Utils
# =====================================================

def get_audio_duration(file_path: str) -> float:
    info = sf.info(file_path)
    return info.frames / info.samplerate


def mono(signal: np.ndarray) -> np.ndarray:
    if signal.ndim > 1:
        return signal.mean(axis=1)
    return signal


def estimate_bpm(signal: np.ndarray, sr: int) -> float | None:
    signal = mono(signal)
    energy = np.abs(signal)
    energy /= np.max(energy) if np.max(energy) != 0 else 1

    peaks = np.where(energy > 0.9)[0]
    if len(peaks) < 2:
        return None

    intervals = np.diff(peaks) / sr
    avg_interval = np.mean(intervals)

    if avg_interval <= 0:
        return None

    bpm = 60.0 / avg_interval
    if 40 <= bpm <= 240:
        return round(bpm, 2)

    return None


def classify_audio(signal: np.ndarray) -> str:
    signal = mono(signal)
    rms = np.sqrt(np.mean(signal ** 2))

    if rms < 0.02:
        return "vocal"
    elif rms < 0.06:
        return "melody"
    return "beat"


# =====================================================
# Upload
# =====================================================

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


# =====================================================
# Analyze
# =====================================================

@app.post("/analyze")
async def analyze_audio(file_id: str):
    matches = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(file_id)]
    if not matches:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    file_path = os.path.join(UPLOAD_DIR, matches[0])
    signal, sr = sf.read(file_path)

    bpm = estimate_bpm(signal, sr)
    audio_type = classify_audio(signal)
    duration = get_audio_duration(file_path)

    return {
        "file_id": file_id,
        "audio_type": audio_type,
        "duration_seconds": round(duration, 2),
        "sample_rate": sr,
        "bpm_real": bpm
    }


# =====================================================
# Orchestrate (Decisão musical)
# =====================================================

@app.post("/orchestrate")
async def orchestrate(file_id: str):
    matches = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(file_id)]
    if not matches:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    file_path = os.path.join(UPLOAD_DIR, matches[0])
    signal, sr = sf.read(file_path)

    bpm = estimate_bpm(signal, sr)
    audio_type = classify_audio(signal)

    decisions = []

    if audio_type == "vocal":
        decisions += [
            "vocal sem grid fixo",
            "usar BPM como referência de alinhamento",
            "ajustar time stretching no FL"
        ]
    elif audio_type == "beat":
        decisions += [
            "beat com grid fixo",
            "BPM define o projeto"
        ]
    else:
        decisions += [
            "elemento melódico",
            "pode seguir BPM do projeto"
        ]

    return {
        "file_id": file_id,
        "audio_type": audio_type,
        "bpm_real": bpm,
        "decisions": decisions
    }


# =====================================================
# FL Studio Time Base Sync
# =====================================================

@app.post("/fl-sync")
async def fl_time_base_sync(file_id: str):
    matches = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(file_id)]
    if not matches:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    file_path = os.path.join(UPLOAD_DIR, matches[0])
    signal, sr = sf.read(file_path)
    signal = mono(signal)

    bpm = estimate_bpm(signal, sr)
    if not bpm:
        raise HTTPException(
            status_code=400,
            detail="BPM indeterminado – necessário referência externa"
        )

    seconds_per_beat = 60.0 / bpm
    grid_4 = seconds_per_beat
    grid_8 = seconds_per_beat / 2
    grid_16 = seconds_per_beat / 4

    return {
        "file_id": file_id,
        "bpm_anchor": bpm,
        "time_base_seconds_per_beat": round(seconds_per_beat, 6),
        "fl_grid": {
            "1_beat": round(grid_4, 6),
            "1_8": round(grid_8, 6),
            "1_16": round(grid_16, 6)
        },
        "instructions": [
            "Setar BPM do projeto no FL",
            "Ativar Stretch Mode adequado",
            "Alinhar início do áudio no grid",
            "Usar time stretching se for vocal"
        ],
        "status": "fl_sync_ready"
    }


@app.get("/")
def root():
    return {"status": "online"}