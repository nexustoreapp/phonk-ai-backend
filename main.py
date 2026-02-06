import os
import uuid
import wave
import shutil
import sqlite3
import subprocess
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime

# =====================
# CONFIG
# =====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
DB_PATH = os.path.join(BASE_DIR, "audio.db")

os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="Phonk AI Backend")

# =====================
# DATABASE
# =====================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audios (
            id TEXT PRIMARY KEY,
            original_name TEXT,
            wav_path TEXT,
            duration REAL,
            sample_rate INTEGER,
            channels INTEGER,
            file_size_mb REAL,
            format TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# =====================
# UTILS
# =====================
def convert_to_wav(input_path: str, output_path: str):
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-ac", "2",
        "-ar", "44100",
        output_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def analyze_wav(wav_path: str):
    with wave.open(wav_path, "rb") as wf:
        channels = wf.getnchannels()
        sample_rate = wf.getframerate()
        frames = wf.getnframes()
        duration = frames / float(sample_rate)

    size_mb = os.path.getsize(wav_path) / (1024 * 1024)

    return {
        "duration_seconds": round(duration, 2),
        "sample_rate": sample_rate,
        "channels": channels,
        "file_size_mb": round(size_mb, 2),
        "format": "wav"
    }

# =====================
# ROUTES
# =====================
@app.get("/")
def root():
    return {"status": "ok", "service": "phonk-ai-backend"}

@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    file_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1].lower()

    raw_path = os.path.join(UPLOAD_DIR, f"{file_id}{ext}")
    wav_path = os.path.join(UPLOAD_DIR, f"{file_id}.wav")

    with open(raw_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    if ext != ".wav":
        convert_to_wav(raw_path, wav_path)
        os.remove(raw_path)
    else:
        shutil.move(raw_path, wav_path)

    analysis = analyze_wav(wav_path)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO audios VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        file_id,
        file.filename,
        wav_path,
        analysis["duration_seconds"],
        analysis["sample_rate"],
        analysis["channels"],
        analysis["file_size_mb"],
        "wav",
        datetime.utcnow().isoformat()
    ))
    conn.commit()
    conn.close()

    return {
        "file_id": file_id,
        "status": "done",
        "analysis": analysis
    }

@app.get("/analyze-audio/{file_id}")
def analyze_audio(file_id: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM audios WHERE id = ?", (file_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="File not found")

    return {
        "file_id": row[0],
        "status": "done",
        "analysis": {
            "duration_seconds": row[3],
            "sample_rate": row[4],
            "channels": row[5],
            "file_size_mb": row[6],
            "format": row[7]
        }
    }