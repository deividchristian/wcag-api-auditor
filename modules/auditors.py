import subprocess
import json
import os
import requests
from typing import Dict, Any

# --- Helper para limpiar salidas de Node.js ---
def safe_parse_json(raw_stdout: str) -> Dict[str, Any]:
    """
    Intenta extraer y parsear un objeto JSON válido de una cadena de texto sucia.
    Busca el primer '{' y el último '}'.
    """
    if not raw_stdout:
        return {}
        
    # 1. Intento directo (el ideal)
    try:
        return json.loads(raw_stdout)
    except json.JSONDecodeError:
        pass # Falló, probamos limpieza manual

    # 2. Búsqueda de patrón JSON (ignora logs de "Downloading...", warnings, etc.)
    try:
        start_idx = raw_stdout.find('{')
        end_idx = raw_stdout.rfind('}') + 1
        
        if start_idx != -1 and end_idx > start_idx:
            clean_json_str = raw_stdout[start_idx:end_idx]
            return json.loads(clean_json_str)
    except Exception:
        pass
        
    return None

# --- Funciones de Auditoría ---

def run_lighthouse(target_url: str) -> Dict[str, Any]:
    """
    Ejecuta Lighthouse contra una URL HTTP (localhost).
    Retorna el puntaje de accesibilidad (0-100).
    """
    print(f"   [Node] Ejecutando Lighthouse para {target_url}...")
    
    # Flags clave:
    # --quiet: Menos logs
    # --no-enable-error-reporting: Evita prompts interactivos
    cmd = [
        "npx", "lighthouse", target_url,
        "--output=json",
        "--only-categories=accessibility",
        "--chrome-flags='--headless --no-sandbox --disable-dev-shm-usage'",
        "--quiet",
        "--no-enable-error-reporting"
    ]
    
    try:
        # errors='replace' evita crasheos por emojis o caracteres raros en la consola
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        
        data = safe_parse_json(result.stdout)
        
        if not data:
            # Si falló el parseo, devolvemos el error crudo para debug
            return {"error": "Lighthouse output parsing failed", "raw_snippet": result.stdout[:200]}
        
        # Lighthouse devuelve "categories" -> "accessibility" -> "score" (0 a 1)
        score = data.get("categories", {}).get("accessibility", {}).get("score", 0)
        return {"score_accessibility": int(score * 100)}
        
    except Exception as e:
        return {"error": str(e)}

def run_pa11y(target_url: str) -> Dict[str, Any]:
    """
    Ejecuta Pa11y contra una URL HTTP (localhost).
    Retorna la lista de problemas detectados.
    """
    print(f"   [Node] Ejecutando Pa11y para {target_url}...")
    
    cmd = ["npx", "pa11y", target_url, "--reporter", "json"]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        
        data = safe_parse_json(result.stdout)
        
        if data is not None:
             # Pa11y devuelve un array directo de issues o un objeto si falló diferente
             if isinstance(data, list):
                 return {"issues_count": len(data), "issues": data}
             else:
                 # A veces devuelve un objeto error
                 return {"issues_count": 0, "issues": [], "raw_data": data}
        
        return {"error": "Pa11y parsing failed", "raw_snippet": result.stdout[:200]}
            
    except Exception as e:
        return {"error": str(e)}

def run_w3c_validator(file_path: str) -> Dict[str, Any]:
    """
    Envía el CONTENIDO del archivo HTML a la API pública del W3C Validator.
    NOTA: Requiere ruta de archivo físico.
    """
    print(f"   [HTTP] Consultando W3C Validator para {file_path}...")
    try:
        if not os.path.exists(file_path):
             return {"error": f"Archivo no encontrado: {file_path}"}

        with open(file_path, 'rb') as f:
            content = f.read()
        
        headers = {'Content-Type': 'text/html; charset=utf-8'}
        url = 'https://validator.w3.org/nu/?out=json'
        
        response = requests.post(url, headers=headers, data=content, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            messages = data.get("messages", [])
            errors = [m for m in messages if m.get("type") == "error"]
            return {
                "valid": len(errors) == 0,
                "error_count": len(errors), 
                "messages": messages
            }
        else:
            return {"error": f"W3C API returned status {response.status_code}"}
            
    except Exception as e:
        return {"error": str(e)}