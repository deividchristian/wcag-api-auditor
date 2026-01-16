import os
import shutil
import threading
import uuid
from http.server import SimpleHTTPRequestHandler, HTTPServer
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

# Importamos tus módulos probados
from modules import axe_engine, auto_fixer, auditors

# --- CONFIGURACIÓN DEL SERVIDOR EFÍMERO ---
# Necesitamos esto en la API también, porque Lighthouse en Docker
# odia los archivos locales (file://).

SERVER_PORT = 8099
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = os.path.join(BASE_DIR, "temp_audits")

# Asegurar que existe el directorio temporal
os.makedirs(TEMP_DIR, exist_ok=True)

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

def start_background_server():
    """Inicia un servidor estático para servir los archivos temporales a Lighthouse."""
    try:
        server = HTTPServer(('0.0.0.0', SERVER_PORT), QuietHandler)
        server.root_directory = TEMP_DIR
        # Hack para forzar el directorio raíz del servidor
        os.chdir(TEMP_DIR)
        
        thread = threading.Thread(target=server.serve_forever)
        thread.daemon = True
        thread.start()
        print(f"🌍 Servidor Interno de Auditoría activo en puerto {SERVER_PORT}")
    except OSError:
        print("⚠️ El servidor interno ya estaba corriendo (esto es normal en reloads).")

# --- LIFESPAN (Arranque de FastAPI) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Antes de iniciar la API, levantamos el servidor estático
    # Volvemos al directorio base para no afectar imports
    current = os.getcwd()
    start_background_server()
    os.chdir(current) 
    yield
    # (Al apagar no hacemos nada especial, el hilo muere solo)

app = FastAPI(title="WCAG Auditor API (Hybrid)", lifespan=lifespan)

# --- MODELOS ---
class AuditRequest(BaseModel):
    html_content: str
    run_fixer: bool = True

# --- ENDPOINTS ---

@app.get("/")
def read_root():
    return {"status": "Online", "mode": "Hybrid (Python + Node)"}

@app.post("/audit")
async def audit_html(request: AuditRequest, background_tasks: BackgroundTasks):
    """
    1. Guarda el HTML.
    2. Ejecuta auditoría completa (Axe, Lighthouse, Pa11y, W3C).
    3. Aplica correcciones (Auto-fixer).
    4. Re-audita (opcional, para ver mejoras).
    """
    try:
        # 1. Gestión de Archivos Temporales
        job_id = str(uuid.uuid4())
        filename = f"{job_id}.html"
        fixed_filename = f"{job_id}_fixed.html"
        
        file_path = os.path.join(TEMP_DIR, filename)
        fixed_path = os.path.join(TEMP_DIR, fixed_filename)
        
        # Guardar HTML recibido
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(request.html_content)

        # Preparar URLs para las herramientas (apuntando al servidor interno)
        # Nota: En Render/Docker, localhost funciona para procesos internos
        target_url = f"http://localhost:{SERVER_PORT}/{filename}"
        
        # 2. Cargar Axe
        axe_src = axe_engine.load_axe_source("axe.min.js")

        results = {
            "job_id": job_id,
            "status": "completed",
            "audit_initial": {},
            "fixes_applied": [],
            "fixed_html_preview": None
        }

        # 3. FASE 1: Auditoría Inicial
        print(f"Running audit for {job_id}...")
        
        # Axe
        axe_raw = axe_engine.run_axe_audit(target_url, axe_src)
        results["audit_initial"]["axe"] = axe_engine.summarize_axe(axe_raw)
        
        # Lighthouse
        results["audit_initial"]["lighthouse"] = auditors.run_lighthouse(target_url)
        
        # Pa11y
        results["audit_initial"]["pa11y"] = auditors.run_pa11y(target_url)
        
        # W3C (Usa archivo físico)
        results["audit_initial"]["w3c"] = auditors.run_w3c_validator(file_path)

        # 4. FASE 2: Auto-Fixer
        if request.run_fixer:
            fixed_html, changes = auto_fixer.best_effort_fix_html(request.html_content)
            
            # Guardar arreglado para referencia (o futura re-auditoría)
            with open(fixed_path, "w", encoding="utf-8") as f:
                f.write(fixed_html)
                
            results["fixes_applied"] = changes
            results["fixed_html_preview"] = fixed_html[:500] + "... (truncated)"
            
            # Agregamos el HTML completo en un campo separado si se necesita
            results["full_fixed_html"] = fixed_html

        # Limpieza en segundo plano (borrar archivos temp después de unos segundos)
        background_tasks.add_task(cleanup_files, [file_path, fixed_path])

        return results

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def cleanup_files(paths):
    """Borra archivos temporales."""
    import time
    time.sleep(5) # Espera 5s para asegurar que procesos terminen
    for p in paths:
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass