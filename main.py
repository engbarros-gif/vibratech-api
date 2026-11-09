from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
import os
import math
from datetime import datetime, timedelta

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

app = FastAPI(title="VibraTech API - Blindada contra NaN")

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
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    except Exception:
        return None

# Escudo para converter NaN ou Infinity em Null (None) para não rebentar o JSON
def safe_float(val):
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (ValueError, TypeError):
        return None

@app.get("/")
def home():
    return {"message": "API online e blindada contra NaN!"}

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
    if not conn: 
        return fallback_route
    
    cur = None
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tb_schedule_rotas ORDER BY plan_id;")
        rotas = cur.fetchall()
        
        if not rotas:
            return fallback_route
            
        rotas_formatadas = []
        for r in rotas:
            try:
                last_exec = r.get("last_execution")
                next_exec = r.get("next_execution")
                
                rotas_formatadas.append({
                    "plan_id": str(r.get("plan_id", "")),
                    "route_name": str(r.get("route_name", "")),
                    "area": str(r.get("area", "")),
                    "frequency": str(r.get("frequency", "")),
                    "last_execution": last_exec.isoformat() if last_exec else "",
                    "next_execution": next_exec.isoformat() if next_exec else "",
                    "responsable": str(r.get("responsable", "")),
                    "status": str(r.get("status", ""))
                })
            except Exception:
                continue
                
        return rotas_formatadas if rotas_formatadas else fallback_route
    except Exception: 
        return fallback_route
    finally:
        if cur:
            try: cur.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass

@app.get("/medicoes")
@app.get("/api/medicoes")
def get_medicoes():
    conn = get_db_connection()
    if not conn: 
        return []
    
    cur = None
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tb_medicoes_vibracao ORDER BY data_hora DESC LIMIT 100;")
        medicoes_cruas = cur.fetchall()
        
        medicoes_formatadas = []
        for idx, m in enumerate(medicoes_cruas):
            try:
                dh = m.get("data_hora")
                medicoes_formatadas.append({
                    "id": m.get("id", idx + 1),
                    "equipamento_tag": str(m.get("equipamento_tag", "")),
                    "ponto_medicao": str(m.get("ponto_medicao", "")),
                    "data_hora": dh.isoformat() if dh else "",
                    # Aplicação do escudo safe_float nos valores numéricos!
                    "valor_medido": safe_float(m.get("valor_medido")),
                    "valor_limite": safe_float(m.get("valor_limite")),
                    "variacao_perc": safe_float(m.get("variacao_perc")),
                    "unidade": str(m.get("unidade", "")),
                    "status_alarme": str(m.get("status_alarme", "---")),
                    "nome_rota": str(m.get("nome_rota", "")),
                    "status": "Unacknowledged"
                })
            except Exception:
                continue
                
        return medicoes_formatadas
    except Exception: 
        return []
    finally:
        if cur:
            try: cur.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass

@app.post("/upload-html")
@app.post("/api/upload-html")
async def upload_html(file: UploadFile = File(...), rota_nome: str = Form(None)):
    if not BS4_AVAILABLE:
        return {"status": "error", "message": "Bibliotecas de parsing não disponíveis."}
    
    conn = get_db_connection()
    if not conn:
        return {"status": "error", "message": "Banco de dados indisponível."}

    cur = None
    try:
        cur = conn.cursor()
        contents = await file.read()
        html_content = contents.decode("utf-8", errors="ignore")
        soup = BeautifulSoup(html_content, "html.parser")
        
        table = soup.find("table")
        if not table:
            return {"status": "error", "message": "Nenhuma tabela encontrada no HTML."}

        data = []
        current_machine, current_unit, current_area, current_point = "", "", "", ""
        current_datetime = None
        route_title = rota_nome if rota_nome else "Inspection Route"

        rows = table.find_all("tr")
        for row in rows:
            try:
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
            except Exception:
                continue

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

        df = (df_raw.groupby(["equipamento_tag", "ponto_medicao", "data_hora"], as_index=False, group_keys=False)
              .apply(agrupar_alarmes)
              .reset_index(drop=True))

        records_to_insert = []
        for _, row in df.iterrows():
            if pd.isna(row['data_hora']): continue
            records_to_insert.append((
                row['equipamento_tag'], row['unidade_fabril'], row['area_set'], row['ponto_medicao'], 
                row['data_hora'].to_pydatetime() if pd.notna(row['data_hora']) else None,
                row['valor_medido'], row['valor_limite'], row['variacao_perc'], 
                row['unidade'], row['status_alarme'], row['nome_rota']
            ))

        if records_to_insert:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO tb_medicoes_vibracao 
                (equipamento_tag, unidade_fabril, area_set, ponto_medicao, data_hora, valor_medido, valor_limite, variacao_perc, unidade, status_alarme, nome_rota)
                VALUES %s
                """,
                records_to_insert
            )

        agora = datetime.now()
        cur.execute("""
            UPDATE tb_schedule_rotas 
            SET status = 'Completed', last_execution = %s, next_execution = %s
            WHERE route_name = %s;
        """, (agora, agora + timedelta(days=28), rota_nome))

        conn.commit()
        return {"status": "success", "filename": file.filename, "message": f"{len(records_to_insert)} medições gravadas com sucesso!"}

    except Exception as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        return {"status": "error", "message": f"Erro no processamento: {str(e)}"}
    finally:
        if cur:
            try: cur.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass
