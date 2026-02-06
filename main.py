from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import uuid
import wave
import struct
import math

app = FastAPI()

# CORS liberado pra testar de qualquer app (HTTP Shortcut incluso)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "PHONK AI API online"
    }


def analyze_wav(path: str):
    with wave.open(path, "rb") as wf:
        channels = wf.getnchannels()
        sample_rate = wf.getframerate()
        frames = wf.getnframes()
        sampwidth = wf.getsampwidth()

        raw = wf.readframes(frames)

        if sampwidth != 2:
            raise ValueError("Somente WAV 16-bit suportado")

        samples = struct.unpack("<" + "h" * (len(raw) // 2), raw)

        # RMS (volume médio)
        rms = math.sqrt(sum(s * s for s in samples) / len(samples))

        # Pico
        peak = max(abs(s) for s in samples)

        duration = frames / float(sample_rate)

    return {
        "channels": channels,
        "sample_rate": sample_rate,
        "duration_sec": round(duration, 2),
        "rms": round(rms, 2),
        "peak": peak
    }


@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".wav"):
        raise HTTPException(status_code=400, detail="Somente WAV é aceito")

    file_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}.wav")

    with open(file_path, "wb") as f:
        f.write(await file.read())

    try:
        analysis = analyze_wav(file_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "file_id": file_id,
        "analysis": analysis
    }