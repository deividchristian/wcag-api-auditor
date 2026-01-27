from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

# --- IMPORTACIÓN NUEVA ---
# Importamos la lógica orquestadora que creamos en auditor_jefa.py
from auditor_jefa import process_wcag_audit

app = FastAPI(title="WCAG Auditor API (Regex Optimized)")

# Configuración CORS (Importante para que Copilot/Power Automate puedan hablarle)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODELOS ---
class AuditRequest(BaseModel):
    # Power Automate enviará el HTML como texto dentro de este campo JSON
    html_content: str
    filename: str = "archivo_desde_copilot.html" # Opcional, nombre por defecto

# --- ENDPOINTS ---
@app.get("/")
def read_root():
    return {
        "status": "Online", 
        "mode": "Fast Regex Audit",
        "description": "API optimizada para Microsoft Copilot Studio"
    }

@app.post("/audit")
async def audit_html(request: AuditRequest):
    """
    Endpoint principal.
    Recibe el HTML crudo, lo limpia, lo analiza y retorna el JSON estructurado.
    """
    try:
        # Llamamos a tu función 'Jefa' directamente.
        # Ya no necesitamos crear archivos temporales ni hilos complejos.
        resultado = process_wcag_audit(request.html_content, request.filename)
        
        return resultado

    except Exception as e:
        print(f"❌ Error procesando solicitud: {str(e)}")
        # Retornamos un 500 limpio si algo explota
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # Esto permite correrlo localmente para pruebas con: python main.py
    uvicorn.run(app, host="0.0.0.0", port=8099)