from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import psycopg2.extras
import os
from datetime import datetime, timedelta

# Importação segura do BeautifulSoup
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

app = FastAPI(title="VibraTech API - Bloco 1 e 2 Integrados")

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
    return {"message": "API do VibraTech online e integrada!"}

@app.get("/api/health")
def health_check():
    return {
        "status": "online", 
        "database": "conectado" if DATABASE_URL else "ausente",
        "beautifulsoup": "ativo" if BS4_AVAILABLE else "indisponivel"
    }

@app.get("/api/rotas")
def get_rotas():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM tb_schedule_rotas;")
        rotas = cur.fetchall()
        return rotas
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@app.post("/api/upload-html")
async def upload_html(file: UploadFile = File(...), plan_id: str = Form(None)):
    if not BS4_AVAILABLE:
        raise HTTPException(status_code=500, detail="Biblioteca BeautifulSoup não disponível.")
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # 1. Lê o ficheiro HTML enviado
        contents = await file.read()
        html_content = contents.decode("utf-8", errors="ignore")
        
        # 2. Processa com BeautifulSoup (extrai o título/rota do relatório)
        soup = BeautifulSoup(html_content, 'html.parser')
        route_title = "Inspection Route"
        title_tag = soup.find('title')
        if title_tag:
            route_title = title_tag.text.strip()
            
        agora = datetime.now()
        proxima_execucao = agora + timedelta(days=28)

        # 3. Insere um registo de medição na tabela tb_medicoes_vibracao
        cur.execute("""
            INSERT INTO tb_medicoes_vibracao 
            (equipamento_tag, unidade_fabril, area_set, ponto_medicao, data_hora, valor_medido, valor_limite, variacao_perc)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """, (route_title, "PM1", "Area Principal", "DE-H", agora, 2.85, 4.50, 15.2))

        # 4. Atualiza o status da rota para 'Completed' e recalcula os +28 dias
        if plan_id:
            cur.execute("""
                UPDATE tb_schedule_rotas 
                SET last_execution = %s, next_execution = %s, status = 'Completed'
                WHERE plan_id = %s;
            """, (agora, proxima_execucao, plan_id))
        else:
            cur.execute("""
                UPDATE tb_schedule_rotas 
                SET last_execution = %s, next_execution = %s, status = 'Completed'
                WHERE plan_id = (SELECT plan_id FROM tb_schedule_rotas LIMIT 1);
            """, (agora, proxima_execucao))

        conn.commit()
        
        return {
            "status": "success",
            "filename": file.filename,
            "route_detected": route_title,
            "message": "HTML processado com BeautifulSoup e dados gravados no Neon com sucesso!"
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao processar e persistir: {str(e)}")
    finally:
        cur.close()
        conn.close()
