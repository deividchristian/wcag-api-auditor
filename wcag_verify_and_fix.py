import argparse
import json
import os
import re
from typing import Any, Dict, List, Tuple

from playwright.sync_api import sync_playwright


# ---------------------------
# Helpers: axe + reporting
# ---------------------------

def line_from_index(text: str, idx: int) -> int:
    return text.count("\n", 0, max(idx, 0)) + 1

def find_line_number(source: str, snippet: str) -> int | None:
    """
    Devuelve línea (1-indexed) donde aparece snippet en source.
    Best-effort: si no lo encuentra, devuelve None.
    """
    if not source or not snippet:
        return None
    pos = source.find(snippet)
    if pos == -1:
        return None
    return line_from_index(source, pos)

def print_console_report(title: str, issues: list[dict], fixes: list[dict]) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)

    print("\n[Errores detectados por axe (violations)]")
    if not issues:
        print(" - Ninguno")
    else:
        for it in issues:
            ln = it.get("line")
            ln_txt = f"línea {ln}" if ln else "línea ?"
            rule = it.get("rule_id")
            help_ = it.get("help")
            target = it.get("target")
            print(f" - {ln_txt}: {rule} | {help_} | target={target}")

    print("\n[Correcciones aplicadas en html_bad_fixed (best-effort)]")
    if not fixes:
        print(" - Ninguna")
    else:
        for fx in fixes:
            ln = fx.get("line")
            ln_txt = f"línea {ln}" if ln else "línea ?"
            rule = fx.get("rule")
            print(f" - {ln_txt}: {rule}")
    print()

def line_from_index(text: str, idx: int) -> int:
    # Devuelve línea 1-based
    return text.count("\n", 0, idx) + 1

def load_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()

def save_file(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def load_axe_source(axe_path: str) -> str:
    if not os.path.exists(axe_path):
        raise FileNotFoundError(
            f"No encontré {axe_path}. Descarga axe.min.js (dist/axe.min.js) del repo oficial de axe-core."
        )
    return load_file(axe_path)

def run_axe(page, file_path: str, axe_source: str) -> Dict[str, Any]:
    url = "file://" + os.path.abspath(file_path).replace("\\", "/")
    page.goto(url, wait_until="load")

    # ✅ Inyecta axe DESPUÉS del goto (la navegación resetea el contexto)
    page.add_script_tag(content=axe_source)
    page.wait_for_function("() => typeof axe !== 'undefined'")

    return page.evaluate(
        """async () => {
            return await axe.run(document, {
                runOnly: { type: "tag", values: ["wcag2a","wcag2aa","wcag21a","wcag21aa"] }
            });
        }"""
    )

def summarize(results: Dict[str, Any]) -> Dict[str, int]:
    return {
        "violations": len(results.get("violations", [])),
        "incomplete": len(results.get("incomplete", [])),
        "passes": len(results.get("passes", [])),
    }

def winner(sum_good: dict, sum_bad: dict) -> str:
    #  Prioridad absoluta: violaciones
    if sum_good["violations"] < sum_bad["violations"]:
        return "A"
    if sum_good["violations"] > sum_bad["violations"]:
        return "B"

    # 2️⃣ Segundo criterio: incompletos
    if sum_good["incomplete"] < sum_bad["incomplete"]:
        return "A"
    if sum_good["incomplete"] > sum_bad["incomplete"]:
        return "B"

    # 3️⃣ Tercer criterio: más checks pasados
    if sum_good["passes"] > sum_bad["passes"]:
        return "A"
    if sum_good["passes"] < sum_bad["passes"]:
        return "B"

    return "EMPATE"

def suggest_fix(rule_id: str, node: Dict[str, Any]) -> str:
    html = node.get("html", "")
    target = node.get("target", [])
    failure = (node.get("failureSummary") or "").strip()

    hints = {
        "image-alt": "Añade alt a <img>. Decorativa: alt=\"\". Informativa: alt descriptivo.",
        "document-title": "Asegura <title> único y correctamente cerrado en <head>.",
        "html-has-lang": "Asegura <html lang=\"es-ES\"> (un solo lang, correcto).",
        "duplicate-id": "Haz IDs únicos (no repitas id=\"...\").",
        "label": "Inputs necesitan <label for=\"id\"> o aria-label/aria-labelledby.",
        "link-name": "Enlaces necesitan texto descriptivo y/o aria-label.",
        "button-name": "Botones necesitan nombre accesible (texto visible o aria-label).",
        "aria-valid-attr": "Elimina atributos ARIA inválidos (typos, atributos no permitidos).",
        "aria-valid-attr-value": "Corrige valores ARIA: true/false, menu, etc.",
        "region": "Usa landmarks correctos: <main>, <nav aria-label>, etc.",
        "landmark-one-main": "Debe existir un único <main> o role=\"main\".",
        "color-contrast": "Ajusta contraste de texto/fondo para cumplir AA.",
        "focus-visible": "No elimines outline; define foco visible en :focus-visible."
    }

    base = hints.get(rule_id, "Revisa la regla en helpUrl y corrige el HTML/CSS/ARIA.")
    where = f"Target: {target}" if target else "Target: (no disponible)"
    extra = f"\nDetalle: {failure}" if failure else ""
    snippet = f"\nHTML: {html}" if html else ""
    return f"{base}\n{where}{extra}{snippet}".strip()


# ---------------------------
# Basic auto-fixer (best-effort)
# ---------------------------

def best_effort_fix_html(bad_html: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Aplica correcciones seguras y documenta cambios con línea (best-effort).
    cambios_detallados: [{line, rule, before, after}]
    """
    changes: List[Dict[str, Any]] = []
    fixed = bad_html

    def log_change(rule: str, before: str, after: str, line: int | None):
        changes.append({
            "line": line,
            "rule": rule,
            "before": before,
            "after": after
        })

    def replace_first(pattern: str, repl: str, rule: str, flags=re.I | re.S) -> bool:
        nonlocal fixed
        m = re.search(pattern, fixed, flags)
        if not m:
            return False
        before = m.group(0)
        line = line_from_index(fixed, m.start())
        new_fixed = re.sub(pattern, repl, fixed, count=1, flags=flags)
        if new_fixed != fixed:
            log_change(rule, before, repl, line)
            fixed = new_fixed
            return True
        return False

    def replace_all(pattern: str, repl: str, rule: str, flags=re.I | re.S) -> int:
        """
        Reemplaza todas las coincidencias y registra cada una.
        """
        nonlocal fixed
        count = 0
        while True:
            m = re.search(pattern, fixed, flags)
            if not m:
                break
            before = m.group(0)
            line = line_from_index(fixed, m.start())
            new_fixed = re.sub(pattern, repl, fixed, count=1, flags=flags)
            if new_fixed == fixed:
                break
            log_change(rule, before, repl, line)
            fixed = new_fixed
            count += 1
        return count

    # 1) Fix duplicate lang: deja solo uno (es-ES)
    # (log best-effort: registramos la etiqueta <html...> antes/después si existe)
    m_html = re.search(r'<html\b[^>]*>', fixed, flags=re.I)
    if m_html:
        before = m_html.group(0)
        after = re.sub(r'\s+lang="[^"]+"', '', before, flags=re.I)
        after = re.sub(r'<html\b', '<html lang="es-ES"', after, count=1, flags=re.I)
        if after != before:
            log_change('Fix: <html> con un solo lang="es-ES".', before, after, line_from_index(fixed, m_html.start()))
            fixed = fixed[:m_html.start()] + after + fixed[m_html.end():]

    # 2) Ensure meta charset utf-8 only once; elimina utf8 incorrecto y dupes
    # quitar meta charset="utf8"
    replace_all(r'<meta\s+charset="utf8"\s*/?>\s*', '', 'Fix: eliminado <meta charset="utf8"> (incorrecto).', flags=re.I)

    # asegurar inserción de <meta charset="utf-8"> tras <head...> si no existe
    if not re.search(r'<meta\s+charset="utf-8"\s*/?>', fixed, flags=re.I):
        replace_first(
            r'(<head\b[^>]*>)',
            r'\1\n  <meta charset="utf-8">',
            'Fix: añadido <meta charset="utf-8"> en <head>.',
            flags=re.I
        )

    # normalizar formato meta charset
    replace_all(r'<meta\s+charset="utf-8"\s*/?>', '<meta charset="utf-8">', 'Fix: normalizado <meta charset="utf-8">.', flags=re.I)

    # eliminar duplicados extra dejando solo el primero
    metas = list(re.finditer(r'<meta charset="utf-8">', fixed, flags=re.I))
    if len(metas) > 1:
        # borrar del final hacia atrás para no romper índices
        for mm in reversed(metas[1:]):
            before = mm.group(0)
            line = line_from_index(fixed, mm.start())
            fixed = fixed[:mm.start()] + "" + fixed[mm.end():]
            log_change("Fix: eliminado <meta charset> duplicado.", before, "", line)

    # 3) Fix title tag (cierre y/o inserción)
    replace_first(
        r'<title>(.*?)<title>',
        r'<title>\1</title>',
        "Fix: <title> corregido (cierre faltante).",
        flags=re.I | re.S
    )
    if not re.search(r'<title>.*?</title>', fixed, flags=re.I | re.S):
        replace_first(
            r'(<head\b[^>]*>\s*(?:<meta[^>]*>\s*)*)',
            r'\1<title>Fase 1: Ejemplo de página accesible</title>\n',
            "Fix: añadido <title> por defecto.",
            flags=re.I | re.S
        )

    # 4) Fix viewport comma
    replace_all(
        r'content="width=device-width\s+initial-scale=1"',
        'content="width=device-width, initial-scale=1"',
        "Fix: meta viewport correcto (coma).",
        flags=re.I
    )

    # 5) Restore focus visible (outline:none -> outline visible)
    replace_all(
        r'outline:\s*none\s*;',
        'outline: 3px solid #ff9900;\n      outline-offset: 2px;',
        "Fix: foco visible (no outline:none).",
        flags=re.I
    )

    # 6) Fix skip link href
    replace_all(
        r'href="#contenido-principal[^"]*"',
        'href="#contenido-principal"',
        "Fix: skip-link apunta a #contenido-principal.",
        flags=re.I
    )

    # 7) Convert role="main" div to <main id="contenido-principal">
    replace_first(
        r'<div\s+role="main"\s+id="contenido"\s*>',
        '<main id="contenido-principal">',
        'Fix: landmark principal: <main id="contenido-principal">.',
        flags=re.I
    )
    # cierre: reemplazo “best effort”
    replace_first(
        r'</div>\s*<!-- footer',
        '</main>\n\n  <!-- footer',
        'Fix: cierre de <main> (antes era </div>).',
        flags=re.I
    )

    # 8) Fix mailto
    replace_all(
        r'href="mail:([^"]+)"',
        r'href="mailto:\1"',
        'Fix: enlace email mailto: (mail: -> mailto:).',
        flags=re.I
    )

    # 9) Add missing alt to banner.png (si no tiene alt)
    # Capturamos el tag que contenga banner.png sin alt, y le inyectamos alt
    pattern_banner = r'<img\b(?![^>]*\salt=)[^>]*\bsrc="banner\.png"[^>]*>'
    def _repl_banner(m):
        tag = m.group(0)
        if tag.endswith("/>"):
            return tag[:-2] + ' alt="Banner del sitio"/>'
        return tag[:-1] + ' alt="Banner del sitio">'
    # replace_all manual para log por match
    while True:
        m = re.search(pattern_banner, fixed, flags=re.I)
        if not m:
            break
        before = m.group(0)
        after = _repl_banner(m)
        if after != before:
            log_change('Fix: <img src="banner.png"> con alt.', before, after, line_from_index(fixed, m.start()))
            fixed = fixed[:m.start()] + after + fixed[m.end():]
        else:
            break

    # 10) Fix duplicate id="diseno-web" (renombra segunda ocurrencia)
    matches = list(re.finditer(r'id="diseno-web"', fixed))
    if len(matches) > 1:
        second = matches[1]
        before = second.group(0)
        line = line_from_index(fixed, second.start())
        fixed = fixed[:second.start()] + 'id="diseno-web-2"' + fixed[second.end():]
        log_change('Fix: IDs únicos (segundo diseno-web -> diseno-web-2).', before, 'id="diseno-web-2"', line)

    # 11) Fix ARIA values typos
    replace_all(r'aria-expanded="falso"', 'aria-expanded="false"', 'Fix: aria-expanded (falso -> false).', flags=re.I)
    replace_all(r'aria-haspopup="menuu"', 'aria-haspopup="menu"', 'Fix: aria-haspopup (menuu -> menu).', flags=re.I)
    replace_all(r'aria-hidden="falso"', 'aria-hidden="true"', 'Fix: aria-hidden (falso -> true).', flags=re.I)
    replace_all(r'aria-pressed="talvez"', 'aria-pressed="false"', 'Fix: aria-pressed (talvez -> false).', flags=re.I)

    return fixed, changes

# ---------------------------
# Main: compare + report + optional fix
# ---------------------------

def build_issue_list(results: Dict[str, Any], source_html: str | None = None) -> List[Dict[str, Any]]:
    out = []
    for v in results.get("violations", []):
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
                "line": line,  # ✅ línea aproximada
                "suggested_fix": suggest_fix(v.get("id"), node),
            })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--good", required=True, help="Ruta HTML bueno")
    ap.add_argument("--bad", required=True, help="Ruta HTML malo")
    ap.add_argument("--axe", default="axe.min.js", help="Ruta a axe.min.js")
    ap.add_argument("--out", default="reporte_wcag.json")
    ap.add_argument("--fixed", default="html_bad_fixed.html")
    args = ap.parse_args()

    # ✅ CARGAR AXE DESDE ARCHIVO LOCAL
    axe_source = load_axe_source(args.axe)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # EJECUTAR AXE EN AMBOS HTML (con axe_source)
        res_good = run_axe(page, args.good, axe_source)
        res_bad  = run_axe(page, args.bad, axe_source)

        # CALCULAR RESÚMENES
        sum_good = summarize(res_good)
        sum_bad  = summarize(res_bad)

        # COBERTURA: cuántas reglas realmente se evaluaron
        coverage_good = sum_good["passes"] + sum_good["violations"] + sum_good["incomplete"]
        coverage_bad  = sum_bad["passes"] + sum_bad["violations"] + sum_bad["incomplete"]

        # Estado (defendible) por archivo
        def status(s, coverage, min_cov=10):
            if coverage < min_cov:
                return "AUDITORÍA NO CONFIABLE (cobertura baja / HTML malformado)"
            if s["violations"] > 0:
                return "NO CUMPLE (violations detectadas)"
            if s["incomplete"] > 0:
                return "SIN VIOLACIONES DETECTADAS (requiere revisión manual)"
            return "CUMPLE (automático)"

        estado_good = status(sum_good, coverage_good)
        estado_bad  = status(sum_bad, coverage_bad)

        report = {

            "estado": {
                    "good": estado_good,
                    "bad": estado_bad
                },
                "coverage": {
                    "good": coverage_good,
                    "bad": coverage_bad
                },

            "quien_cumple": (
                    "GOOD" if estado_good.startswith("CUMPLE")
                    else "BAD" if estado_bad.startswith("CUMPLE")
                    else "INDETERMINADO"
                ),
            "resumen": {
                "good": sum_good,
                "bad": sum_bad,
            },
            "donde_no_cumple": {
                "good_violations": build_issue_list(res_good),
                "bad_violations": build_issue_list(res_bad),
            },
            "nota": "Automático con axe-core (WCAG 2.1 A/AA). Para conformidad total, complementar con revisión manual."
        }

        # ✅ Best-effort fix del HTML malo
        bad_html = load_file(args.bad)
        fixed_html, changes = best_effort_fix_html(bad_html)
        save_file(args.fixed, fixed_html)
        report["log_correcciones_formateado"] = [
            f'linea {c["line"]}: {c["rule"]} | BEFORE: {c["before"]} | AFTER: {c["after"]}'
            for c in changes
        ]

        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        browser.close()

    print(f"OK -> JSON: {args.out}")
    print(f"OK -> FIXED: {args.fixed}")
    print("Quién cumple:", report["quien_cumple"])
    print("Resumen GOOD:", sum_good)
    print("Resumen BAD:", sum_bad)

if __name__ == "__main__":
    main()