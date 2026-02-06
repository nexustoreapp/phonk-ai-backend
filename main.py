from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import os
import uuid
import subprocess
import shutil

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
WAV_DIR = os.path.join(BASE_DIR, "wav")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(WAV_DIR, exist_ok=True)


@app.get("/")
def root():
    return {"status": "ok", "service": "phonk-ai"}


@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file sent")

    file_id = f"{uuid.uuid4()}_{file.filename}"
    input_path = os.path.join(UPLOAD_DIR, file_id)

    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {
        "status": "ok",
        "message": "upload ok",
        "file_id": file_id,
        "path": f"uploads/{file_id}",
    }


@app.post("/analyze-audio")
async def analyze_audio(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file sent")

    uid = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_DIR, f"{uid}_{file.filename}")
    wav_path = os.path.join(WAV_DIR, f"{uid}.wav")

    with open(input_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Converte qualquer formato para WAV usando FFmpeg
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-ac",
        "1",
        "-ar",
        "44100",
        wav_path,
    ]

    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    except subprocess.CalledProcessError:
        raise HTTPException(status_code=500, detail="Audio conversion failed")

    return JSONResponse(
        {
            "status": "ok",
            "message": "audio received and converted",
            "analysis_stage": "stub",
            "wav_path": f"wav/{uid}.wav",
        }
    )