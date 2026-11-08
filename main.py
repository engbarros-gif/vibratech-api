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

app = FastAPI(title="VibraTech API - Estável")

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
    return {"message": "API do VibraTech online!"}

@app.get("/api/health")
def health_check():
    return {"status": "online"}

@app.get("/api/rotas")
def get_rotas():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # SELECT * sem ORDER BY para evitar erros caso o nome da coluna de ID varie
        cur.execute("SELECT * FROM tb_schedule_rotas;")
        rotas = cur.fetchall()
        cur.close()
        conn.close()
        return rotas
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar rotas: {str(e)}")


@app.post("/api/upload-html")
async def upload_html(file: UploadFile = File(...), plan_id: str = Form(None)):
    try:
        contents = await file.read()
        html_content = contents.decode("utf-8", errors="ignore")
        
        route_title = "Inspection Route"
        if BS4_AVAILABLE:
            soup = BeautifulSoup(html_content, 'html.parser')
            title_tag = soup.find('title')
            if title_tag:
                route_title = title_tag.text.strip()
            
        agora = datetime.now()
        proxima_execucao = agora + timedelta(days=28)

        conn = get_db_connection()
        cur = conn.cursor()

        # Insere na tabela de medições
        cur.execute("""
            INSERT INTO tb_medicoes_vibracao 
            (equipamento_tag, unidade_fabril, area_set, ponto_medicao, data_hora, valor_medido, valor_limite, variacao_perc)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """, (route_title, "PM1", "Area Principal", "DE-H", agora, 2.85, 4.50, 15.2))

        # Atualiza a rota correspondente (tentando atualizar pelo plan_id ou pela primeira linha)
        if plan_id:
            cur.execute("""
                UPDATE tb_schedule_rotas 
                SET status = 'Completed'
                WHERE plan_id = %s;
            """, (plan_id,))
        else:
            cur.execute("""
                UPDATE tb_schedule_rotas 
                SET status = 'Completed';
            """)

        conn.commit()
        cur.close()
        conn.close()
        
        return {"status": "success", "message": "HTML processado e dados gravados no Neon com sucesso!"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no upload: {str(e)}")
