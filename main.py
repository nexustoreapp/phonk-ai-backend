from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta

# =====================
# CONFIG
# =====================
SECRET_KEY = "PHONK_SUPER_SECRET_KEY"
ALGORITHM = "HS256"

app = FastAPI(title="PHONK AI ENGINE")

pwd_context = CryptContext(schemes=["bcrypt"])

# =====================
# DATABASE (SIMPLES)
# =====================
users_db = {}
projects_db = {}

# =====================
# MODELS
# =====================
class UserAuth(BaseModel):
    email: str
    password: str

class Project(BaseModel):
    name: str
    bpm: Optional[float] = None
    style: Optional[str] = "phonk_br"
    references: List[str] = []
    confidence_mode: bool = False
    approved_steps: List[str] = []
    rejected_steps: List[str] = []

# =====================
# AUTH UTILS
# =====================
def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(password, hashed):
    return pwd_context.verify(password, hashed)

def create_token(email: str):
    payload = {
        "sub": email,
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

# =====================
# AUTH ROUTES
# =====================
@app.post("/auth/register")
def register(user: UserAuth):
    if user.email in users_db:
        raise HTTPException(400, "Usuário já existe")

    users_db[user.email] = {
        "password": hash_password(user.password)
    }
    return {"status": "ok", "message": "Usuário criado"}

@app.post("/auth/login")
def login(user: UserAuth):
    db_user = users_db.get(user.email)
    if not db_user:
        raise HTTPException(401, "Login inválido")

    if not verify_password(user.password, db_user["password"]):
        raise HTTPException(401, "Login inválido")

    token = create_token(user.email)
    return {"token": token}

# =====================
# PROJECT ROUTES
# =====================
@app.post("/project/create")
def create_project(project: Project):
    project_id = len(projects_db) + 1
    projects_db[project_id] = project
    return {
        "project_id": project_id,
        "project": project
    }

@app.get("/project/{project_id}")
def get_project(project_id: int):
    project = projects_db.get(project_id)
    if not project:
        raise HTTPException(404, "Projeto não encontrado")
    return project

# =====================
# DECISION ENGINE
# =====================
@app.post("/project/{project_id}/decide")
def decide(project_id: int):
    project = projects_db.get(project_id)
    if not project:
        raise HTTPException(404, "Projeto não encontrado")

    if project.confidence_mode:
        decision = "IA decidiu automaticamente com base em referências humanas"
    else:
        decision = "Aguardando decisão do usuário"

    return {
        "decision": decision,
        "project": project
    }

# =====================
# ROOT
# =====================
@app.get("/")
def root():
    return {
        "status": "ONLINE",
        "engine": "PHONK AI",
        "philosophy": [
            "controle_total_do_usuario",
            "respeito_criativo",
            "qualidade_sonora",
            "erro_musical_negociavel",
            "erro_etico_proibido"
        ]
}
