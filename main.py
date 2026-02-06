# main.py
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uuid
import os
import subprocess
import wave
import contextlib
import numpy as np

app = FastAPI()

# CORS liberado (frontend depois)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def convert_to_wav(input_path: str, output_path: str):
    """
    Converte qualquer áudio (mp3, ogg, etc) para WAV PCM 16bit
    Requer ffmpeg disponível no ambiente (Render tem).
    """
    command = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-ac", "1",
        "-ar", "44100",
        "-sample_fmt", "s16",
        output_path
    ]
    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


def analyze_wav(wav_path: str):
    """
    Análise simples real (não fake):
    - duração
    - sample rate
    - RMS médio
    """
    with contextlib.closing(wave.open(wav_path, 'rb')) as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        duration = frames / float(rate)

    with wave.open(wav_path, 'rb') as wf:
        raw = wf.readframes(wf.getnframes())
        audio = np.frombuffer(raw, dtype=np.int16)
        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))

    return {
        "duration_seconds": round(duration, 2),
        "sample_rate": rate,
        "rms": round(rms, 2)
    }


@app.get("/")
def root():
    return {"status": "online"}


@app.post("/upload")
async def upload_audio(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Arquivo inválido")

    file_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1].lower()

    original_path = os.path.join(UPLOAD_DIR, f"{file_id}{ext}")
    wav_path = os.path.join(UPLOAD_DIR, f"{file_id}.wav")

    with open(original_path, "wb") as f:
        f.write(await file.read())

    try:
        if ext != ".wav":
            convert_to_wav(original_path, wav_path)
        else:
            os.rename(original_path, wav_path)
    except Exception:
        raise HTTPException(status_code=500, detail="Erro ao converter áudio")

    return {
        "file_id": file_id,
        "wav_ready": True
    }


@app.post("/analyze/{file_id}")
def analyze_audio(file_id: str):
    wav_path = os.path.join(UPLOAD_DIR, f"{file_id}.wav")

    if not os.path.exists(wav_path):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    try:
        analysis = analyze_wav(wav_path)
    except Exception:
        raise HTTPException(status_code=500, detail="Erro ao analisar áudio")

    return {
        "file_id": file_id,
        "analysis": analysis
    }