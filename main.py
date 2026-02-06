import os
import uuid
import wave
import math
import sqlite3
import tempfile
import subprocess

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

import numpy as np

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "audio.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

os.makedirs(UPLOAD_DIR, exist_ok=True)


# ---------------------------
# DATABASE
# ---------------------------
def get_db():
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS audio (
            file_id TEXT PRIMARY KEY,
            filename TEXT,
            wav_path TEXT,
            duration REAL,
            sample_rate INTEGER,
            channels INTEGER,
            file_size_mb REAL,
            bpm REAL,
            rms REAL,
            peak REAL
        )
        """)
        conn.commit()


init_db()


# ---------------------------
# AUDIO UTILS
# ---------------------------
def convert_to_wav(input_path: str, output_path: str):
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-ac", "2",
        "-ar", "44100",
        output_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def analyze_wav_basic(wav_path: str):
    with wave.open(wav_path, "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        channels = wf.getnchannels()
        duration = frames / float(rate)

    size_mb = os.path.getsize(wav_path) / (1024 * 1024)
    return duration, rate, channels, size_mb


def analyze_music(wav_path: str):
    with wave.open(wav_path, "rb") as wf:
        frames = wf.readframes(wf.getnframes())
        channels = wf.getnchannels()

    audio = np.frombuffer(frames, dtype=np.int16)
    if channels == 2:
        audio = audio.reshape(-1, 2).mean(axis=1)

    audio = audio / 32768.0

    rms = float(np.sqrt(np.mean(audio ** 2)))
    peak = float(np.max(np.abs(audio)))

    # BPM estimation (simple energy peak method)
    energy = audio ** 2
    window = 1024
    energy_env = np.convolve(energy, np.ones(window) / window, mode="same")

    peaks = np.where(energy_env > np.mean(energy_env) * 1.5)[0]
    if len(peaks) > 1:
        intervals = np.diff(peaks)
        avg_interval = np.mean(intervals)
        bpm = float(60 * 44100 / avg_interval)
    else:
        bpm = 0.0

    return bpm, rms, peak


# ---------------------------
# ROUTES
# ---------------------------
@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1].lower()

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    wav_path = os.path.join(UPLOAD_DIR, f"{file_id}.wav")
    convert_to_wav(tmp_path, wav_path)
    os.unlink(tmp_path)

    duration, sr, channels, size_mb = analyze_wav_basic(wav_path)

    with get_db() as conn:
        conn.execute("""
        INSERT INTO audio (file_id, filename, wav_path, duration, sample_rate, channels, file_size_mb)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            file_id,
            file.filename,
            wav_path,
            duration,
            sr,
            channels,
            size_mb
        ))
        conn.commit()

    return {
        "file_id": file_id,
        "status": "uploaded",
        "analysis": {
            "duration_seconds": duration,
            "sample_rate": sr,
            "channels": channels,
            "file_size_mb": round(size_mb, 2),
            "format": "wav"
        }
    }


@app.get("/analyze-audio/{file_id}")
def analyze_audio(file_id: str):
    with get_db() as conn:
        row = conn.execute(
            "SELECT wav_path FROM audio WHERE file_id = ?",
            (file_id,)
        ).fetchone()

    if not row:
        raise HTTPException(404, "Audio not found")

    wav_path = row[0]
    bpm, rms, peak = analyze_music(wav_path)

    with get_db() as conn:
        conn.execute("""
        UPDATE audio
        SET bpm = ?, rms = ?, peak = ?
        WHERE file_id = ?
        """, (bpm, rms, peak, file_id))
        conn.commit()

    return {
        "file_id": file_id,
        "status": "done",
        "music_analysis": {
            "bpm": round(bpm, 2),
            "rms": round(rms, 6),
            "peak": round(peak, 6)
        }
    }


@app.get("/")
def root():
    return {"status": "ok"}