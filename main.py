import os
import shutil
import threading
import uuid
from http.server import SimpleHTTPRequestHandler, HTTPServer
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.concurrency import run_in_threadpool  # <--- IMPORTANTE
from pydantic import BaseModel

# Importamos tus módulos probados
from modules import axe_engine, auto_fixer, auditors

# --- CONFIGURACIÓN DEL SERVIDOR EFÍMERO ---
SERVER_PORT = 8099
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = os.path.join(BASE_DIR, "temp_audits")

os.makedirs(TEMP_DIR, exist_ok=True)

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

def start_background_server():
    """Inicia un servidor estático para servir los archivos temporales a Lighthouse."""
    try:
        server = HTTPServer(('0.0.0.0', SERVER_PORT), QuietHandler)
        server.root_directory = TEMP_DIR
        os.chdir(TEMP_DIR)
        
        thread = threading.Thread(target=server.serve_forever)
        thread.daemon = True
        thread.start()
        print(f"🌍 Servidor Interno de Auditoría activo en puerto {SERVER_PORT}")
    except OSError:
        print("⚠️ El servidor interno ya estaba corriendo (esto es normal en reloads).")

# --- LIFESPAN ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    current = os.getcwd()
    start_background_server()
    os.chdir(current) 
    yield

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
    try:
        # 1. Gestión de Archivos Temporales
        job_id = str(uuid.uuid4())
        filename = f"{job_id}.html"
        fixed_filename = f"{job_id}_fixed.html"
        
        file_path = os.path.join(TEMP_DIR, filename)
        fixed_path = os.path.join(TEMP_DIR, fixed_filename)
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(request.html_content)

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
        
        # --- CORRECCIÓN CRÍTICA AQUI ---
        # Usamos await run_in_threadpool(...) para sacar la ejecución del bucle principal
        
        # A) Axe (El que causaba el error 500)
        print("   ... running Axe")
        axe_raw = await run_in_threadpool(axe_engine.run_axe_audit, target_url, axe_src)
        results["audit_initial"]["axe"] = axe_engine.summarize_axe(axe_raw)
        
        # B) Lighthouse (También es lento, mejor en hilo aparte)
        print("   ... running Lighthouse")
        results["audit_initial"]["lighthouse"] = await run_in_threadpool(auditors.run_lighthouse, target_url)
        
        # C) Pa11y
        print("   ... running Pa11y")
        results["audit_initial"]["pa11y"] = await run_in_threadpool(auditors.run_pa11y, target_url)
        
        # D) W3C
        print("   ... running W3C")
        results["audit_initial"]["w3c"] = await run_in_threadpool(auditors.run_w3c_validator, file_path)

        # 4. FASE 2: Auto-Fixer
        if request.run_fixer:
            print("   ... running Fixer")
            # El fixer es puro regex rápido, podría ir directo, pero lo aislamos por consistencia
            fixed_html, changes = await run_in_threadpool(auto_fixer.best_effort_fix_html, request.html_content)
            
            with open(fixed_path, "w", encoding="utf-8") as f:
                f.write(fixed_html)
                
            results["fixes_applied"] = changes
            results["fixed_html_preview"] = fixed_html[:500] + "... (truncated)"
            results["full_fixed_html"] = fixed_html

        background_tasks.add_task(cleanup_files, [file_path, fixed_path])

        return results

    except Exception as e:
        print(f"Error CRITICO: {e}")
        # Importante: Imprimir el stack trace en los logs de Render para debug
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

def cleanup_files(paths):
    import time
    time.sleep(5)
    for p in paths:
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass