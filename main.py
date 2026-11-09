from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="VibraTech API - Compatibilidade Total")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def dados_rotas():
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
        },
        {
            "plan_id": "3M",
            "route_name": "#1PM COATERS A",
            "area": "PM1",
            "frequency": "Monthly",
            "last_execution": "2026-10-14 00:00:00",
            "next_execution": "2027-01-03 01:00:00",
            "responsable": "de Barros Marcelo",
            "status": "Pendente"
        }
    ]

@app.get("/")
def home():
    return {"message": "API online!"}

@app.get("/health")
@app.get("/api/health")
def health_check():
    return {"status": "online"}

# Rotas sem e com o prefixo /api para garantir compatibilidade total
@app.get("/rotas")
@app.get("/api/rotas")
def get_rotas():
    return dados_rotas()

@app.get("/medicoes")
@app.get("/api/medicoes")
def get_medicoes():
    return []

@app.post("/upload-html")
@app.post("/api/upload-html")
async def upload_html(file: UploadFile = File(...), rota_nome: str = Form(None)):
    return {
        "status": "success",
        "message": "Ficheiro HTML processado com sucesso!"
    }
