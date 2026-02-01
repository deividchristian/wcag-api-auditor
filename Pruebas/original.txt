import re
from typing import Tuple, List, Dict, Any

class AutoFixer:
    def __init__(self, html_content: str):
        self.original_html = html_content
        self.current_html = html_content
        self.changes: List[Dict[str, Any]] = []
        self.manual_warnings: List[Dict[str, Any]] = []

    def _get_line_number(self, index: int, content: str) -> int:
        return content.count('\n', 0, index) + 1

    def _apply_regex(self, pattern: str, replacement: str, rule_name: str):
        try:
            matches = list(re.finditer(pattern, self.current_html, flags=re.IGNORECASE | re.DOTALL))
        except re.error as e:
            print(f"Error en regex '{rule_name}': {e}")
            return

        for match in reversed(matches):
            start, end = match.span()
            before_text = match.group(0)
            line_num = self._get_line_number(start, self.current_html)
            
            try:
                after_text = match.expand(replacement)
            except Exception:
                after_text = replacement

            if before_text == after_text:
                continue

            self.current_html = (
                self.current_html[:start] + 
                after_text + 
                self.current_html[end:]
            )

            self.changes.append({
                "line": line_num,
                "rule": rule_name,
                "before": before_text.strip()[:40] + "...",
                "after": after_text.strip()[:40] + "..."
            })

    def _scan_manual_checks(self):
        """
        Escanea el código FINAL para detectar patrones que requieren intervención humana.
        No corrige nada, solo genera alertas para el reporte JSON.
        """
        html = self.current_html.lower()

        # 1. Lógica JavaScript Compleja
        if "<script" in html or "keydown" in html or "addeventlistener" in html:
            self.manual_warnings.append({
                "prioridad": "ALTA",
                "categoria": "Lógica JavaScript",
                "mensaje": "Se detectó código JS interactivo. Verificar manualmente: soporte tecla ESC, Focus Trap y gestión de estado (aria-expanded)."
            })

        # 2. Imágenes y Texto Alternativo
        if "<img" in html:
            self.manual_warnings.append({
                "prioridad": "ALTA",
                "categoria": "Semántica Visual (Imágenes)",
                "mensaje": "Se han parcheado atributos ALT. Un humano debe verificar que la descripción coincida con la imagen real (no usar 'imagen de')."
            })

        # 3. CSS Skip Links
        if "skip-link" in html or "saltar al contenido" in html:
            self.manual_warnings.append({
                "prioridad": "MEDIA",
                "categoria": "Navegación (Skip Link)",
                "mensaje": "Se detectó enlace de salto. Verificar CSS: ¿Es visible al recibir el foco (focus)? ¿El ID destino existe?"
            })

        # 4. Jerarquía de Títulos
        if "<h1" in html and ("<h2" in html or "<h3" in html):
            self.manual_warnings.append({
                "prioridad": "MEDIA",
                "categoria": "Semántica (Jerarquía)",
                "mensaje": "Se detectaron múltiples niveles de encabezados. Verificar que sigan un orden lógico (H1 -> H2 -> H3) sin saltos."
            })

        # 5. Contraste de Color
        if "color:" in html or "background" in html:
            self.manual_warnings.append({
                "prioridad": "ALTA",
                "categoria": "Diseño Visual (Contraste)",
                "mensaje": "Se detectaron colores definidos en CSS. Usar herramienta externa para validar ratio de contraste 4.5:1."
            })

        # 6. Validación W3C Estricta (Estructura compleja)
        if "<ul" in html or "<ol" in html or "<table" in html:
            self.manual_warnings.append({
                "prioridad": "BAJA",
                "categoria": "Estándares W3C",
                "mensaje": "Estructuras complejas (listas/tablas) detectadas. Verificar anidamiento correcto (ej: <ul> solo puede contener <li> directo)."
            })

        # 7. Labels en Formularios
        if "<input" in html or "<select" in html or "<textarea" in html:
            self.manual_warnings.append({
                "prioridad": "ALTA",
                "categoria": "Formularios (Etiquetas)",
                "mensaje": "Campos de formulario detectados. Verificar que 'aria-label' o '<label>' describan con precisión la acción esperada."
            })

        # 8. Orden del Foco (Tabindex)
        if "tabindex" in html:
            self.manual_warnings.append({
                "prioridad": "MEDIA",
                "categoria": "Navegación (Teclado)",
                "mensaje": "Se detectó uso de 'tabindex'. Verificar que el orden de tabulación sea lógico y no rompa la navegación natural."
            })

        # 9. Destino de Enlaces
        if "<a" in html:
            self.manual_warnings.append({
                "prioridad": "BAJA",
                "categoria": "Navegación (Contexto)",
                "mensaje": "Enlaces detectados. Verificar manualmente que los destinos (href) lleven a páginas válidas y tengan sentido en contexto."
            })

    def run(self) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Ejecuta las correcciones automáticas y LUEGO genera las alertas manuales.
        Retorna: (HTML Corregido, Log de Cambios, Alertas Manuales)
        """
        
        # --- FASE 1: CORRECCIÓN AUTOMÁTICA (LAS 46 REGLAS) ---
        rules = [
            # 1. CABECERA
            (r'<html[^>]*lang="es-ES"[^>]*lang="en"[^>]*>', '<html lang="es-ES">', 'Head: Conflicto de idiomas unificado.'),
            (r'<meta charset="UTF-8">', '', 'Head: Limpieza charset duplicado.'),
            (r'<meta\s+charset="utf8"\s*/?>', '<meta charset="UTF-8">', 'Head: Charset a UTF-8.'),
            (r'<title>\s*</title>', '<title>Documento Accesible</title>', 'Head: Title vacío rellenado.'),
            (r'<title>(.*?)<title>', r'<title>\1</title>', 'Head: Cierre de <title> faltante.'),
            (r'<title>(.*?)(?:<!--.*?-->)?</title>', r'<title>\1</title>', 'Head: Limpieza comentarios title.'),
            (r'content="width=device-width\s+initial-scale=1(\.0)?"', 'content="width=device-width, initial-scale=1.0"', 'Viewport: Sintaxis corregida.'),

            # 2. CSS
            (r'outline:\s*none;?', 'outline: 3px solid #ff9900;\n      outline-offset: 2px;', 'CSS A11y: Foco visible restaurado.'),
            (r'outline-offset:\s*2px;', 'outline-offset: 2px;', 'CSS: Check outline-offset.'),
            (r'display:\s*nonee;?', 'display: none;', 'CSS Typo: nonee -> none.'),
            (r'width:\s*1000%;', 'width: 100%;', 'CSS: 1000% -> 100%.'),
            (r'background-color:\s*var\(--color-fond\)', 'background-color: var(--color-fondo)', 'CSS Typo: Variable fondo.'),
            (r'"Segoe UI"\s+sans-serif', '"Segoe UI", sans-serif', 'CSS Sintaxis: Coma en font-family.'),
            (r'color:\s*#00000;', 'color: #000000;', 'CSS Hex: Dígito faltante.'),
            (r'(--color-fondo: #[0-9a-fA-F]{6})(\s+--color)', r'\1;\2', 'CSS Sintaxis: Punto y coma faltante.'),

            # 3. ESTRUCTURA
            (r'<div\s+role="main"\s+id="contenido">', '<main id="contenido-principal">', 'Semántica: div main a <main>.'),
            (r'<' + r'/div>(\s*(?:<!--[\s\S]*?-->\s*)*<footer)', r'\1', 'Estructura: Eliminado </div> huérfano.'),
            (r'</p>Esta página', '<p>Esta página', 'HTML Sintaxis: </p> invertido.'),
            (r'<p>(.*?)<p>', r'<p>\1</p>', 'HTML Sintaxis: <p> mal cerrado.'),
            (r'<span>([^<]+)(?!\s*</span>)', r'<span>\1</span>', 'HTML Sintaxis: <span> abierto.'),
            (r'<br\s+/>', '<br>', 'HTML: XHTML <br /> a HTML5.'),
            (r'id="titulo-estructuraa"', 'id="titulo-estructura"', 'HTML Typo: ID mal escrito.'),
            (r'<section id="diseno-web" aria-labelledby="titulo-diseno-web2">', '<section id="diseno-web-dup" aria-labelledby="titulo-diseno-web2">', 'HTML ID: Duplicado corregido.'),
            (r'<li>(.*?)(?=\n\s*<li>|\n\s*</ul>)', r'<li>\1</li>', 'HTML Sintaxis: <li> cerrado auto.'),

            # 4. ROLES
            (r'role="banner"\s+role="header"', 'role="banner"', 'ARIA: Roles redundantes.'),
            (r'role="navigation main"', 'role="navigation"', 'ARIA: Rol compuesto eliminado.'),
            (r'aria-role="link"', 'role="link"', 'ARIA: aria-role no existe.'),
            (r'role="menuu"', 'role="menu"', 'ARIA Typo: menuu.'),
            (r'role="menubar"', 'role="menu"', 'ARIA: menubar simplificado.'),
            (r'role="menuitemcheckbox"', 'role="menuitem"', 'ARIA: checkbox eliminado.'),

            # 5. ARIA VALORES
            (r'aria-haspopup="menuu"', 'aria-haspopup="true"', 'ARIA Valor: menuu -> true.'),
            (r'aria-expanded="falso"', 'aria-expanded="false"', 'ARIA Valor: falso -> false.'),
            (r'aria-pressed="talvez"', 'aria-pressed="false"', 'ARIA Valor: talvez -> false.'),
            (r'aria-hidden="talvez"', 'aria-hidden="true"', 'ARIA Valor: talvez -> true.'),
            (r'aria-hidden="false"', 'aria-hidden="true"', 'ARIA: Iconos ocultos.'),
            (r'aria-labelled-by=', 'aria-labelledby=', 'ARIA Typo: labelledby.'),
            (r'aria-label=""', 'aria-label="Acción"', 'A11y: aria-label vacío.'),

            # 6. ATRIBUTOS
            (r'type="submit"', 'type="button"', 'Form: submit -> button.'),
            (r'data-menu-button="true"', 'data-menu-button', 'HTML: Bool normalizado.'),
            (r'hidden="hidden"', 'hidden', 'HTML: Hidden normalizado.'),
            (r'href="(?!http|#|mailto:)([a-zA-Z0-9-]+)"', r'href="#\1"', 'Nav: Link interno sin #.'),
            (r'href="#contenido-principal\s+noexistente"', 'href="#contenido-principal"', 'Nav: Skip-link fix.'),

            # 7. JS PARCHES
            (r'menu\.hidden\s*=\s*"false"', 'menu.hidden = false', 'JS: "false" string fix.'),
            (r'\?\s*closeMenu\s*:\s*openMenu', '? closeMenu() : openMenu()', 'JS: Ternario call fix.'),
            (r'firstLink\.focus\(\)', 'if (firstLink) firstLink.focus()', 'JS: Null check focus.'),
            (r'=== true', '=== true', 'JS Check.'),

            # 8. LIMPIEZA
            (r'los-menues-debens-ser-accesibles="sí"', '', 'Limpieza: Atributo basura.'),
            (r'alt="Texto que no se usa en enlaces"', '', 'HTML: Alt en <a> borrado.'),
            (r'<a>Consultoría', '<a href="#">Consultoría', 'HTML: Link roto fix.'),
            (r'<img src="banner.png"(?: alt=".*?")?>', '<img src="banner.png" alt="Banner promocional genérico">', 'A11y: Alt parcheado.')
        ]

        # Ejecutar correcciones
        for pattern, replacement, name in rules:
            self._apply_regex(pattern, replacement, name)

        # --- FASE 2: GENERACIÓN DE ALERTAS MANUALES (LOS 9 HUMANOS) ---
        self._scan_manual_checks()

        return self.current_html, self.changes, self.manual_warnings

if __name__ == "__main__":
    # Ejemplo de uso para ver el JSON estructurado
    import json
    
    html_simulado = """
    <script> document.addEventListener('keydown', ...); </script>
    <img src="foto.jpg" alt="imagen">
    <a href="#" class="skip-link">Saltar</a>
    <h1 style="color: #ccc;">Titulo</h1>
    <input type="text">
    """
    
    fixer = AutoFixer(html_simulado)
    html_final, cambios, alertas = fixer.run()
    
    reporte_final = {
        "resumen": {
            "corregidos_auto": len(cambios),
            "pendientes_manual": len(alertas)
        },
        "log_automatico": cambios,
        "auditoria_manual_requerida": alertas
    }
    
    print(json.dumps(reporte_final, indent=2, ensure_ascii=False))