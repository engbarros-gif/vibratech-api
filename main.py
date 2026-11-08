@app.post("/api/upload-html")
async def upload_html(file: UploadFile = File(...), rota_nome: str = Form(...)):
    content = await file.read()
    soup = BeautifulSoup(content, 'html.parser')
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        inserted_points = 0
        agora = datetime.now()
        proxima = agora + timedelta(days=28)
        
        # Leitura das tabelas HTML do SKF
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows[1:]: # Pula o cabeçalho
                cols = row.find_all('td')
                if len(cols) >= 3:
                    equipamento = cols[0].get_text(strip=True) or "EQUIPMENT"
                    ponto = cols[1].get_text(strip=True) or "POINT-01"
                    valor_str = cols[2].get_text(strip=True).replace(',', '.')
                    
                    try:
                        valor = float(''.join(c for c in valor_str if c.isdigit() or c == '.'))
                    except ValueError:
                        valor = 0.0

                    # Inserção com nome_rota e data_inclusao preenchidos automaticamente
                    cur.execute(
                        """
                        INSERT INTO tb_medicoes_vibracao 
                        (equipamento_tag, area_set, ponto_medicao, data_hora, valor_vibracao, valor_limite, variacao_perc, status_alarme, validation_status, nome_rota, data_inclusao)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                        """,
                        (equipamento, "PM1", ponto, agora, valor, 0.05, 120.0, "Overall - Alert", "Unacknowledged", rota_nome, agora)
                    )
                    inserted_points += 1

        # Atualiza a tabela de cronograma de rotas
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
            "message": f"Relatório da rota '{rota_nome}' processado! {inserted_points} pontos gravados com sucesso."
        }
        
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao processar HTML: {str(e)}")
    finally:
        cur.close()
        conn.close()
