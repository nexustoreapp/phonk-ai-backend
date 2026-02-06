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

os.makedirs(UPLOAD_DIR, exist_ok=True)

# =========================
# Utils
# =========================

def get_audio_duration(file_path: str) -> float:
    info = sf.info(file_path)
    return info.frames / info.samplerate


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


def analyze_bpm(signal: np.ndarray, sr: int):
    """
    Retorna:
    - bpm_reference: BPM mais estável
    - bpm_performance: BPM médio detectado
    - confidence: confiança (0–1)
    """

    if signal.ndim > 1:
        signal = signal.mean(axis=1)

    # envelope de energia
    energy = np.abs(signal)
    max_energy = np.max(energy)

    if max_energy == 0:
        return None, None, 0.0

    energy = energy / max_energy

    peaks = np.where(energy > 0.9)[0]

    if len(peaks) < 4:
        return None, None, 0.15  # pouco pulso

    intervals = np.diff(peaks) / sr
    intervals = intervals[intervals > 0]

    if len(intervals) == 0:
        return None, None, 0.15

    avg_interval = np.mean(intervals)
    bpm_perf = 60.0 / avg_interval

    if bpm_perf < 40 or bpm_perf > 240:
        return None, None, 0.2

    # estabilização
    bpm_ref = round(bpm_perf / 2) * 2

    variance = np.std(intervals)
    confidence = max(0.0, min(1.0, 1.0 - (variance * 5)))

    return round(bpm_ref, 2), round(bpm_perf, 2), round(confidence, 2)


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

    audio_type = classify_audio(signal)
    bpm_ref, bpm_perf, confidence = analyze_bpm(signal, sr)

    return {
        "file_id": file_id,
        "duration_seconds": round(duration, 2),
        "sample_rate": sr,
        "audio_type": audio_type,
        "bpm_reference": bpm_ref,
        "bpm_performance": bpm_perf,
        "bpm_confidence": confidence
    }


# =========================
# Orchestrate (Fase 2)
# =========================

@app.post("/orchestrate")
async def orchestrate(file_id: str):
    matches = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(file_id)]
    if not matches:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    file_path = os.path.join(UPLOAD_DIR, matches[0])
    signal, sr = sf.read(file_path)

    audio_type = classify_audio(signal)
    bpm_ref, bpm_perf, confidence = analyze_bpm(signal, sr)

    decisions = []

    if audio_type == "vocal":
        decisions.append("vocal detectado")
        decisions.append("necessita beat compatível")
        if bpm_ref:
            decisions.append("grid pode ser ajustado ao BPM do vocal")
        else:
            decisions.append("vocal sem pulso definido")
    elif audio_type == "beat":
        decisions.append("beat detectado")
        decisions.append("pronto para receber vocal")
    else:
        decisions.append("elemento melódico")

    if bpm_ref:
        decisions.append(f"BPM de referência: {bpm_ref}")
    else:
        decisions.append("BPM não definido – referência externa necessária")

    return {
        "file_id": file_id,
        "audio_type": audio_type,
        "bpm_reference": bpm_ref,
        "bpm_performance": bpm_perf,
        "bpm_confidence": confidence,
        "decisions": decisions,
        "status": "orquestrado"
    }


@app.get("/")
def root():
    return {"status": "online"}