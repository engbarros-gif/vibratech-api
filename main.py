from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import psycopg2.extras
import os

app = FastAPI(title="VibraTech API - Rotas Flexíveis")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL não configurada.")
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


@app.get("/")
def home():
    return {"message": "API do VibraTech online!"}

@app.get("/api/health")
def health_check():
    return {"status": "online", "database": "conectado" if DATABASE_URL else "ausente"}

@app.get("/api/rotas")
def get_rotas():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Usa SELECT * para trazer todas as colunas da tabela de rotas sem risco de erro de nome
        cur.execute("SELECT * FROM tb_schedule_rotas;")
        rotas = cur.fetchall()
        return rotas
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@app.post("/api/upload-html")
async def upload_html():
    return {
        "status": "success",
        "message": "Endpoint pronto."
    }
