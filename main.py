from fastapi import FastAPI, UploadFile, File, HTTPException
import uuid
import os
import soundfile as sf
import numpy as np

app = FastAPI()

UPLOAD_DIR = "uploads"
MAX_DURATION_SECONDS = 7 * 60  # 7 minutos

os.makedirs(UPLOAD_DIR, exist_ok=True)

# =========================
# Utils
# =========================

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
    signal = mono(signal)
    rms = np.sqrt(np.mean(signal ** 2))

    if rms < 0.02:
        return "vocal"
    elif rms < 0.06:
        return "melody"
    else:
        return "beat"


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

    bpm_real = estimate_bpm(signal, sr)
    audio_type = classify_audio(signal)
    duration = get_audio_duration(file_path)

    return {
        "file_id": file_id,
        "duration_seconds": round(duration, 2),
        "sample_rate": sr,
        "bpm_real": bpm_real,
        "audio_type": audio_type
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

    bpm_real = estimate_bpm(signal, sr)
    audio_type = classify_audio(signal)

    decisions = []

    if audio_type == "vocal":
        decisions += [
            "necessita beat compatível",
            "sincronizar grid ao tempo do vocal"
        ]
    elif audio_type == "beat":
        decisions.append("pronto para receber vocal")
    else:
        decisions.append("elemento melódico ou base")

    if bpm_real:
        decisions.append(f"BPM real detectado: {bpm_real}")
    else:
        decisions.append("BPM não detectável sem referência externa")

    return {
        "file_id": file_id,
        "audio_type": audio_type,
        "bpm_real": bpm_real,
        "decisions": decisions
    }


# =========================
# FL Studio Time Base Sync
# =========================

@app.post("/fl/sync")
async def fl_sync(file_id: str):
    matches = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(file_id)]
    if not matches:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    file_path = os.path.join(UPLOAD_DIR, matches[0])
    signal, sr = sf.read(file_path)

    bpm_real = estimate_bpm(signal, sr)
    audio_type = classify_audio(signal)

    if bpm_real is None:
        raise HTTPException(
            status_code=422,
            detail="BPM real não detectável. Referência externa necessária."
        )

    seconds_per_bar = (60 / bpm_real) * 4

    return {
        "fl_project": {
            "bpm_project": bpm_real,
            "time_signature": "4/4",
            "seconds_per_bar": round(seconds_per_bar, 4),
            "start_offset_seconds": 0.0
        },
        "audio_alignment": {
            "recommended_stretch_mode": "resample" if audio_type == "beat" else "stretch",
            "align_to": "bar_1"
        },
        "markers": [
            {"bar": 1, "time_seconds": 0.0},
            {"bar": 2, "time_seconds": round(seconds_per_bar, 4)},
            {"bar": 3, "time_seconds": round(seconds_per_bar * 2, 4)}
        ],
        "status": "fl_timebase_ready"
    }


# =========================
# Health
# =========================

@app.get("/")
def root():
    return {"status": "online"}