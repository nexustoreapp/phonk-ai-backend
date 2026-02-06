from fastapi import FastAPI, UploadFile, File, HTTPException
import numpy as np
import soundfile as sf
import tempfile
import uuid
import os

app = FastAPI()

# memória simples (depois vira DB)
AUDIO_DB = {}

@app.get("/")
def root():
    return {"status": "ok"}

@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Arquivo inválido")

    file_id = str(uuid.uuid4())

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        contents = await file.read()
        tmp.write(contents)
        tmp_path = tmp.name

    AUDIO_DB[file_id] = {
        "path": tmp_path,
        "filename": file.filename
    }

    return {
        "file_id": file_id,
        "message": "Upload concluído"
    }


@app.post("/analyze/{file_id}")
def analyze_audio(file_id: str):
    if file_id not in AUDIO_DB:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    path = AUDIO_DB[file_id]["path"]

    try:
        audio, sr = sf.read(path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao ler áudio: {str(e)}")

    # mono
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)

    duration = len(audio) / sr

    # envelope simples (energia)
    frame_size = int(0.05 * sr)
    energy = np.array([
        np.sum(np.abs(audio[i:i+frame_size]))
        for i in range(0, len(audio), frame_size)
    ])

    # picos = eventos temporais reais
    threshold = np.mean(energy) * 1.5
    peaks = np.where(energy > threshold)[0]

    if len(peaks) < 2:
        bpm = None
        tempo_map = []
        bpm_type = "indefinido"
    else:
        times = peaks * (frame_size / sr)
        intervals = np.diff(times)
        avg_interval = np.mean(intervals)
        bpm = round(60 / avg_interval, 2)
        tempo_map = times.tolist()
        bpm_type = "performance"

    AUDIO_DB[file_id].update({
        "sample_rate": sr,
        "duration": duration,
        "bpm": bpm,
        "bpm_type": bpm_type,
        "tempo_map": tempo_map
    })

    return {
        "file_id": file_id,
        "duration": duration,
        "sample_rate": sr,
        "bpm": bpm,
        "bpm_type": bpm_type,
        "tempo_map": tempo_map
    }


@app.get("/analysis/{file_id}")
def get_analysis(file_id: str):
    if file_id not in AUDIO_DB:
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    return AUDIO_DB[file_id]