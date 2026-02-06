from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import uuid
import wave
import subprocess
import numpy as np

app = FastAPI()

# CORS (liberado pra frontend depois)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def convert_to_wav(input_path: str, output_path: str):
    """
    Converte MP3/OGG -> WAV usando ffmpeg.
    ffmpeg já vem disponível no ambiente do Render.
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-ac", "1",
        "-ar", "44100",
        output_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def analyze_wav(wav_path: str):
    """
    Análise simples e estável:
    - duração
    - RMS (energia)
    - BPM aproximado (picos)
    """
    with wave.open(wav_path, "rb") as wf:
        channels = wf.getnchannels()
        sample_rate = wf.getframerate()
        frames = wf.getnframes()
        duration = frames / float(sample_rate)
        audio = wf.readframes(frames)

    # WAV 16-bit
    samples = np.frombuffer(audio, dtype=np.int16)
    if channels > 1:
        samples = samples[::channels]

    samples = samples.astype(np.float32)

    # Energia (RMS)
    rms = float(np.sqrt(np.mean(samples ** 2)))

    # BPM simples por picos
    abs_signal = np.abs(samples)
    threshold = np.percentile(abs_signal, 95)
    peaks = np.where(abs_signal > threshold)[0]

    if len(peaks) > 1:
        peak_intervals = np.diff(peaks) / sample_rate
        avg_interval = np.mean(peak_intervals)
        bpm = float(60.0 / avg_interval) if avg_interval > 0 else 0.0
    else:
        bpm = 0.0

    return {
        "duration_sec": round(duration, 2),
        "energy_rms": round(rms, 2),
        "bpm_estimated": round(bpm, 2),
        "sample_rate": sample_rate
    }


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/upload")
async def upload_and_analyze(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Arquivo inválido")

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".wav", ".mp3", ".ogg"]:
        raise HTTPException(
            status_code=400,
            detail="Formato não suportado. Use WAV, MP3 ou OGG."
        )

    file_id = str(uuid.uuid4())
    raw_path = os.path.join(UPLOAD_DIR, f"{file_id}{ext}")
    wav_path = os.path.join(UPLOAD_DIR, f"{file_id}.wav")

    # salva upload
    with open(raw_path, "wb") as f:
        f.write(await file.read())

    # converte se precisar
    if ext != ".wav":
        convert_to_wav(raw_path, wav_path)
    else:
        wav_path = raw_path

    if not os.path.exists(wav_path):
        raise HTTPException(status_code=500, detail="Erro ao converter áudio")

    analysis = analyze_wav(wav_path)

    return {
        "file_id": file_id,
        "filename": file.filename,
        "analysis": analysis
    }