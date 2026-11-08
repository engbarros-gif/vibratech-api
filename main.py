# ==========================================
# BLOCO 1: MÓDULO SINCRONISMO DO SCHEDULE
# ==========================================
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import psycopg2.extras
import os

app = FastAPI(title="VibraTech API - Bloco 1 Conexao")

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
    return {"message": "API do VibraTech está online! Acesse /api/rotas para ver os dados do Neon."}

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
# BLOCO 2: MÓDULO DE IMPORTAÇÃO E PARSER HTML
# ==========================================
@app.post("/api/upload-html")
async def upload_html(file: UploadFile = File(...)):
    try:
        # Lê o conteúdo do arquivo HTML enviado pelo usuário
        contents = await file.read()
        html_content = contents.decode("utf-8", errors="ignore")
        
        # Processa o HTML usando BeautifulSoup para extrair informações estruturadas
        soup = BeautifulSoup(html_content, 'html.parser')
        
        route_title = "Inspection Route"
        title_tag = soup.find('title')
        if title_tag:
            route_title = title_tag.text.strip()
            
        return {
            "status": "success",
            "filename": file.filename,
            "route_detected": route_title,
            "message": "HTML processado com sucesso pelo BeautifulSoup!"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar HTML: {str(e)}")
