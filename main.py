from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
import os
from datetime import datetime, timedelta

# Instancia o objeto app obrigatoriamente no topo
app = FastAPI(title="VibraTech API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
try:
    import psycopg2
    import psycopg2.extras
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

try:
    from bs4 import BeautifulSoup
    import pandas as pd
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

app = FastAPI(title="VibraTech API - Completa")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL")

def get_db_connection():
    if not DATABASE_URL or not DB_AVAILABLE:
        return None
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)

@app.get("/")
def home():
    return {"message": "API online!"}

@app.get("/health")
@app.get("/api/health")
def health_check():
    return {"status": "online", "db_connected": DB_AVAILABLE, "bs4_ready": BS4_AVAILABLE}

@app.get("/rotas")
@app.get("/api/rotas")
def get_rotas():
    fallback_route = [{
        "plan_id": "ERR", "route_name": "Erro na Conexão", "area": "N/A", "frequency": "N/A", 
        "last_execution": None, "next_execution": None, "responsable": "Sistema", "status": "Erro"
    }]
    conn = get_db_connection()
    if not conn: return fallback_route
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tb_schedule_rotas ORDER BY plan_id;")
        rotas = cur.fetchall()
        
        if not rotas:
            return fallback_route
            
        rotas_formatadas = []
        for r in rotas:
            rotas_formatadas.append({
                "plan_id": r.get("plan_id", ""),
                "route_name": r.get("route_name", ""),
                "area": r.get("area", ""),
                "frequency": r.get("frequency", ""),
                "last_execution": r.get("last_execution").isoformat() if r.get("last_execution") else "",
                "next_execution": r.get("next_execution").isoformat() if r.get("next_execution") else "",
                "responsable": r.get("responsable", ""),
                "status": r.get("status", "")
            })
        return rotas_formatadas
    except Exception as e: 
        print(f"Erro rotas: {e}")
        return fallback_route
    finally:
        cur.close()
        conn.close()

@app.get("/medicoes")
@app.get("/api/medicoes")
def get_medicoes():
    conn = get_db_connection()
    if not conn: 
        return []
    
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tb_medicoes_vibracao ORDER BY data_hora DESC LIMIT 100;")
        medicoes_cruas = cur.fetchall()
        
        medicoes_formatadas = []
        for m in medicoes_cruas:
            medicoes_formatadas.append({
                "id": m.get("id", len(medicoes_formatadas) + 1),
                "equipamento_tag": m.get("equipamento_tag", ""),
                "ponto_medicao": m.get("ponto_medicao", ""),
                "data_hora": m.get("data_hora").isoformat() if m.get("data_hora") else "",
                "valor_medido": m.get("valor_medido"),
                "valor_limite": m.get("valor_limite"),
                "variacao_perc": m.get("variacao_perc"),
                "unidade": m.get("unidade", ""),
                "status_alarme": m.get("status_alarme", "---"),
                "nome_rota": m.get("nome_rota", ""),
                "status": "Unacknowledged"
            })
        return medicoes_formatadas
    except Exception as e:
        print(f"Erro medições: {e}")
        return []
    finally:
        cur.close()
        conn.close()

@app.post("/upload-html")
@app.post("/api/upload-html")
async def upload_html(file: UploadFile = File(...), rota_nome: str = Form(None)):
    if not BS4_AVAILABLE:
        return {"status": "error", "message": "Bibliotecas de parsing não disponíveis."}
    
    conn = get_db_connection()
    if not conn:
        return {"status": "error", "message": "Banco de dados indisponível."}

    try:
        cur = conn.cursor()
        contents = await file.read()
        html_content = contents.decode("utf-8", errors="ignore")
        soup = BeautifulSoup(html_content, "lxml")
        
        table = soup.find("table")
        if not table:
            return {"status": "error", "message": "Nenhuma tabela encontrada no HTML."}

        data = []
        current_machine, current_unit, current_area, current_point = "", "", "", ""
        current_datetime = None
        route_title = rota_nome if rota_nome else "Inspection Route"

        rows = table.find_all("tr")
        for row in rows:
            cols = [ele.get_text(strip=True) for ele in row.find_all(["td", "th"])]
            cols_clean = [c for c in cols if c != ""]
            if len(cols_clean) < 3 or "Machine Description" in cols_clean[0] or "POINT name" in str(cols_clean):
                continue

            if cols_clean[0] != "---":
                current_machine = cols_clean[0]
                current_unit = cols_clean[1] if len(cols_clean) > 1 else ""
                current_area = cols_clean[2] if len(cols_clean) > 2 else ""
                current_point = cols_clean[3] if len(cols_clean) > 3 else ""

            if len(cols_clean) > 3 and cols_clean[3] != "---":
                current_point = cols_clean[3]

            dh_raw = cols_clean[4] if len(cols_clean) > 4 else None
            if dh_raw and dh_raw != "---":
                dt_parsed = pd.to_datetime(dh_raw, errors="coerce")
                if pd.notna(dt_parsed): current_datetime = dt_parsed

            vm_raw = cols_clean[5] if len(cols_clean) > 5 else None
            vl_raw = cols_clean[6] if len(cols_clean) > 6 else None
            var_raw = cols_clean[7] if len(cols_clean) > 7 else None
            unidade = cols_clean[8] if len(cols_clean) > 8 else ""
            status_alarme = cols_clean[-1] if len(cols_clean) > 0 else "---"

            valor_medido = pd.to_numeric(vm_raw, errors="coerce")
            valor_limite = pd.to_numeric(vl_raw, errors="coerce")
            variacao_perc = pd.to_numeric(var_raw, errors="coerce")

            if pd.notna(variacao_perc) and variacao_perc > 200.0:
                if status_alarme == "---" or not status_alarme:
                    status_alarme = "Alert: High Deviation (>200%)"

            data.append({
                "equipamento_tag": current_machine,
                "unidade_fabril": current_unit,
                "area_set": current_area,
                "ponto_medicao": current_point,
                "data_hora": current_datetime,
                "valor_medido": float(valor_medido) if pd.notna(valor_medido) else None,
                "valor_limite": float(valor_limite) if pd.notna(valor_limite) else None,
                "variacao_perc": float(variacao_perc) if pd.notna(variacao_perc) else None,
                "unidade": unidade,
                "status_alarme": status_alarme,
                "nome_rota": route_title
            })

        if not data:
            return {"status": "error", "message": "Nenhum dado válido extraído."}

        df_raw = pd.DataFrame(data)

        def agrupar_alarmes(group):
            linha_base = group.iloc[0].copy()
            if pd.isna(linha_base["valor_medido"]):
                vm_validos = group["valor_medido"].dropna()
                if not vm_validos.empty: linha_base["valor_medido"] = vm_validos.iloc[0]
            
            alarmes_validos = [str(st) for st in group["status_alarme"].unique() if st and str(st) != "---"]
            linha_base["status_alarme"] = "\n".join(alarmes_validos) if alarmes_validos else "---"
            return linha_base

        df = (df_raw.groupby(["equipamento_tag", "p
