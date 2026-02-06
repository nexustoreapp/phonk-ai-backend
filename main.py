from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uuid
import os
import subprocess
import wave
import contextlib

app = FastAPI()

# CORS (liberado pra teste / app)
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

# Estado simples em memória (depois vira banco)
FILES = {}

# -----------------------------
# Utils
# -----------------------------

def convert_to_wav(input_path: str, output_path: str):
    """
    Converte MP3 / OGG / WAV para WAV padronizado
    Requer ffmpeg disponível (Render tem)
    """
    command = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-ac", "2",
        "-ar", "44100",
        output_path
    ]
    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def analyze_wav(wav_path: str):
    """
    Análise REAL de áudio WAV (sem IA fake)
    """
    with contextlib.closing(wave.open(wav_path, "r")) as wf:
        channels = wf.getnchannels()
        sample_rate = wf.getframerate()
        frames = wf.getnframes()
        duration = frames / float(sample_rate)

    size_mb = round(os.path.getsize(wav_path) / (1024 * 1024), 2)

    return {
        "duration_seconds": round(duration, 2),
        "sample_rate": sample_rate,
        "channels": channels,
        "file_size_mb": size_mb,
        "format": "wav"
    }

# -----------------------------
# Routes
# -----------------------------

@app.get("/")
def root():
    return {"status": "online", "service": "phonk-ai-backend"}


@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in [".wav", ".mp3", ".ogg"]:
        raise HTTPException(status_code=400, detail="Formato não suportado")

    original_path = os.path.join(UPLOAD_DIR, f"{file_id}{ext}")
    wav_path = os.path.join(UPLOAD_DIR, f"{file_id}.wav")

    # Salva arquivo original
    with open(original_path, "wb") as f:
        f.write(await file.read())

    # Converte pra WAV
    convert_to_wav(original_path, wav_path)

    if not os.path.exists(wav_path):
        raise HTTPException(status_code=500, detail="Falha ao converter áudio")

    # Marca estado
    FILES[file_id] = {
        "status": "processing",
        "original_file": file.filename,
        "wav_path": wav_path
    }

    # Analisa automaticamente
    analysis = analyze_wav(wav_path)

    FILES[file_id]["status"] = "done"
    FILES[file_id]["analysis"] = analysis

    return {
        "file_id": file_id,
        "status": "done",
        "analysis": analysis
    }


@app.get("/analyze/{file_id}")
def get_analysis(file_id: str):
    if file_id not in FILES:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    return {
        "file_id": file_id,
        "status": FILES[file_id]["status"],
        "analysis": FILES[file_id].get("analysis")
    }