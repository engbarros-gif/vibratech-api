from fastapi import APIRouter, File, UploadFile, HTTPException, Form
import os
import pandas as pd
from bs4 import BeautifulSoup
from sqlalchemy import create_engine
from sqlalchemy.types import FLOAT, TIMESTAMP, VARCHAR
from datetime import datetime, timedelta
import psycopg2

router = APIRouter(prefix="/api", tags=["Parser SKF"])

DATABASE_URL = os.getenv("DATABASE_URL")

@router.post("/upload-html")
async def upload_html(file: UploadFile = File(...), plan_id: str = Form(None)):
    if not DATABASE_URL:
        raise HTTPException(status_code=500, detail="DATABASE_URL não configurada.")
    
    try:
        # 1. Lê o conteúdo do ficheiro HTML enviado pela interface React
        contents = await file.read()
        html_content = contents.decode("utf-8", errors="ignore")
        
        # 2. Parse do HTML com BeautifulSoup (usando html.parser para compatibilidade serverless)
        soup = BeautifulSoup(html_content, "html.parser")
        table = soup.find("table")
        
        if not table:
            raise HTTPException(status_code=400, detail="Nenhuma tabela encontrada no relatório SKF.")

        data = []
        current_machine = ""
        current_unit = ""
        current_area = ""
        current_point = ""
        current_datetime = None

        rows = table.find_all("tr")
        for row in rows:
            cols = [ele.get_text(strip=True) for ele in row.find_all(["td", "th"])]
            if not cols:
                continue

            cols_clean = [c for c in cols if c != ""]
            if len(cols_clean) < 3:
                continue

            if "Machine Description" in cols_clean[0] or "POINT name" in str(cols_clean):
                continue

            # Herança de Equipamento, Unidade e Área
            if cols_clean[0] != "---":
                current_machine = cols_clean[0]
                current_unit = cols_clean[1] if len(cols_clean) > 1 else ""
                current_area = cols_clean[2] if len(cols_clean) > 2 else ""
                current_point = cols_clean[3] if len(cols_clean) > 3 else ""

            if len(cols_clean) > 3 and cols_clean[3] != "---":
                current_point = cols_clean[3]

            dh_raw = cols_clean[4] if len(cols_clean) > 4 else None
            vm_raw = cols_clean[5] if len(cols_clean) > 5 else None
            vl_raw = cols_clean[6] if len(cols_clean) > 6 else None
            var_raw = cols_clean[7] if len(cols_clean) > 7 else None
            unidade = cols_clean[8] if len(cols_clean) > 8 else ""
            status_alarme = cols_clean[-1] if len(cols_clean) > 0 else "---"

            # Conversão de Data/Hora com Herança para linhas secundárias de alarme
            if dh_raw and dh_raw != "---":
                dt_parsed = pd.to_datetime(dh_raw, errors="coerce")
                if pd.notna(dt_parsed):
                    current_datetime = dt_parsed

            valor_medido = pd.to_numeric(vm_raw, errors="coerce")
            valor_limite = pd.to_numeric(vl_raw, errors="coerce")
            variacao_perc = pd.to_numeric(var_raw, errors="coerce")

            # Regra de Desvio > 200%
            if variacao_perc is not None and variacao_perc > 200.0:
                if status_alarme == "---" or not status_alarme:
                    status_alarme = "Alert: High Deviation (>200%)"

            data.append({
                "equipamento_tag": current_machine,
                "unidade_fabril": current_unit,
                "area_set": current_area,
                "ponto_medicao": current_point,
                "data_hora": current_datetime,
                "valor_medido": valor_medido,
                "valor_limite": valor_limite,
                "variacao_perc": variacao_perc,
                "unidade": unidade,
                "status_alarme": status_alarme,
            })

        if not data:
            raise HTTPException(status_code=400, detail="Nenhum dado válido extraído do HTML.")

        df_raw = pd.DataFrame(data)

        # 3. Consolidação com Quebra de Linha (\n) entre Alarmes
        def agrupar_alarmes(group):
            linha_base = group.iloc[0].copy()
            if pd.isna(linha_base["valor_medido"]):
                vm_validos = group["valor_medido"].dropna()
                if not vm_validos.empty:
                    linha_base["valor_medido"] = vm_validos.iloc[0]

            alarmes_validos = [
                str(st) for st in group["status_alarme"].unique()
                if st and str(st) != "---"
            ]
            if alarmes_validos:
                linha_base["status_alarme"] = "\n".join(alarmes_validos)
            else:
                linha_base["status_alarme"] = "---"
            return linha_base

        df = (
            df_raw.groupby(
                ["equipamento_tag", "ponto_medicao", "data_hora"],
                as_index=False,
                group_keys=False,
            )
            .apply(agrupar_alarmes)
            .reset_index(drop=True)
        )

        # 4. Mapeamento de Tipos e Gravação no Neon via SQLAlchemy
        db_url_sa = DATABASE_URL
        if db_url_sa.startswith("postgres://"):
            db_url_sa = db_url_sa.replace("postgres://", "postgresql://", 1)

        dtype_mapping = {
            "equipamento_tag": VARCHAR(100),
            "unidade_fabril": VARCHAR(50),
            "area_set": VARCHAR(100),
            "ponto_medicao": VARCHAR(50),
            "data_hora": TIMESTAMP,
            "valor_medido": FLOAT,
            "valor_limite": FLOAT,
            "variacao_perc": FLOAT,
            "unidade": VARCHAR(20),
            "status_alarme": VARCHAR(1000),
        }

        engine = create_engine(db_url_sa)
        df.to_sql(
            "tb_medicoes_vibracao",
            engine,
            if_exists="append", # Acumula as medições das rotas importadas
            index=False,
            dtype=dtype_mapping,
        )

        # 5. Atualiza o status da rota no Neon para 'Completed' e recalcula a próxima execução (+28 dias)
        conn_pg = psycopg2.connect(DATABASE_URL)
        cur_pg = conn_pg.cursor()
        agora = datetime.now()
        proxima_execucao = agora + timedelta(days=28)

        if plan_id:
            cur_pg.execute("""
                UPDATE tb_schedule_rotas 
                SET last_execution = %s, next_execution = %s, status = 'Completed'
                WHERE plan_id = %s;
            """, (agora, proxima_execucao, plan_id))
        else:
            cur_pg.execute("""
                UPDATE tb_schedule_rotas 
                SET last_execution = %s, next_execution = %s, status = 'Completed'
                WHERE plan_id = (SELECT plan_id FROM tb_schedule_rotas LIMIT 1);
            """, (agora, proxima_execucao))

        conn_pg.commit()
        cur_pg.close()
        conn_pg.close()

        return {
            "status": "success",
            "filename": file.filename,
            "points_saved": len(df),
            "message": f"Sucesso! {len(df)} pontos processados e gravados no Neon."
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar relatório SKF: {str(e)}")
