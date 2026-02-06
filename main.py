from fastapi import FastAPI, UploadFile, File, Form, HTTPException
import os
import uuid

app = FastAPI()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.get("/")
def root():
    return {"status": "ok", "service": "phonk-ai"}


@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file sent")

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
async def analyze_audio(file_id: str = Form(...)):
    file_path = os.path.join(UPLOAD_DIR, file_id)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    # Stub por enquanto
    return {
        "status": "ok",
        "message": "audio received",
        "analysis_stage": "stub",
        "file_id": file_id
    }