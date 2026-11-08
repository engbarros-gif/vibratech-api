from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import psycopg2.extras
import os
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re

app = FastAPI(title="VibraTech API - Blocos 1, 2 e 3")

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
    return {"message": "API do VibraTech está online! Sistema modular ativo."}

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
# BLOCO 2 & 3: PARSER HTML E PERSISTÊNCIA NO NEON
# ==========================================
@app.post("/api/upload-html")
async def upload_html(file: UploadFile = File(...), plan_id: str = Form(None)):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Lê o conteúdo do ficheiro HTML enviado
        contents = await file.read()
        html_content = contents.decode("utf-8", errors="ignore")
        
        # Processa o HTML usando BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        route_title = "Inspection Route"
        title_tag = soup.find('title')
        if title_tag:
            route_title = title_tag.text.strip()

        # Exemplo de gravação de registo de teste/extraído nas medições de vibração
        # (Aqui refinaremos a leitura das tags exatas do relatório SKF)
        agora = datetime.now()
        proxima_execucao = agora + timedelta(days=28)

        # Insere um registo de exemplo na tabela tb_medicoes_vibracao para validar a persistência
        cur.execute("""
            INSERT INTO tb_medicoes_vibracao 
            (equipamento_tag, unidade_fabril, area_set, ponto_medicao, data_hora, valor_medido, valor_limite, variacao_perc)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """, ("MOTOR-01", "PM1", route_title, "DE-H", agora, 2.5, 4.5, 12.5))

        # Atualiza a tabela de rotas marcando como Completed e recalcule a próxima execução (+28 dias)
        if plan_id:
            cur.execute("""
                UPDATE tb_schedule_rotas 
                SET last_execution = %s, next_execution = %s, status = 'Completed'
                WHERE plan_id = %s;
            """, (agora, proxima_execucao, plan_id))
        else:
            # Caso o plan_id venha vazio, atualiza a primeira rota pendente para teste
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
            "message": "HTML processado e dados gravados com sucesso no Neon!"
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao persistir dados: {str(e)}")
    finally:
        cur.close()
        conn.close()
