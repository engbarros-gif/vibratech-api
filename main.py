import os
import re
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
from bs4 import BeautifulSoup

app = FastAPI(title="VibraTech API")

# Habilitar CORS para permitir requisições do seu frontend na Vercel
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, pode especificar o domínio da Vercel
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL não configurada.")
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# --- MODELOS DE DADOS ---
class RegistroFalha(BaseModel):
    id: str
    ponto_medicao: str
    equipamento_tag: str
    area_set: str
    validation_type: str
    justificativa_erro: Optional[str] = None
    tipos_falha: str
    descricao_falha: str
    severidade: str
    recomendacao: str
    espectros_count: int = 0

# --- ROTAS DA API ---

@app.get("/")
def read_root():
    return {"status": "VibraTech API online", "timestamp": datetime.now()}

@app.get("/api/rotas")
def listar_rotas():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tb_schedule_rotas ORDER BY rota_id;")
    rotas = cur.fetchall()
    cur.close()
    conn.close()
    return rotas

@app.get("/api/medicoes")
def listar_medicoes(rota: Optional[str] = None, status: Optional[str] = None):
    conn = get_db_connection()
    cur = conn.cursor()
    query = "SELECT * FROM tb_medicoes_vibracao WHERE 1=1"
    params = []
    
    if rota and rota != "ALL":
        query += " AND rota = %s"
        params.append(rota)
    if status and status != "ALL":
        query += " AND status = %s"
        params.append(status)
        
    query += " ORDER BY data_medicao DESC;"
    cur.execute(query, params)
    medicoes = cur.fetchall()
    cur.close()
    conn.close()
    return medicoes

@app.post("/api/upload-html")
async def upload_html(rota_nome: str = Form(...), file: UploadFile = File(...)):
    content = await file.read()
    soup = BeautifulSoup(content, 'html.parser')
    
    # Exemplo simples de parsing de tabela SKF HTML
    rows = soup.find_all('tr')
    parsed_count = 0
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    for row in rows:
        cols = row.find_all(['td', 'th'])
        cols_text = [c.text.strip() for c in cols]
        
        # Lógica de extração baseada na estrutura do HTML SKF
        if len(cols_text) >= 4 and "mm/s" in cols_text[-1].lower():
            ponto = cols_text[0]
            valor_str = re.sub(r'[^\d.]', '', cols_text[-1])
            valor = float(valor_str) if valor_str else 0.0
            
            status = "Normal"
            if valor > 4.5:
                status = "Danger"
            elif valor > 2.8:
                status = "Alert"
                
            cur.execute("""
                INSERT INTO tb_medicoes_vibracao 
                (ponto_medicao, rota, valor_vibracao, status, data_medicao)
                VALUES (%s, %s, %s, %s, NOW());
            """, (ponto, rota_nome, valor, status))
            parsed_count += 1
            
    # Atualizar ciclo de 28 dias na tabela de rotas
    next_exec = datetime.now() + timedelta(days=28)
    cur.execute("""
        UPDATE tb_schedule_rotas 
        SET last_execution = NOW(), next_execution = %s, status = 'Compliant'
        WHERE nome_rota = %s;
    """, (next_exec, rota_nome))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return {"message": f"HTML processado com sucesso! {parsed_count} medições inseridas.", "rota": rota_nome}

@app.post("/api/registros-falha")
def salvar_registro_falha(registro: RegistroFalha):
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO tb_registros_falha 
        (id, ponto_medicao, equipamento_tag, area_set, validation_type, tipos_falha, descricao_falha, severidade, recomendacao, espectros_count)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE SET
            validation_type = EXCLUDED.validation_type,
            tipos_falha = EXCLUDED.tipos_falha,
            descricao_falha = EXCLUDED.descricao_falha,
            severidade = EXCLUDED.severidade,
            recomendacao = EXCLUDED.recomendacao;
    """, (
        registro.id, registro.ponto_medicao, registro.equipamento_tag, 
        registro.area_set, registro.validation_type, registro.tipos_falha, 
        registro.descricao_falha, registro.severidade, registro.recomendacao, 
        registro.espectros_count
    ))
    
    # Atualizar status da medição original para concluído
    cur.execute("""
        UPDATE tb_medicoes_vibracao 
        SET status = %s 
        WHERE ponto_medicao = %s;
    """, (registro.validation_type, registro.ponto_medicao))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return {"status": "success", "id": registro.id}
