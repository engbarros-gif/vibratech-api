from fastapi import APIRouter, File, UploadFile, HTTPException, Form
import psycopg2
import psycopg2.extras
import os
from datetime import datetime, timedelta

router = APIRouter(prefix="/api", tags=["Parser Teste"])

DATABASE_URL = os.getenv("DATABASE_URL")

@router.post("/upload-html")
async def upload_html(file: UploadFile = File(...), plan_id: str = Form(None)):
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL não configurada.")
    
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    cur = conn.cursor()
    
    try:
        # Apenas lê o ficheiro recebido para garantir que o upload funciona
        contents = await file.read()
        filename = file.filename
        
        agora = datetime.now()
        proxima_execucao = agora + timedelta(days=28)

        # 1. Insere uma LINHA DE TESTE fixa na tabela tb_medicoes_vibracao
        cur.execute("""
            INSERT INTO tb_medicoes_vibracao 
            (equipamento_tag, unidade_fabril, area_set, ponto_medicao, data_hora, valor_medido, valor_limite, variacao_perc)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """, ("TESTE-COMUNICACAO", "PM1", "AREA-TESTE", "PONTO-01", agora, 1.23, 5.00, 10.5))

        # 2. Atualiza a rota correspondente para 'Completed'
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
            "message": "Teste de comunicação concluído! Linha gravada no Neon."
        }

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro no teste de inserção: {str(e)}")
    finally:
        cur.close()
        conn.close()
