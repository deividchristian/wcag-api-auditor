import os
from typing import Dict, Any
from playwright.sync_api import sync_playwright

def load_axe_source(axe_path: str = "axe.min.js") -> str:
    """Carga el script de axe-core local."""
    if not os.path.exists(axe_path):
        if os.path.exists("axe.min.js"):
            with open("axe.min.js", "r", encoding="utf-8") as f:
                return f.read()
        return "" 
    with open(axe_path, "r", encoding="utf-8") as f:
        return f.read()

def run_axe_audit(target_url: str, axe_source: str) -> Dict[str, Any]:
    """
    Navega a la URL (localhost) e inyecta axe-core.
    YA NO calcula file://, confía en la URL que recibe.
    """
    if not axe_source:
        return {"error": "Axe source not found"}

    with sync_playwright() as p:
        # Lanzamos con argumentos para evitar bloqueos de CORS
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-web-security"])
        page = browser.new_page()
        try:
            # Ahora navegamos a http://localhost...
            page.goto(target_url, wait_until="load")
            
            # Inyección de script
            page.add_script_tag(content=axe_source)
            page.wait_for_function("() => typeof axe !== 'undefined'")
            
            results = page.evaluate("""async () => {
                return await axe.run(document, {
                    runOnly: { type: "tag", values: ["wcag2a","wcag2aa","wcag21a","wcag21aa"] }
                });
            }""")
            return results
        except Exception as e:
            return {"error": str(e)}
        finally:
            browser.close()

def summarize_axe(results: Dict[str, Any]) -> Dict[str, int]:
    if "error" in results:
        return {"error": 1}
    return {
        "violations": len(results.get("violations", [])),
        "incomplete": len(results.get("incomplete", [])),
        "passes": len(results.get("passes", [])),
    }