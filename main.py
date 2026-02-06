from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import uuid
import subprocess
import wave
import struct
import math

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".ogg"}


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "PHONK AI API online"
    }


def convert_to_wav(input_path: str, output_path: str) -> bool:
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", input_path, output_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        return True
    except Exception:
        return False


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

        rms = math.sqrt(sum(s * s for s in samples) / len(samples))
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
    ext = os.path.splitext(file.filename)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Formato não suportado. Use WAV, MP3 ou OGG"
        )

    file_id = str(uuid.uuid4())
    original_path = os.path.join(UPLOAD_DIR, f"{file_id}{ext}")

    with open(original_path, "wb") as f:
        f.write(await file.read())

    response = {
        "file_id": file_id,
        "original_name": file.filename,
        "original_format": ext.replace(".", ""),
        "stored": True
    }

    wav_path = os.path.join(UPLOAD_DIR, f"{file_id}.wav")

    if ext != ".wav":
        converted = convert_to_wav(original_path, wav_path)
        if not converted:
            response["analysis_status"] = "skipped"
            response["note"] = "Conversão para WAV não disponível no servidor"
            return response
    else:
        wav_path = original_path

    try:
        response["analysis"] = analyze_wav(wav_path)
        response["analysis_status"] = "full"
        response["analysis_format"] = "wav"
    except Exception as e:
        response["analysis_status"] = "failed"
        response["error"] = str(e)

    return response