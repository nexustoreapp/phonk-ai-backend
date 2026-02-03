from fastapi import FastAPI, UploadFile, File

app = FastAPI()

@app.get("/")
def root():
    return {"status": "ok"}

@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    return {
        "filename": file.filename,
        "content_type": file.content_type
    }