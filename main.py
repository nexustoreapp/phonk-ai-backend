from fastapi import FastAPI, UploadFile, File, HTTPException
import uuid
import os
import soundfile as sf
import numpy as np
import math

app = FastAPI()

UPLOAD_DIR = "uploads"
MAX_DURATION_SECONDS = 7 * 60  # 7 minutos
PPQ = 960  # FL Studio padrão

os.makedirs(UPLOAD_DIR, exist_ok=True)

# ======================================================
# Utils – Audio
# ======================================================

def get_audio_duration(path: str) -> float:
    info = sf.info(path)
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
    avg = np.mean(intervals)

    if avg <= 0:
        return None

    bpm = 60 / avg
    if bpm < 40 or bpm > 240:
        return None

    return round(bpm, 2)

# ======================================================
# Utils – BPM Logic (3 BPMs)
# ======================================================

def resolve_bpms(bpm_detected: float | None, audio_type: str):
    if bpm_detected is None:
        return {
            "bpm_detected": None,
            "bpm_reference": None,
            "bpm_performance": None
        }

    bpm_reference = round(bpm_detected)
    bpm_performance = bpm_reference

    if audio_type == "vocal":
        bpm_performance = bpm_reference
    elif audio_type == "beat":
        bpm_performance = bpm_reference
    else:
        bpm_performance = bpm_reference

    return {
        "bpm_detected": bpm_detected,
        "bpm_reference": bpm_reference,
        "bpm_performance": bpm_performance
    }

# ======================================================
# Utils – FL Time Base
# ======================================================

def bpm_to_timebase(bpm: float, sr: int, beats_per_bar: int = 4):
    seconds_per_beat = 60 / bpm
    seconds_per_bar = seconds_per_beat * beats_per_bar

    return {
        "bpm": bpm,
        "beats_per_bar": beats_per_bar,
        "seconds_per_beat": round(seconds_per_beat, 6),
        "seconds_per_bar": round(seconds_per_bar, 6),
        "samples_per_beat": int(seconds_per_beat * sr),
        "samples_per_bar": int(seconds_per_bar * sr),
        "sample_rate": sr,
        "ppq": PPQ
    }


def seconds_to_fl_position(seconds: float, bpm: float, beats_per_bar: int = 4):
    seconds_per_beat = 60 / bpm
    total_beats = seconds / seconds_per_beat

    bar = int(total_beats // beats_per_bar) + 1
    beat = int(total_beats % beats_per_bar) + 1
    tick = int((total_beats - math.floor(total_beats)) * PPQ)

    return {
        "bar": bar,
        "beat": beat,
        "tick": tick,
        "absolute_seconds": round(seconds, 6)
    }

# ======================================================
# Upload
# ======================================================

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1].lower()
    path = os.path.join(UPLOAD_DIR, f"{file_id}{ext}")

    with open(path, "wb") as f:
        f.write(await file.read())

    duration = get_audio_duration(path)
    if duration > MAX_DURATION_SECONDS:
        os.remove(path)
        raise HTTPException(400, "Áudio excede 7 minutos")

    return {
        "file_id": file_id,
        "duration_seconds": round(duration, 2)
    }

# ======================================================
# Analyze
# ======================================================

@app.post("/analyze")
async def analyze(file_id: str):
    matches = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(file_id)]
    if not matches:
        raise HTTPException(404, "Arquivo não encontrado")

    path = os.path.join(UPLOAD_DIR, matches[0])
    signal, sr = sf.read(path)

    audio_type = classify_audio(signal)
    bpm_detected = estimate_bpm(signal, sr)
    bpm_data = resolve_bpms(bpm_detected, audio_type)

    return {
        "file_id": file_id,
        "audio_type": audio_type,
        "sample_rate": sr,
        **bpm_data
    }

# ======================================================
# FL Sync – FINAL
# ======================================================

@app.post("/fl-sync")
async def fl_sync(file_id: str):
    matches = [f for f in os.listdir(UPLOAD_DIR) if f.startswith(file_id)]
    if not matches:
        raise HTTPException(404, "Arquivo não encontrado")

    path = os.path.join(UPLOAD_DIR, matches[0])
    signal, sr = sf.read(path)
    duration = get_audio_duration(path)

    audio_type = classify_audio(signal)
    bpm_detected = estimate_bpm(signal, sr)
    bpm_data = resolve_bpms(bpm_detected, audio_type)

    if bpm_data["bpm_performance"] is None:
        raise HTTPException(400, "BPM insuficiente para FL Sync")

    timebase = bpm_to_timebase(bpm_data["bpm_performance"], sr)
    end_position = seconds_to_fl_position(duration, bpm_data["bpm_performance"])

    return {
        "engine": "PHONK_AI_FLSYNC",
        "file_id": file_id,
        "audio_type": audio_type,
        "duration_seconds": round(duration, 6),
        "bpm": bpm_data,
        "timebase": timebase,
        "end_position": end_position,
        "status": "ready_for_fl"
    }

@app.get("/")
def root():
    return {"status": "online"}