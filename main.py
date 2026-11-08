from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import psycopg2.extras
import os

app = FastAPI(title="VibraTech API - Arquitetura Modular")

# Configuração de CORS
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


# ==========================================
# BLOCO 1: NÚCLEO, SAÚDE E ROTAS DO NEON
# ==========================================
@app.get("/")
def home():
    return {"message": "API do VibraTech modular está online!"}

@app.get("/api/health")
def health_check():
    return {"status": "online", "database": "conectado" if DATABASE_URL else "ausente"}

@app.get("/api/rotas")
def get_rotas():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT plan_id, route_name, area, frequency, last_execution, next_execution, responsable, status FROM tb_schedule_rotas ORDER BY plan_id;")
        rotas = cur.fetchall()
        return rotas
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


# ==========================================
# INTEGRAÇÃO SEGURA DO BLOCO 2 (PARSER HTML)
# ==========================================
try:
    from parser_skf import router as parser_router
    app.include_router(parser_router)
    print("Módulo Parser SKF integrado com sucesso.")
except Exception as e:
    print(f"Aviso: O módulo Parser SKF não foi carregado: {e}")
