from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import psycopg2.extras
import os
from datetime import datetime, timedelta

app = FastAPI(title="VibraTech API - Diagnóstico 500")

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
        raise HTTPException(status_code=500, detail="DATABASE_URL não configurada.")
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        cur = conn.cursor()
        cur.execute("SELECT plan_id, route_name, area, frequency, last_execution, next_execution, responsable, status FROM tb_schedule_rotas ORDER BY plan_id;")
        rotas = cur.fetchall()
        cur.close()
        conn.close()
        return rotas
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar rotas: {str(e)}")

@app.post("/api/upload-html")
async def upload_html(file: UploadFile = File(...), plan_id: str = Form(None)):
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL não configurada no ambiente.")
    
    try:
        # Tenta a conexão e as operações dentro do bloco protegido
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        cur = conn.cursor()
        
        filename = file.filename
        agora = datetime.now()
        proxima_execucao = agora + timedelta(days=28)

        # Insere a linha de teste na tabela de medições
        cur.execute("""
            INSERT INTO tb_medicoes_vibracao 
            (equipamento_tag, unidade_fabril, area_set, ponto_medicao, data_hora, valor_medido, valor_limite, variacao_perc)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """, ("MOTOR-01", "PM1", "AREA-TESTE", "DE-H", agora, 2.5, 4.5, 12.5))

        # Atualiza a rota correspondente
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
        cur.close()
        conn.close()
        
        return {
            "status": "success",
            "filename": filename,
            "message": "Upload processado e gravado no Neon com sucesso!"
        }

    except Exception as e:
        # Se houver qualquer erro, devolve o detalhe exato para a interface
        raise HTTPException(status_code=500, detail=f"Erro detalhado no servidor: {str(e)}")
