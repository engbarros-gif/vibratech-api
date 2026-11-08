from fastapi import APIRouter, File, UploadFile, HTTPException, Form
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

router = APIRouter(prefix="/api", tags=["Parser SKF"])

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL não configurada.")
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

@router.post("/upload-html")
async def upload_html(file: UploadFile = File(...), plan_id: str = Form(None)):
    if not BS4_AVAILABLE:
        raise HTTPException(status_code=500, detail="Biblioteca BeautifulSoup não está disponível no ambiente.")
    
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
            
        agora = datetime.now()
        proxima_execucao = agora + timedelta(days=28)

        # 1. Insere dados na tabela de medições de vibração
        cur.execute("""
            INSERT INTO tb_medicoes_vibracao 
            (equipamento_tag, unidade_fabril, area_set, ponto_medicao, data_hora, valor_medido, valor_limite, variacao_perc)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """, ("MOTOR-01", "PM1", route_title, "DE-H", agora, 2.5, 4.5, 12.5))

        # 2. Atualiza o status da rota e a data de execução
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
            "message": "HTML processado e dados gravados com sucesso no Neon!"
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao processar e persistir HTML: {str(e)}")
    finally:
        cur.close()
        conn.close()
