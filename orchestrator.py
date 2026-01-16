import argparse
import json
import os
import threading
import time
from http.server import SimpleHTTPRequestHandler, HTTPServer
from modules import axe_engine, auto_fixer, auditors

# --- Configuración del Servidor Efímero ---
class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

def start_server(directory, port):
    server = HTTPServer(('localhost', port), QuietHandler)
    server.root_directory = directory 
    os.chdir(directory)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    return server

def run_full_audit(target_url, file_path_for_w3c, axe_src):
    """Ejecuta todos los auditores y retorna un diccionario de resultados."""
    results = {}
    
    print(f"    🔎 Ejecutando Axe-core...")
    axe_raw = axe_engine.run_axe_audit(target_url, axe_src)
    results["axe_core"] = axe_engine.summarize_axe(axe_raw)
    
    print(f"    💡 Ejecutando Lighthouse...")
    results["lighthouse"] = auditors.run_lighthouse(target_url)

    print(f"    ♿ Ejecutando Pa11y...")
    results["pa11y"] = auditors.run_pa11y(target_url)

    print(f"    🌐 Ejecutando W3C Validator...")
    results["w3c"] = auditors.run_w3c_validator(file_path_for_w3c)
    
    return results

def main():
    parser = argparse.ArgumentParser(description="WCAG Auditor (Audit -> Fix -> Verify)")
    parser.add_argument("--bad", required=True, help="Archivo HTML original")
    parser.add_argument("--out", default="reporte_final.json")
    parser.add_argument("--fixed", default="html_corregido.html")
    parser.add_argument("--axe-source", default="axe.min.js")
    
    args = parser.parse_args()

    # Rutas absolutas
    abs_bad_path = os.path.abspath(args.bad)
    abs_fixed_path = os.path.abspath(args.fixed)
    base_dir = os.path.dirname(abs_bad_path)
    file_name_bad = os.path.basename(abs_bad_path)
    file_name_fixed = os.path.basename(abs_fixed_path)
    
    original_cwd = os.getcwd()
    
    # Cargar Axe source una sola vez
    axe_src = axe_engine.load_axe_source(args.axe_source)

    # Iniciar servidor
    PORT = 8085
    print(f"🌍 Servidor activo en http://localhost:{PORT}")
    try:
        start_server(base_dir, PORT)
        time.sleep(1) # Espera técnica
        
        # URL targets
        url_bad = f"http://localhost:{PORT}/{file_name_bad}"
        url_fixed = f"http://localhost:{PORT}/{file_name_fixed}"

        report_data = {
            "original_file": args.bad,
            "fixed_file": args.fixed,
            "phase_1_audit_initial": {},
            "fixes_applied": [],
            "phase_2_audit_fixed": {}
        }

        # ---------------------------------------------------------
        # FASE 1: Auditoría Inicial (Archivo Roto)
        # ---------------------------------------------------------
        print("\n📊 FASE 1: Auditando archivo original (Estado actual)...")
        # NOTA: Si el HTML está muy roto, esperamos que esto falle o de 0 errores.
        report_data["phase_1_audit_initial"] = run_full_audit(url_bad, abs_bad_path, axe_src)

        # ---------------------------------------------------------
        # FASE 2: Reparación (Auto-Fixer)
        # ---------------------------------------------------------
        print("\n🛠️ FASE 2: Aplicando correcciones...")
        # Volvemos al directorio original para leer/escribir archivos correctamente
        os.chdir(original_cwd)
        
        with open(abs_bad_path, "r", encoding="utf-8", errors="replace") as f:
            original_html = f.read()
        
        fixed_html, changes = auto_fixer.best_effort_fix_html(original_html)
        
        with open(abs_fixed_path, "w", encoding="utf-8") as f:
            f.write(fixed_html)
            
        report_data["fixes_applied"] = changes
        print(f"   ✅ Se aplicaron {len(changes)} correcciones estructurales.")

        # ---------------------------------------------------------
        # FASE 3: Re-Auditoría (Verificación)
        # ---------------------------------------------------------
        print("\n📈 FASE 3: Verificando archivo corregido...")
        # El servidor ya está sirviendo el directorio, así que el nuevo archivo ya es accesible
        report_data["phase_2_audit_fixed"] = run_full_audit(url_fixed, abs_fixed_path, axe_src)

        # Guardar reporte final
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        print("\n🏁 PROCESO COMPLETADO EXITOSAMENTE.")
        print(f"   📄 Reporte Unificado: {args.out}")
        print(f"   🔧 Archivo Reparado: {args.fixed}")
        
        # Resumen comparativo en consola
        p1_score = report_data["phase_1_audit_initial"].get("lighthouse", {}).get("score_accessibility", "N/A")
        p2_score = report_data["phase_2_audit_fixed"].get("lighthouse", {}).get("score_accessibility", "N/A")
        
        print("\n--- COMPARATIVA DE IMPACTO ---")
        print(f"Lighthouse Score: {p1_score} -> {p2_score}")
        print(f"W3C Errors: {report_data['phase_1_audit_initial']['w3c'].get('error_count',0)} -> {report_data['phase_2_audit_fixed']['w3c'].get('error_count',0)}")

    except Exception as e:
        print(f"\n❌ ERROR CRÍTICO: {e}")
    finally:
        os.chdir(original_cwd)

if __name__ == "__main__":
    main()