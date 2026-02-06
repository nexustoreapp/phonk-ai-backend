import os
import uuid
import tempfile
import math
from typing import Optional

import numpy as np
import soundfile as sf

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="PHONK AI – Audio Core")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ===============================
# Utils
# ===============================

def save_upload(file: UploadFile) -> str:
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".wav", ".mp3", ".ogg", ".flac"]:
        raise HTTPException(status_code=400, detail="Unsupported audio format")

    file_id = str(uuid.uuid4())
    path = os.path.join(UPLOAD_DIR, f"{file_id}{ext}")

    with open(path, "wb") as f:
        f.write(file.file.read())

    return path


def load_audio_mono(path: str):
    data, sr = sf.read(path)
    if data.ndim > 1:
        data = np.mean(data, axis=1)
    return data.astype(np.float32), sr


def estimate_bpm_onsets(signal, sr):
    # Envelope
    env = np.abs(signal)
    env = np.convolve(env, np.ones(1024) / 1024, mode="same")

    # Peaks
    threshold = np.percentile(env, 75)
    peaks = np.where(env > threshold)[0]

    if len(peaks) < 10:
        return None, 0.0

    intervals = np.diff(peaks) / sr
    intervals = intervals[(intervals > 0.25) & (intervals < 2.0)]

    if len(intervals) < 5:
        return None, 0.0

    median_interval = np.median(intervals)
    bpm = 60.0 / median_interval

    confidence = min(1.0, len(intervals) / 200)
    return bpm, confidence


def estimate_bpm_vocal(signal, sr):
    energy = signal ** 2
    window = int(sr * 0.02)
    energy_env = np.convolve(energy, np.ones(window) / window, mode="same")

    peaks = np.where(energy_env > np.percentile(energy_env, 80))[0]

    if len(peaks) < 8:
        return None, 0.0

    intervals = np.diff(peaks) / sr
    intervals = intervals[(intervals > 0.3) & (intervals < 3.0)]

    if len(intervals) < 5:
        return None, 0.0

    bpm = 60.0 / np.median(intervals)
    confidence = min(1.0, len(intervals) / 150)
    return bpm, confidence


def converge_bpm(ref_bpm, ref_conf, perf_bpm, perf_conf):
    if ref_bpm and ref_conf >= perf_conf:
        return ref_bpm, ref_conf, "reference_priority"

    if perf_bpm:
        return perf_bpm, perf_conf, "performance_priority"

    return None, 0.0, "indeterminate"


# ===============================
# Routes
# ===============================

@app.get("/")
def root():
    return {"status": "online", "service": "phonk-ai-backend"}


@app.post("/upload")
def upload_audio(file: UploadFile = File(...)):
    path = save_upload(file)
    return {
        "status": "uploaded",
        "file_path": path
    }


@app.post("/analyze")
def analyze_audio(file_path: str):
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    signal, sr = load_audio_mono(file_path)

    ref_bpm, ref_conf = estimate_bpm_onsets(signal, sr)
    perf_bpm, perf_conf = estimate_bpm_vocal(signal, sr)

    conv_bpm, conv_conf, basis = converge_bpm(
        ref_bpm, ref_conf, perf_bpm, perf_conf
    )

    def pack(bpm, conf, method):
        if bpm is None:
            return {
                "value": None,
                "confidence": 0.0,
                "method": method,
                "status": "indeterminate"
            }
        return {
            "value": round(bpm, 2),
            "confidence": round(conf, 3),
            "method": method,
            "status": "valid" if conf >= 0.4 else "unstable"
        }

    return {
        "bpm": {
            "reference": pack(ref_bpm, ref_conf, "onset_interval"),
            "performance": pack(perf_bpm, perf_conf, "vocal_cadence"),
            "convergence": pack(conv_bpm, conv_conf, basis)
        }
    }