from fastapi import FastAPI, UploadFile, File
import uuid
import os
from engine.audio_analyzer import analyze_audio

app = FastAPI()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.get("/")
def root():
    return {"status": "PHONK AI backend online"}

@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    ext = file.filename.split(".")[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    path = os.path.join(UPLOAD_DIR, filename)

    with open(path, "wb") as f:
        f.write(await file.read())

    analysis = analyze_audio(path)

    return {
        "file_id": filename,
        "analysis": analysis
    }