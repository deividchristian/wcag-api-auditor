import argparse
import json
import os
import sys
import requests
from playwright.sync_api import sync_playwright

# --- CORRECCIÓN DE IMPORTACIÓN ---
# Intentamos importar desde la carpeta 'modules' donde tienes el archivo
try:
    from modules.auto_fixer import best_effort_fix_html
except ImportError:
    # Si falla, intentamos buscarlo en la raíz (por si acaso lo mueves)
    try:
        from auto_fixer import best_effort_fix_html
    except ImportError:
        print("Error CRITICO: No se encontro auto_fixer.py ni en la raiz ni en la carpeta 'modules'.")
        sys.exit(1)

def auditar_w3c_online(ruta_archivo):
    try:
        with open(ruta_archivo, 'rb') as f:
            contenido = f.read()
        
        headers = {'Content-Type': 'text/html; charset=utf-8'}
        url = 'https://validator.w3.org/nu/?out=json'
        
        respuesta = requests.post(url, data=contenido, headers=headers, timeout=20)
        
        if respuesta.status_code == 200:
            resultados = respuesta.json()
            mensajes = resultados.get('messages', [])
            errores = [m for m in mensajes if m.get('type') == 'error']
            return {
                "executed": True,
                "errors": len(errores),
                "messages": errores
            }
        else:
            return {"executed": False, "errors": f"Error HTTP {respuesta.status_code}"}
            
    except Exception as e:
        return {"executed": False, "errors": f"Excepcion W3C: {str(e)}"}

def line_from_index(text: str, idx: int) -> int:
    return text.count("\n", 0, max(idx, 0)) + 1

def find_line_number(source: str, snippet: str) -> int | None:
    if not source or not snippet:
        return None
    pos = source.find(snippet)
    if pos == -1:
        return None
    return line_from_index(source, pos)

def load_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()

def save_file(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def load_axe_source(axe_path: str) -> str:
    # 1. Buscamos ruta exacta dada
    if os.path.exists(axe_path):
        return load_file(axe_path)
    # 2. Buscamos en raiz
    if os.path.exists("axe.min.js"):
        return load_file("axe.min.js")
    # 3. Buscamos en modules
    if os.path.exists("modules/axe.min.js"):
        return load_file("modules/axe.min.js")
        
    raise FileNotFoundError(f"No encontre axe.min.js en ninguna ruta (raiz o modules).")

def run_axe(page, file_path: str, axe_source: str) -> dict:
    url = "file://" + os.path.abspath(file_path).replace("\\", "/")
    
    try:
        page.goto(url, wait_until="load", timeout=15000)
    except Exception as e:
        return {"error": str(e), "violations": []}

    has_body = page.evaluate("document.body !== null")
    if not has_body:
        return {"error": "Documento vacio o body null", "violations": []}
    
    page.add_script_tag(content=axe_source)
    
    axe_loaded = page.evaluate("typeof axe !== 'undefined'")
    if not axe_loaded:
        return {
            "violations": [{"id": "CRITICAL-ERROR", "impact": "critical", "help": "Axe no cargo. HTML roto.", "nodes": []}],
            "passes": [],
            "incomplete": []
        }

    return page.evaluate(
        """async () => {
            try {
                return await axe.run(document, {
                    runOnly: { type: "tag", values: ["wcag2a","wcag2aa","wcag21a","wcag21aa"] }
                });
            } catch(e) {
                return { error: e.toString(), violations: [] };
            }
        }"""
    )

def summarize(results: dict) -> dict:
    if "error" in results:
        return {"violations": 999, "incomplete": 0, "passes": 0, "error": results["error"]}
    return {
        "violations": len(results.get("violations", [])),
        "incomplete": len(results.get("incomplete", [])),
        "passes": len(results.get("passes", [])),
    }

def suggest_fix(rule_id: str, node: dict) -> str:
    html = node.get("html", "")
    target = node.get("target", [])
    failure = (node.get("failureSummary") or "").strip()

    hints = {
        "image-alt": "Anade alt a <img>. Decorativa: alt=\"\". Informativa: alt descriptivo.",
        "document-title": "Asegura <title> unico y correctamente cerrado en <head>.",
        "html-has-lang": "Asegura <html lang=\"es-ES\"> (un solo lang, correcto).",
        "duplicate-id": "Haz IDs unicos (no repitas id=\"...\").",
        "label": "Inputs necesitan <label for=\"id\"> o aria-label/aria-labelledby.",
        "link-name": "Enlaces necesitan texto descriptivo y/o aria-label.",
        "button-name": "Botones necesitan nombre accesible (texto visible o aria-label).",
        "aria-valid-attr": "Elimina atributos ARIA invalidos.",
        "aria-valid-attr-value": "Corrige valores ARIA: true/false, menu, etc.",
        "region": "Usa landmarks correctos: <main>, <nav aria-label>, etc.",
        "landmark-one-main": "Debe existir un unico <main> o role=\"main\".",
        "color-contrast": "Ajusta contraste de texto/fondo para cumplir AA.",
        "focus-visible": "No elimines outline; define foco visible en :focus-visible."
    }

    base = hints.get(rule_id, "Revisa la regla en helpUrl y corrige el HTML/CSS/ARIA.")
    where = f"Target: {target}" if target else ""
    return f"{base}\n{where}\nHTML: {html}".strip()

def build_issue_list(results: dict, source_html: str = None) -> list:
    out = []
    if "violations" in results:
        for v in results["violations"]:
            for node in v.get("nodes", []):
                snippet = node.get("html") or ""
                line = find_line_number(source_html, snippet) if source_html else None

                out.append({
                    "rule_id": v.get("id"),
                    "impact": v.get("impact"),
                    "help": v.get("help"),
                    "helpUrl": v.get("helpUrl"),
                    "wcag_tags": [t for t in v.get("tags", []) if "wcag" in t.lower()],
                    "target": node.get("target"),
                    "failureSummary": node.get("failureSummary"),
                    "html": snippet,
                    "line": line,
                    "suggested_fix": suggest_fix(v.get("id"), node),
                })
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--good", required=True)
    ap.add_argument("--bad", required=True)
    ap.add_argument("--axe", default="axe.min.js")
    ap.add_argument("--out", default="reporte_wcag.json")
    ap.add_argument("--fixed", default="html_bad_fixed.html")
    args = ap.parse_args()

    try:
        axe_source = load_axe_source(args.axe)
    except Exception as e:
        print(f"Error iniciando Axe: {e}")
        sys.exit(1)

    raw_html = load_file(args.bad)
    # Llamamos al fixer importado (ya sea de modules o raiz)
    pre_fixed_html, initial_changes = best_effort_fix_html(raw_html)
    
    temp_sanitized = args.bad + ".temp_sanitized.html"
    save_file(temp_sanitized, pre_fixed_html)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        res_bad = run_axe(page, temp_sanitized, axe_source)
        sum_bad = summarize(res_bad)
        
        browser.close()

    if os.path.exists(temp_sanitized):
        os.remove(temp_sanitized)

    w3c_res = auditar_w3c_online(args.bad)

    report = {
        "estado": "AUDIT_COMPLETE",
        "w3c": {
            "errors": w3c_res.get('errors', 0),
            "details": w3c_res.get('messages', [])
        },
        "resumen": {
            "bad": sum_bad
        },
        "donde_no_cumple": {
            "bad_violations": build_issue_list(res_bad, pre_fixed_html)
        },
        "nota": "Auditoria Hibrida (Pre-fix + Axe + W3C).",
        "log_correcciones_formateado": [
            f'Linea {c["line"]}: {c["rule"]} | BEFORE: {c["before"]}' for c in initial_changes
        ]
    }

    save_file(args.fixed, pre_fixed_html)
    
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"OK -> JSON: {args.out}")
    print(f"OK -> FIXED: {args.fixed}")
    print(f"Violaciones: {sum_bad.get('violations', 0)}")
    print(f"Correcciones: {len(initial_changes)}")

if __name__ == "__main__":
    main()