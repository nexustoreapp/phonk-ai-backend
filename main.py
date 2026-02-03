from fastapi import FastAPI, UploadFile, File, HTTPException
from engine.audio_analyzer import analyze_audio
import uuid
import os

app = FastAPI(
    title="PHONK AI ENGINE",
    version="0.2.0"
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.get("/")
def root():
    return {"status": "PHONK AI ENGINE ONLINE"}


@app.post("/audio/analyze")
async def analyze_uploaded_audio(file: UploadFile = File(...)):
    if not file.filename.lower().endswith((".wav", ".mp3", ".ogg")):
        raise HTTPException(status_code=400, detail="Unsupported audio format")

    file_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")

    try:
        with open(file_path, "wb") as f:
            f.write(await file.read())

        analysis = analyze_audio(file_path)

        return {
            "file_id": file_id,
            "filename": file.filename,
            "analysis": analysis
        }

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)