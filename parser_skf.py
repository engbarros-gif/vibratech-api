from fastapi import APIRouter, File, UploadFile, HTTPException
import re

# Importação segura do BeautifulSoup
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

# Criamos um router dedicado para este módulo
router = APIRouter(prefix="/api", tags=["Parser SKF"])

@router.post("/upload-html")
async def upload_html(file: UploadFile = File(...)):
    if not BS4_AVAILABLE:
        raise HTTPException(status_code=500, detail="Biblioteca BeautifulSoup não está disponível no ambiente.")
    
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
            
        return {
            "status": "success",
            "filename": file.filename,
            "route_detected": route_title,
            "message": "HTML processado com sucesso pelo módulo isolado (parser_skf.py)!"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar HTML: {str(e)}")
