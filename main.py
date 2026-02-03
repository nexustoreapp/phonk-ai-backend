from fastapi import FastAPI, UploadFile, File, HTTPException
import os
import uuid

app = FastAPI()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.get("/")
def root():
    return {"status": "ok"}


@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Arquivo inválido")

    file_id = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, file_id)

    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)

    return {
        "message": "upload ok",
        "file_id": file_id,
        "path": file_path
    }