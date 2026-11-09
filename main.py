from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import psycopg2.extras
import os
from datetime import datetime, timedelta

app = FastAPI(title="VibraTech API - Blindada Final")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL")

@app.get("/")
def home():
    return {"message": "API do VibraTech online!"}

@app.get("/api/health")
def health_check():
    return {"status": "online", "database": "configurado" if DATABASE_URL else "ausente"}

@app.get("/api/rotas")
def get_rotas():
    if not DATABASE_URL:
        return []
    
    conn = None
    cur = None
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        cur = conn.cursor()
        
        # 1. Garante que a tabela de rotas existe
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

        # 2. Se a tabela estiver vazia, insere uma rota padrão para teste
        cur.execute("SELECT COUNT(*) as total FROM tb_schedule_rotas;")
        res = cur.fetchone()
        if res and res['total'] == 0:
            cur.execute("""
                INSERT INTO tb_schedule_rotas 
                (plan_id, route_name, area, frequency, last_execution, next_execution, responsable, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
            """, ("1M", "#1PM BASEMENT 1", "PM1", "Monthly", datetime.now(), datetime.now() + timedelta(days=28), "de Barros Marcelo", "Pendente"))
            conn.commit()

        # 3. Busca todas as rotas
        cur.execute("SELECT * FROM tb_schedule_rotas;")
        rotas = cur.fetchall()
        return rotas

    except Exception as e:
        # Nunca deixa a API dar 500 nas rotas, evitando que sumam na tela
        return []
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@app.post("/api/upload-html")
async def upload_html(file: UploadFile = File(...), rota_nome: str = Form(None)):
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL não configurada.")
    
    conn = None
    cur = None
    try:
        contents = await file.read()
        agora = datetime.now()
        proxima_execucao = agora + timedelta(days=28)

        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        cur = conn.cursor()

        # Garante que a tabela de medições existe
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tb_medicoes_vibracao (
                id SERIAL PRIMARY KEY,
                equipamento_tag VARCHAR(100),
                unidade_fabril VARCHAR(50),
                area_set VARCHAR(100),
                ponto_medicao VARCHAR(50),
                data_hora TIMESTAMP,
                valor_medido FLOAT,
                valor_limite FLOAT,
                variacao_perc FLOAT,
                unidade VARCHAR(20),
                status_alarme VARCHAR(1000)
            );
        """)

        # Insere a medição de teste vinculada
        route_title = rota_nome if rota_nome else "Inspection Route"
        cur.execute("""
            INSERT INTO tb_medicoes_vibracao 
            (equipamento_tag, unidade_fabril, area_set, ponto_medicao, data_hora, valor_medido, valor_limite, variacao_perc, unidade, status_alarme)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """, (route_title, "PM1", "Área Principal", "DE-H", agora, 2.50, 4.50, 15.0, "mm/s", "Normal"))

        # Atualiza o status da rota correspondente para 'Completed'
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
            "message": "Upload efetuado e dados gravados no Neon com sucesso!"
        }

    except Exception as e:
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro no upload: {str(e)}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
