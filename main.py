from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from bs4 import BeautifulSoup
import psycopg2
import psycopg2.extras
import os
from datetime import datetime, timedelta

app = FastAPI(title="VibraTech API - Neon & FastAPI")

# Configuração de CORS para permitir requisições do frontend na Vercel
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, pode restringir para o domínio da Vercel
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Obter a URL de conexão do Neon PostgreSQL das variáveis de ambiente do Render
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL environment variable not configured.")
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn

# Modelos Pydantic
class FalhaRecord(BaseModel):
    id: str
    ponto_medicao: str
    equipamento_tag: str
    area_set: str
    validation_type: str
    tipos_falha: str
    descricao_falha: str
    severidade: str
    recomendacao: str
    espectros_count: int

@app.get("/api/rotas")
def get_rotas():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM tb_schedule_rotas ORDER BY plan_id;")
        rotas = cur.fetchall()
        return rotas
    except Exception as e:
        # Fallback de dados caso a tabela ainda esteja a ser criada
        return []
    finally:
        cur.close()
        conn.close()

@app.get("/api/medicoes")
def get_medicoes():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM tb_medicoes_vibracao ORDER BY data_hora DESC LIMIT 100;")
        medicoes = cur.fetchall()
        return medicoes
    except Exception as e:
        return []
    finally:
        cur.close()
        conn.close()

@app.post("/api/upload-html")
async def upload_html(file: UploadFile = File(...), rota_nome: str = Form(...)):
    content = await file.read()
    soup = BeautifulSoup(content, 'html.parser')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        inserted_points = 0
        
        # Exemplo de leitura de tabelas HTML do SKF
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows[1:]: # Pula o cabeçalho
                cols = row.find_all('td')
                if len(cols) >= 3:
                    # Extração genérica de dados da linha do relatório SKF
                    equipamento = cols[0].get_text(strip=True) or "EQUIPMENT"
                    ponto = cols[1].get_text(strip=True) or "POINT-01"
                    valor_str = cols[2].get_text(strip=True).replace(',', '.')
                    
                    try:
                        valor = float(''.join(c for c in valor_str if c.isdigit() or c == '.'))
                    except ValueError:
                        valor = 0.0

                    # Inserir cada ponto encontrado na tabela de medições do Neon
                    cur.execute(
                        """
                        INSERT INTO tb_medicoes_vibracao 
                        (equipamento_tag, area_set, ponto_medicao, data_hora, valor_vibracao, valor_limite, variacao_perc, status_alarme, validation_status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
                        """,
                        (equipamento, "PM1", ponto, datetime.now(), valor, 0.05, 120.0, "Overall - Alert", "Unacknowledged")
                    )
                    inserted_points += 1

        # Atualizar o cronograma da rota (última execução e +28 dias para a próxima)
        agora = datetime.now()
        proxima = agora + timedelta(days=28)
        
        cur.execute(
            """
            UPDATE tb_schedule_rotas 
            SET status = 'Completed', 
                last_execution = %s, 
                next_execution = %s 
            WHERE route_name = %s OR plan_id = %s;
            """,
            (agora, proxima, rota_nome, rota_nome)
        )
        
        conn.commit()
        return {
            "message": f"Relatório HTML para '{rota_nome}' processado! {inserted_points} pontos importados para o Neon."
        }
        
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao processar HTML: {str(e)}")
    finally:
        cur.close()
        conn.close()

@app.post("/api/registros-falha")
def save_registro_falha(record: FalhaRecord):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO tb_registros_falha 
            (id, ponto_medicao, equipamento_tag, area_set, validation_type, tipos_falha, descricao_falha, severidade, recomendacao, espectros_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                validation_type = EXCLUDED.validation_type,
                tipos_falha = EXCLUDED.tipos_falha,
                descricao_falha = EXCLUDED.descricao_falha,
                severidade = EXCLUDED.severidade,
                recomendacao = EXCLUDED.recomendacao;
            """,
            (
                record.id, record.ponto_medicao, record.equipamento_tag, record.area_set,
                record.validation_type, record.tipos_falha, record.descricao_falha,
                record.severidade, record.recomendacao, record.espectros_count
            )
        )
        conn.commit()
        return {"status": "success", "message": "Registro de falha salvo com sucesso no Neon!"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
