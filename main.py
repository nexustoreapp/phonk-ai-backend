from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import JSONResponse
import os
import uuid

from engine.audio_analyzer import analyze_audio

app = FastAPI()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.get("/")
def root():
    return {"status": "ok", "service": "phonk-ai"}


@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    if not file.filename:
        return JSONResponse(
            status_code=400,
            content={"error": "no file sent"}
        )

    file_id = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, file_id)

    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    return {
        "message": "upload ok",
        "file_id": file_id,
        "path": file_path
    }


@app.post("/analyze-audio")
async def analyze_audio_endpoint(file_id: str = Form(...)):
    file_path = os.path.join(UPLOAD_DIR, file_id)

    if not os.path.exists(file_path):
        return JSONResponse(
            status_code=404,
            content={"error": "file not found"}
        )

    result = analyze_audio(file_path)
    return result