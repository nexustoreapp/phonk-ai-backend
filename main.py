from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import os
import uuid
import wave
import contextlib
import audioop

app = FastAPI()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
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
async def analyze_audio(file: UploadFile = File(...)):
    file_id = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, file_id)

    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    try:
        with contextlib.closing(wave.open(file_path, 'rb')) as wf:
            channels = wf.getnchannels()
            sample_rate = wf.getframerate()
            frames = wf.getnframes()
            duration = frames / float(sample_rate)

            wf.rewind()
            raw_audio = wf.readframes(frames)

            rms = audioop.rms(raw_audio, wf.getsampwidth())
            peak = audioop.max(raw_audio, wf.getsampwidth())

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"audio analysis failed: {str(e)}")

    return JSONResponse({
        "status": "ok",
        "message": "audio analyzed",
        "analysis_stage": "basic_features",
        "file_id": file_id,
        "analysis": {
            "duration_seconds": round(duration, 3),
            "sample_rate": sample_rate,
            "channels": channels,
            "rms_energy": rms,
            "peak_amplitude": peak
        }
    })


@app.get("/")
def root():
    return {"status": "online"}