from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
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

app = FastAPI(title="VibraTech API - Completa (Ciclo Fixo & Falhas)")

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

# --- MODELO PARA RECEBER OS DADOS DE FALHA DO FRONTEND ---
class RegistroFalha(BaseModel):
    id: str
    ponto_medicao: Optional[str] = ""
    equipamento_tag: Optional[str] = ""
    area_set: Optional[str] = ""
    validation_type: Optional[str] = ""
    tipos_falha: Optional[str] = ""
    descricao_falha: Optional[str] = ""

@app.get("/")
def home():
    return {"message": "API online: Ciclo Fixo 28d e Relatórios ativados!"}

@app.get("/health")
@app.get("/api/health")
def health_check():
    return {"status": "online", "db_connected": DB_AVAILABLE, "bs4_ready": BS4_AVAILABLE}

# --- ENDPOINTS DE ROTAS ---
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
        
        # 1. ATUALIZAÇÃO AUTOMÁTICA DE STATUS (LAZY UPDATE)
        # Se a rota estiver "Completed" mas faltar 7 dias (ou menos) para o vencimento, volta para "Pendente"
        cur.execute("""
            UPDATE tb_schedule_rotas 
            SET status = 'Pendente' 
            WHERE status = 'Completed' 
              AND next_execution IS NOT NULL 
              AND next_execution <= (CURRENT_TIMESTAMP + INTERVAL '7 days');
        """)
        conn.commit()

        # 2. LEITURA NORMAL DOS DADOS ATUALIZADOS
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

# --- ENDPOINTS DE MEDIÇÕES ---
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

# --- ENDPOINTS DE RELATÓRIOS DE FALHA ---
@app.get("/falhas")
@app.get("/api/falhas")
def get_falhas():
    conn = get_db_connection()
    if not conn: return []
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tb_registros_falha ORDER BY data_registro DESC;")
        falhas = cur.fetchall()
        retorno = []
        for f in falhas:
            f_data = dict(f)
            if f_data.get("data_registro"):
                f_data["data_registro"] = f_data["data_registro"].isoformat()
            retorno.append(f_data)
        return retorno
    except Exception:
        return []
    finally:
        if 'cur' in locals() and cur:
            try: cur.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass

@app.post("/falhas")
@app.post("/api/falhas")
def save_falha(falha: RegistroFalha):
    conn = get_db_connection()
    if not conn: return {"status": "error", "message": "Sem DB"}
    try:
        cur = conn.cursor()
        agora = datetime.now()
        
        # Verifica se o relatório já existe para permitir a edição
        cur.execute("SELECT id FROM tb_registros_falha WHERE id = %s", (falha.id,))
        exists = cur.fetchone()
        
        if exists:
            cur.execute("""
                UPDATE tb_registros_falha 
                SET validation_type=%s, tipos_falha=%s, descricao_falha=%s 
                WHERE id=%s
            """, (falha.validation_type, falha.tipos_falha, falha.descricao_falha, falha.id))
        else:
            cur.execute("""
                INSERT INTO tb_registros_falha 
                (id, ponto_medicao, equipamento_tag, area_set, data_registro, validation_type, tipos_falha, descricao_falha)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (falha.id, falha.ponto_medicao, falha.equipamento_tag, falha.area_set, agora, falha.validation_type, falha.tipos_falha, falha.descricao_falha))
        
        conn.commit()
        return {"status": "success", "id": falha.id}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        if 'cur' in locals() and cur:
            try: cur.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass


# --- ENDPOINT UPLOAD SKF (LÓGICA CICLO FIXO 28D) ---
@app.post("/upload-html")
@app.post("/api/upload-html")
async def upload_html(file: UploadFile = File(...), rota_nome: str = Form(None)):
    if not BS4_AVAILABLE:
        return {"status": "error", "message": "Bibliotecas de parsing indisponíveis."}
    
    conn = get_db_connection()
    if not conn: return {"status": "error", "message": "Sem DB"}

    cur = None
    try:
        cur = conn.cursor()
        contents = await file.read()
        soup = BeautifulSoup(contents.decode("utf-8", errors="ignore"), "html.parser")
        table = soup.find("table")
        if not table: return {"status": "error", "message": "Sem tabela no HTML."}

        data = []
        current_machine, current_unit, current_area, current_point = "", "", "", ""
        current_datetime = None
        route_title = rota_nome if rota_nome else "Inspection Route"

        for row in table.find_all("tr"):
            try:
                cols = [e.get_text(strip=True) for e in row.find_all(["td", "th"])]
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
                status_al = cols_clean[-1] if len(cols_clean) > 0 else "---"

                vm = pd.to_numeric(vm_raw, errors="coerce")
                vl = pd.to_numeric(vl_raw, errors="coerce")
                vp = pd.to_numeric(var_raw, errors="coerce")

                if pd.notna(vp) and vp > 200.0 and (status_al == "---" or not status_al):
                    status_al = "Alert: High Deviation (>200%)"

                data.append({
                    "equipamento_tag": current_machine, "unidade_fabril": current_unit,
                    "area_set": current_area, "ponto_medicao": current_point,
                    "data_hora": current_datetime,
                    "valor_medido": float(vm) if pd.notna(vm) else None,
                    "valor_limite": float(vl) if pd.notna(vl) else None,
                    "variacao_perc": float(vp) if pd.notna(vp) else None,
                    "unidade": cols_clean[8] if len(cols_clean) > 8 else "",
                    "status_alarme": status_al, "nome_rota": route_title
                })
            except Exception:
                continue

        if not data: return {"status": "error", "message": "Sem dados válidos."}

        df_raw = pd.DataFrame(data)

        def agrupar_alarmes(group):
            linha = group.iloc[0].copy()
            if pd.isna(linha["valor_medido"]):
                vm_validos = group["valor_medido"].dropna()
                if not vm_validos.empty: linha["valor_medido"] = vm_validos.iloc[0]
            alarmes = [str(s) for s in group["status_alarme"].unique() if s and str(s) != "---"]
            linha["status_alarme"] = "\n".join(alarmes) if alarmes else "---"
            return linha

        df = (df_raw.groupby(["equipamento_tag", "ponto_medicao", "data_hora"], as_index=False, group_keys=False)
              .apply(agrupar_alarmes).reset_index(drop=True))

        recs = []
        for _, r in df.iterrows():
            if pd.isna(r['data_hora']): continue
            recs.append((
                r['equipamento_tag'], r['unidade_fabril'], r['area_set'], r['ponto_medicao'], 
                r['data_hora'].to_pydatetime() if pd.notna(r['data_hora']) else None,
                r['valor_medido'], r['valor_limite'], r['variacao_perc'], 
                r['unidade'], r['status_alarme'], r['nome_rota']
            ))

        if recs:
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO tb_medicoes_vibracao 
                (equipamento_tag, unidade_fabril, area_set, ponto_medicao, data_hora, valor_medido, valor_limite, variacao_perc, unidade, status_alarme, nome_rota)
                VALUES %s""", recs
            )

        # MÁGICA DO CICLO FIXO AQUI
        agora = datetime.now()
        cur.execute("SELECT next_execution FROM tb_schedule_rotas WHERE route_name = %s;", (rota_nome,))
        rota_atual = cur.fetchone()
        
        if rota_atual and rota_atual.get("next_execution"):
            nova_prox_data = rota_atual["next_execution"] + timedelta(days=28)
        else:
            nova_prox_data = agora + timedelta(days=28)

        cur.execute("""
            UPDATE tb_schedule_rotas 
            SET status = 'Completed', last_execution = %s, next_execution = %s
            WHERE route_name = %s;
        """, (agora, nova_prox_data, rota_nome))

        conn.commit()
        return {"status": "success", "message": f"{len(recs)} medições guardadas com sucesso!"}

    except Exception as e:
        if conn: conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        if cur:
            try: cur.close()
            except Exception: pass
        if conn:
            try: conn.close()
            except Exception: pass
