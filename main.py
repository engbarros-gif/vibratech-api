from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
import os
from datetime import datetime, timedelta

try:
    import psycopg2
    import psycopg2.extras
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

app = FastAPI(title="VibraTech API - Conexão Neon")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    if not DATABASE_URL or not DB_AVAILABLE:
        return None
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

@app.get("/")
def home():
    return {"message": "API do VibraTech online!"}

@app.get("/health")
@app.get("/api/health")
def health_check():
    return {"status": "online", "db_available": DB_AVAILABLE, "db_url_configured": bool(DATABASE_URL)}

@app.get("/rotas")
@app.get("/api/rotas")
def get_rotas():
    # Rota de segurança caso o banco de dados falhe
    fallback_route = [{
        "plan_id": "1M",
        "route_name": "#1PM BASEMENT 1",
        "area": "PM1",
        "frequency": "Monthly",
        "last_execution": "2026-10-19 00:00:00",
        "next_execution": "2026-12-13 01:00:00",
        "responsable": "de Barros Marcelo",
        "status": "Pendente"
    }]

    conn = get_db_connection()
    if not conn:
        return fallback_route

    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tb_schedule_rotas;")
        rotas = cur.fetchall()
        return rotas if rotas else fallback_route
    except Exception:
        return fallback_route
    finally:
        cur.close()
        conn.close()

@app.get("/medicoes")
@app.get("/api/medicoes")
def get_medicoes():
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tb_medicoes_vibracao ORDER BY data_hora DESC LIMIT 50;")
        return cur.fetchall()
    except Exception:
        return []
    finally:
        cur.close()
        conn.close()

@app.post("/upload-html")
@app.post("/api/upload-html")
async def upload_html(file: UploadFile = File(...), rota_nome: str = Form(None)):
    conn = get_db_connection()
    if not conn:
        return {"status": "error", "message": "Banco de dados não disponível."}

    try:
        cur = conn.cursor()
        agora = datetime.now()
        proxima_execucao = agora + timedelta(days=28)
        route_title = rota_nome if rota_nome else "Inspection Route"

        cur.execute("""
            INSERT INTO tb_medicoes_vibracao 
            (equipamento_tag, unidade_fabril, area_set, ponto_medicao, data_hora, valor_medido, valor_limite, variacao_perc, unidade, status_alarme, nome_rota)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """, (route_title, "PM1", "Área Principal", "DE-H", agora, 2.50, 4.50, 15.0, "mm/s", "Normal", route_title))

        if rota_nome:
            cur.execute("""
                UPDATE tb_schedule_rotas 
                SET status = 'Completed', last_execution = %s, next_execution = %s
                WHERE route_name = %s;
            """, (agora, proxima_execucao, rota_nome))

        conn.commit()
        return {"status": "success", "filename": file.filename, "message": "Dados gravados no Neon!"}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": f"Erro ao gravar: {str(e)}"}
    finally:
        cur.close()
        conn.close()
