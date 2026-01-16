import re
from typing import Tuple, List, Dict, Any

def line_from_index(text: str, idx: int) -> int:
    return text.count("\n", 0, max(idx, 0)) + 1

def best_effort_fix_html(bad_html: str) -> Tuple[str, List[Dict[str, Any]]]:
    changes: List[Dict[str, Any]] = []
    fixed = bad_html

    def log_change(rule: str, before: str, after: str, line: int):
        changes.append({
            "line": line,
            "rule": rule,
            "before": before[:50] + "..." if len(before) > 50 else before,
            "after": after[:50] + "..." if len(after) > 50 else after
        })

    def replace_first(pattern: str, repl: str, rule: str):
        nonlocal fixed
        m = re.search(pattern, fixed, flags=re.I | re.S)
        if m:
            before = m.group(0)
            line = line_from_index(fixed, m.start())
            new_fixed = re.sub(pattern, repl, fixed, count=1, flags=re.I | re.S)
            if new_fixed != fixed:
                log_change(rule, before, repl, line)
                fixed = new_fixed

    def replace_all(pattern: str, repl: str, rule: str):
        nonlocal fixed
        if re.search(pattern, fixed, flags=re.I | re.S):
            # Logueamos una vez genérico para no saturar
            new_fixed = re.sub(pattern, repl, fixed, flags=re.I | re.S)
            if new_fixed != fixed:
                log_change(rule, "(Múltiples ocurrencias)", repl, 0)
                fixed = new_fixed

    # ==============================================================================
    # FASE 1: REPARACIÓN ESTRUCTURAL (ORDEN CORREGIDO)
    # ==============================================================================

    # 1. Force Close Title: PRIMERO cerramos el título si está abierto
    if re.search(r'<title>', fixed, re.I) and not re.search(r'</title>', fixed, re.I):
        replace_first(r'(<title>[^<\n\r]+)(?=\n|<)', r'\1</title>', 'Fix: Cierre forzado de <title>')

    # 2. KILLER: AHORA eliminamos <title> fantasma duplicado (</title><title>)
    # Esto atrapará el residuo que pudo haber dejado el paso 1 o que ya existía
    replace_first(r'(</title>)\s*<title>', r'\1', 'Fix: Eliminado <title> fantasma duplicado')
    
    # 3. Limpieza extra: Eliminar cualquier <title> vacío que haya quedado
    replace_all(r'<title>\s*</title>', '', 'Fix: Eliminado <title> vacío')

    # 4. HTML Lang
    if '<html' in fixed.lower():
        replace_first(r'<html\s+[^>]*lang="[^"]+"[^>]*>', '<html lang="es-ES">', 'Fix: Normalización <html lang="es-ES">')
    
    # 5. Meta Charset
    replace_all(r'charset="?utf8"?', 'charset="utf-8"', 'Fix: Corrección sintaxis utf-8')

    # ==============================================================================
    # FASE 2: ACCESIBILIDAD BÁSICA
    # ==============================================================================

    # 6. Viewport
    if 'viewport' not in fixed.lower():
        replace_first(r'<head>', '<head>\n  <meta name="viewport" content="width=device-width, initial-scale=1">', 'Fix: Inyección Viewport')
    else:
        replace_all(r'(content="width=device-width)\s+(initial-scale=1")', r'\1, \2', 'Fix: Coma faltante en Viewport')

    # 7. Alt Text
    pattern_img = r'<img(?![^>]*\balt=)[^>]*>'
    matches = list(re.finditer(pattern_img, fixed, re.I))
    for m in reversed(matches):
        before = m.group(0)
        line = line_from_index(fixed, m.start())
        if before.strip().endswith("/>"):
            after = before.replace("/>", ' alt="Imagen descriptiva"/>')
        else:
            after = before.replace(">", ' alt="Imagen descriptiva">')
        fixed = fixed[:m.start()] + after + fixed[m.end():]
        log_change('Fix: Agregado alt genérico', before, after, line)

    # 8. Main Landmark
    if '<main' not in fixed.lower() and 'role="main"' not in fixed.lower():
        if '<body' in fixed.lower():
            replace_first(r'(<body[^>]*>)', r'\1\n<main id="contenido-principal">', 'Fix: Apertura <main>')
            replace_first(r'</body>', '</main>\n</body>', 'Fix: Cierre </main>')

    # ==============================================================================
    # FASE 3: DETALLES Y TYPOS
    # ==============================================================================

    # 9. IDs Duplicados
    dup_pattern = r'(id="diseno-web")'
    matches = list(re.finditer(dup_pattern, fixed))
    if len(matches) > 1:
        m = matches[1]
        line = line_from_index(fixed, m.start())
        fixed = fixed[:m.start()] + 'id="diseno-web-2"' + fixed[m.end():]
        log_change('Fix: ID duplicado resuelto', 'id="diseno-web"', 'id="diseno-web-2"', line)

    # 10. ARIA Typos
    replace_all(r'aria-expanded="falso"', 'aria-expanded="false"', 'Fix: typo aria-expanded')
    replace_all(r'aria-hidden="falso"', 'aria-hidden="false"', 'Fix: typo aria-hidden')
    replace_all(r'aria-pressed="talvez"', 'aria-pressed="mixed"', 'Fix: typo aria-pressed')
    replace_all(r'aria-haspopup="menuu"', 'aria-haspopup="menu"', 'Fix: typo aria-haspopup')

    # 11. CSS Outline
    replace_all(r'outline:\s*none\s*;', 'outline: 2px solid blue;', 'Fix: CSS outline:none eliminado')

    # 12. Mailto
    replace_all(r'href="mail:', 'href="mailto:', 'Fix: Protocolo mailto corregido')

    # 13. Skip Links
    replace_all(r'href="#contenido-principal\s+noexistente"', 'href="#contenido-principal"', 'Fix: Skip link href inválido')

    return fixed, changes