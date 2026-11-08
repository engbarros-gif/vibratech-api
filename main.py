from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import psycopg2.extras
import os
from datetime import datetime, timedelta

app = FastAPI(title="VibraTech API - Unificada")

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
    return {"message": "API do VibraTech unificada e online!"}

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


# Rota direta de upload para eliminar qualquer 404
@app.post("/api/upload-html")
async def upload_html(file: UploadFile = File(...), plan_id: str = Form(None)):
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL não configurada.")
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        filename = file.filename
        agora = datetime.now()
        proxima_execucao = agora + timedelta(days=28)

        # Insere uma linha de teste na tabela tb_medicoes_vibracao para validar a gravação
        cur.execute("""
            INSERT INTO tb_medicoes_vibracao 
            (equipamento_tag, unidade_fabril, area_set, ponto_medicao, data_hora, valor_medido, valor_limite, variacao_perc)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """, ("MOTOR-01", "PM1", "AREA-TESTE", "DE-H", agora, 2.5, 4.5, 12.5))

        # Atualiza o status da rota correspondente
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
            "filename": filename,
            "message": "Upload efetuado e linha gravada no Neon com sucesso!"
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao persistir dados: {str(e)}")
    finally:
        cur.close()
        conn.close()
