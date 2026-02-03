from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta
import uuid
import os

from engine.audio_analyzer import analyze_audio

# =========================
# APP
# =========================

app = FastAPI(
    title="PHONK AI ENGINE",
    version="0.1.0"
)

# =========================
# CONFIG
# =========================

SECRET_KEY = "dev-secret"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# =========================
# MODELS
# =========================

class UserAuth(BaseModel):
    email: str
    password: str

class Project(BaseModel):
    id: str
    name: str
    created_at: datetime

# =========================
# FAKE DB (DEV)
# =========================

users_db = {}
projects_db = {}

# =========================
# AUTH HELPERS
# =========================

def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(password: str, hashed: str):
    return pwd_context.verify(password, hashed)

def create_token(data: dict):
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

# =========================
# ROUTES
# =========================

@app.get("/")
def root():
    return {"status": "PHONK AI ENGINE ONLINE"}

# ---------- AUTH ----------

@app.post("/auth/register")
def register(user: UserAuth):
    if user.email in users_db:
        raise HTTPException(status_code=400, detail="User already exists")

    users_db[user.email] = {
        "email": user.email,
        "password": hash_password(user.password)
    }
    return {"message": "User registered"}

@app.post("/auth/login")
def login(user: UserAuth):
    db_user = users_db.get(user.email)
    if not db_user or not verify_password(user.password, db_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_token({"sub": user.email})
    return {"access_token": token}

# ---------- PROJECT ----------

@app.post("/project/create")
def create_project(name: str):
    project_id = str(uuid.uuid4())
    project = {