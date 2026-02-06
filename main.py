from fastapi import FastAPI, UploadFile, File, HTTPException
import uuid
import os
import soundfile as sf
import numpy as np

app = FastAPI()

UPLOAD_DIR = "uploads"
MAX_DURATION_SECONDS = 7 * 60  # 7 minutos (regra fixa)

os.makedirs(UPLOAD_DIR, exist_ok=True)

# ======================================================
# Utils
# ======================================================

def get_audio_duration(path: str) -> float:
    info = sf.info(path)
    return info.frames / info.samplerate


def load_audio_mono(path: str):
    signal, sr = sf.read(path)
    if signal.ndim > 1:
        signal = signal.mean(axis=1)
    return signal, sr


def classify_audio(signal: np.ndarray) -> str:
    rms = np.sqrt(np.mean(signal ** 2))

    if rms < 0.02:
        return "vocal"
    elif rms < 0.06:
        return "melody"
    else:
        return "beat"


def estimate_bpm(signal: np.ndarray, sr: int):
    """
    BPM realista simples.
    Se não houver informação rítmica suficiente, retorna None.
    """
    energy = np.abs(signal)
    if energy.max() == 0:
        return None

    energy = energy / energy.max()
    peaks = np.where(energy > 0.9)[0]

    if len(peaks) < 2:
        return None

    intervals = np.diff(peaks) / sr
    mean_interval = np.mean(intervals)

    if mean_interval <= 0:
        return None

    bpm = 60 / mean_interval

    if bpm < 40 or bpm > 240:
        return None

    return round(bpm, 2)


# ======================================================
# Upload
# ======================================================

@app.post("/upload")
async def upload_audio(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1].lower()
    path = os.path.join(UPLOAD_DIR, f"{file_id}{ext}")

    with open(path, "wb") as f:
        f.write(await file.read())

    duration = get_audio_duration(path)

    if duration > MAX_DURATION_SECONDS:
        os.remove(path)
        raise HTTPException(
            status_code=400,
            detail="Áudio excede o limite máximo de 7 minutos"
        )

    return {
        "file_id": file_id,
        "duration_seconds": round(duration, 2),
        "status": "uploaded"
    }


# ======================================================
# Analyze
# ======================================================

@app.post("/analyze")
async def analyze_audio(file_id: str):
    matches = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(file_id)]
    if not matches:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    path = os.path.join(UPLOAD_DIR, matches[0])

    signal, sr = load_audio_mono(path)
    duration = get_audio_duration(path)

    audio_type = classify_audio(signal)
    bpm_detected = estimate_bpm(signal, sr)

    bpm_reference = None
    bpm_performance = None

    if audio_type in ["beat", "melody"]:
        bpm_reference = bpm_detected
    elif audio_type == "vocal":
        bpm_performance = bpm_detected

    return {
        "file_id": file_id,
        "duration_seconds": round(duration, 2),
        "sample_rate": sr,
        "audio_type": audio_type,
        "bpm_detected": bpm_detected,
        "bpm_reference": bpm_reference,
        "bpm_performance": bpm_performance
    }


# ======================================================
# Orchestrate (Base para FL / Time Base Real)
# ======================================================

@app.post("/orchestrate")
async def orchestrate_audio(file_id: str):
    matches = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(file_id)]
    if not matches:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    path = os.path.join(UPLOAD_DIR, matches[0])
    signal, sr = load_audio_mono(path)

    audio_type = classify_audio(signal)
    bpm = estimate_bpm(signal, sr)

    decisions = []

    if audio_type == "vocal":
        decisions.append("usar BPM de performance para alinhamento no grid")
        decisions.append("sincronizar vocal ao BPM do beat no FL")
    elif audio_type == "beat":
        decisions.append("BPM base para todo o projeto")
        decisions.append("aceita vocal sincronizado")
    else:
        decisions.append("elemento melódico ou base auxiliar")

    if bpm:
        decisions.append(f"BPM utilizável: {bpm}")
    else:
        decisions.append("BPM não confiável — requer referência externa")

    return {
        "file_id": file_id,
        "audio_type": audio_type,
        "bpm_real": bpm,
        "decisions": decisions,
        "status": "orquestrado"
    }


@app.get("/")
def root():
    return {"status": "online"}