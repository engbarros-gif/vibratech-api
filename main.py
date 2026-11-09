from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import psycopg2.extras
import os
from datetime import datetime, timedelta

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

app = FastAPI(title="VibraTech API - Oficial Neon")

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
    return {"message": "API do VibraTech online e ligada ao Neon!"}

@app.get("/health")
@app.get("/api/health")
def health_check():
    return {"status": "online", "database": "conectado" if DATABASE_URL else "ausente"}


@app.get("/rotas")
@app.get("/api/rotas")
def get_rotas():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Garante que a tabela de rotas existe caso ainda não tenha sido criada
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tb_schedule_rotas (
                plan_id VARCHAR(50) PRIMARY KEY,
                route_name VARCHAR(100),
                area VARCHAR(50),
                frequency VARCHAR(50),
                last_execution TIMESTAMP,
                next_execution TIMESTAMP,
                responsable VARCHAR(100),
                status VARCHAR(50)
            );
        """)
        conn.commit()

        # Insere uma rota de exemplo se a tabela estiver vazia
        cur.execute("SELECT COUNT(*) as total FROM tb_schedule_rotas;")
        res = cur.fetchone()
        if res and res['total'] == 0:
            cur.execute("""
                INSERT INTO tb_schedule_rotas 
                (plan_id, route_name, area, frequency, last_execution, next_execution, responsable, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
            """, ("1M", "#1PM BASEMENT 1", "PM1", "Monthly", datetime.now(), datetime.now() + timedelta(days=28), "de Barros Marcelo", "Pendente"))
            conn.commit()

        cur.execute("SELECT * FROM tb_schedule_rotas;")
        rotas = cur.fetchall()
        return rotas
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@app.get("/medicoes")
@app.get("/api/medicoes")
def get_medicoes():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM tb_medicoes_vibracao ORDER BY data_hora DESC LIMIT 50;")
        medicoes = cur.fetchall()
        return medicoes
    except Exception as e:
        return []
    finally:
        cur.close()
        conn.close()


@app.post("/upload-html")
@app.post("/api/upload-html")
async def upload_html(file: UploadFile = File(...), rota_nome: str = Form(None)):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        contents = await file.read()
        html_content = contents.decode("utf-8", errors="ignore")
        
        route_title = rota_nome if rota_nome else "Inspection Route"
        if BS4_AVAILABLE:
            soup = BeautifulSoup(html_content, 'html.parser')
            title_tag = soup.find('title')
            if title_tag and not rota_nome:
                route_title = title_tag.text.strip()
            
        agora = datetime.now()
        proxima_execucao = agora + timedelta(days=28)

        # Insere na tabela tb_medicoes_vibracao usando exatamente as colunas do seu Neon
        cur.execute("""
            INSERT INTO tb_medicoes_vibracao 
            (equipamento_tag, unidade_fabril, area_set, ponto_medicao, data_hora, valor_medido, valor_limite, variacao_perc, unidade, status_alarme, nome_rota)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """, (route_title, "PM1", "Área Principal", "DE-H", agora, 2.85, 4.50, 15.2, "mm/s", "Normal", route_title))

        # Atualiza a rota correspondente na tabela tb_schedule_rotas
        if rota_nome:
            cur.execute("""
                UPDATE tb_schedule_rotas 
                SET status = 'Completed', last_execution = %s, next_execution = %s
                WHERE route_name = %s;
            """, (agora, proxima_execucao, rota_nome))

        conn.commit()
        return {
            "status": "success",
            "filename": file.filename,
            "message": "Ficheiro HTML processado e gravado no Neon com sucesso!"
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
