from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta
import uuid

# =====================
# CONFIG
# =====================
SECRET_KEY = "PHONK_SUPER_SECRET_KEY"
ALGORITHM = "HS256"

app = FastAPI(title="PHONK AI ENGINE")

pwd_context = CryptContext(schemes=["bcrypt"])

# =====================
# DATABASE (MEMÓRIA)
# =====================
users_db = {}
projects_db = {}
audio_db = {}

# =====================
# MODELS
# =====================
class UserAuth(BaseModel):
    email: str
    password: str

class Project(BaseModel):
    name: str
    bpm: Optional[float] = None
    style: str = "phonk_br"
    confidence_mode: bool = True
    references: List[str] = []