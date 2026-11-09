from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="VibraTech API - Teste Mock")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "API online!"}

@app.get("/api/health")
def health_check():
    return {"status": "online"}

@app.get("/api/rotas")
def get_rotas():
    # Devolve dados estáticos para garantir que o frontend os exibe imediatamente
    return [
        {
            "plan_id": "1M",
            "route_name": "#1PM BASEMENT 1",
            "area": "PM1",
            "frequency": "Monthly",
            "last_execution": "2026-10-19 00:00:00",
            "next_execution": "2026-12-13 01:00:00",
            "responsable": "de Barros Marcelo",
            "status": "Pendente"
        },
        {
            "plan_id": "2M",
            "route_name": "#1PM BASEMENT 2",
            "area": "PM1",
            "frequency": "Monthly",
            "last_execution": "2026-10-26 00:00:00",
            "next_execution": "2026-11-16 01:00:00",
            "responsable": "de Barros Marcelo",
            "status": "Pendente"
        }
    ]

@app.post("/api/upload-html")
async def upload_html(file: UploadFile = File(...), rota_nome: str = Form(None)):
    return {
        "status": "success",
        "message": "Upload simulado com sucesso!"
    }
