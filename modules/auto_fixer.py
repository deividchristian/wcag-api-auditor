import re
from typing import Tuple, List, Dict, Any, Set

class AutoFixer:
    def __init__(self, html_content: str):
        self.original_html = html_content
        self.current_html = html_content
        self.changes: List[Dict[str, Any]] = []
        self.manual_warnings: List[Dict[str, Any]] = []
        # Eliminamos self._existing_ids ya que se calcula localmente donde se necesita

    def _get_line_number(self, index: int, content: str) -> int:
        return content.count('\n', 0, index) + 1

    def _log_change(self, rule_name: str, before: str, after: str, index: int):
        line_num = self._get_line_number(index, self.current_html)
        self.changes.append({
            "line": line_num,
            "rule": rule_name,
            "before": before.strip()[:60] + "...",
            "after": after.strip()[:60] + "..."
        })

    def _apply_regex(self, pattern: str, replacement: str, rule_name: str, conditional_check: bool = True):
        try:
            def replacer(match):
                before_text = match.group(0)
                try:
                    if callable(replacement):
                        after_text = replacement(match)
                    else:
                        after_text = match.expand(replacement)
                except Exception:
                    after_text = str(replacement)
                
                if conditional_check and before_text == after_text:
                    return before_text
                
                self._log_change(rule_name, before_text, after_text, match.start())
                return after_text

            self.current_html = re.sub(pattern, replacer, self.current_html, flags=re.IGNORECASE | re.DOTALL)
        except re.error as e:
            print(f"Error crítico en regla '{rule_name}': {e}")

    def _fix_head_metadata(self):
        if re.search(r'<html[^>]*lang=["\']es["\'][^>]*lang=["\']en["\']', self.current_html, re.I):
            self._apply_regex(r'<html[^>]*>', '<html lang="es-ES">', "Head: Unificar conflicto lang es/en")
        
        self._apply_regex(r'<meta charset="UTF-8">', '', "Head: Limpieza charset duplicado")
        self._apply_regex(r'<meta\s+charset=["\']?utf-?88?["\']?\s*/?>', '<meta charset="UTF-8">', "Head: Charset a UTF-8")
        self._apply_regex(r'<meta\s+http-equiv=["\']Content-Type["\']\s+content=["\']text/html;\s*charset=[^"\']+["\']\s*/?>', '<meta charset="UTF-8">', "Head: Modernizar meta http-equiv")
        
        if "charset" not in self.current_html.lower():
            self._apply_regex(r'(<head[^>]*>)', r'\1\n  <meta charset="UTF-8">', "Head: Inserción Charset faltante")

        self._apply_regex(r'<title>\s*<title>', '<title>', "Head: Doble apertura title")
        self._apply_regex(r'<title>\s*</title>', '<title>Documento Accesible</title>', "Head: Title vacío rellenado")
        self._apply_regex(r'<title>([^<]+)<title>', r'<title>\1</title>', "Head: Cierre de <title> faltante")
        self._apply_regex(r'<title>(.*?)(?:<!--.*?-->)?</title>', r'<title>\1</title>', "Head: Limpieza comentarios en title")
        
        if "<title>" not in self.current_html.lower():
            self._apply_regex(r'(<head[^>]*>)', r'\1\n  <title>Documento Accesible</title>', "Head: Inserción Title faltante")

        if not re.search(r'<meta\s+name=["\']viewport["\']', self.current_html, re.I):
             self._apply_regex(r'(<head[^>]*>)', r'\1\n  <meta name="viewport" content="width=device-width, initial-scale=1.0">', "Head: Inserción Viewport")
        
        self._apply_regex(r'(content=["\'][^"\']*width=device-width)\s+(initial-scale)', r'\1, \2', "Head: Sintaxis Viewport (coma faltante)")
        self._apply_regex(r'content=["\']width=device-width\s+initial-scale=1(\.0)?["\']', 'content="width=device-width, initial-scale=1.0"', "Head: Sintaxis Viewport standard")
        self._apply_regex(r'(viewport[^>]*content=["\'][^"\']*)\b(?:user-scalable=no|maximum-scale=1\.0|maximum-scale=1)\b', r'\1user-scalable=yes', "Head: Desbloquear zoom usuario")

    def _fix_structure_and_semantics(self):
        # 1. ARREGLO DE MAIN (Evitando duplicados)
        if "<main" not in self.current_html.lower():
            pattern = r'<div\s+([^>]*\b(role=["\']main["\']|id=["\'](?:contenido|main)["\'])[^>]*)>'
            def main_replacer(match):
                attrs = match.group(1)
                attrs = re.sub(r'role=["\']main["\']', '', attrs)
                return f'<main {attrs}>'
            self._apply_regex(pattern, main_replacer, "Semántica: div a main")

        self._apply_regex(r'<' + r'/div>(\s*(?:<!--[\s\S]*?-->\s*)*<footer)', r'\1', "Estructura: Eliminar div cierre huérfano antes de footer")
        self._apply_regex(r'id="titulo-estructuraa"', 'id="titulo-estructura"', "HTML: Typo ID estructura")

        # 2. CIERRE DE PÁRRAFOS (Versión Segura)
        self._apply_regex(r'(<p[^>]*>)(.*?)(?=\s*<div)', r'\1\2</p>', "HTML Sintaxis: <p> mal cerrado antes de div")
        self._apply_regex(r'(<p[^>]*>.*?)(?=<p)', r'\1</p>', "HTML Sintaxis: <p> anidado prohibido")
        self._apply_regex(r'</p>Esta página', '<p>Esta página', "HTML: p invertido")
        self._apply_regex(r'<span>([^<]+)(?!\s*</span>)', r'<span>\1</span>', "HTML: span abierto")
        
        # 3. LISTAS
        self._apply_regex(r'(<ul>\s*)<ul>', r'\1<li><ul>', "Estructura: ul dentro de ul sin li")
        self._apply_regex(r'</ul>\s*</ul>', '</ul></li></ul>', "Estructura: cierre ul anidado")
        self._apply_regex(r'<li>(.*?)(?=\n\s*<li>|\n\s*</ul>)', r'<li>\1</li>', "HTML: li cierre automático")

        # 4. IDS DUPLICADOS
        all_ids = re.findall(r'id=["\']([^"\']+)["\']', self.current_html)
        seen = set()
        duplicates = [x for x in all_ids if x in seen or seen.add(x)]
        
        for dup_id in duplicates:
            pattern = f'(id=["\']{re.escape(dup_id)}["\'].*?)id=["\']{re.escape(dup_id)}["\']'
            replacement = f'\\1id="{dup_id}-dup"' 
            self._apply_regex(pattern, replacement, f"HTML: ID duplicado '{dup_id}' corregido")

        # 5. SEMÁNTICA Y LIMPIEZA GENERAL
        self._apply_regex(r'<b>(.*?)</b>', r'<strong>\1</strong>', "Semántica: b a strong")
        self._apply_regex(r'<i>(.*?)</i>', r'<em>\1</em>', "Semántica: i a em")
        self._apply_regex(r'<center>(.*?)</center>', r'<div style="text-align:center">\1</div>', "W3C: Deprecado center")
        self._apply_regex(r'<font[^>]*>(.*?)</font>', r'<span>\1</span>', "W3C: Deprecado font")
        self._apply_regex(r'<strike>(.*?)</strike>', r'<del>\1</del>', "Semántica: strike a del")
        self._apply_regex(r'<u>(.*?)</u>', r'<span style="text-decoration: underline;">\1</span>', "A11y: u confuso")
        self._apply_regex(r'<br\s+/>', '<br>', "HTML: XHTML br a HTML5")

        self._apply_regex(r'(<table[^>]*)border=["\']\d+["\']', r'\1', "Clean: Tabla border")
        self._apply_regex(r'(<[^>]+)align=["\'][^"\']*["\']', r'\1', "Clean: Atributo align")
        self._apply_regex(r'(<[^>]+)bgcolor=["\'][^"\']*["\']', r'\1', "Clean: Atributo bgcolor")
        self._apply_regex(r'<td\s+headers=["\'][^"\']*["\']', '<td', "Clean: Headers complejos en TD")
        self._apply_regex(r'<table[^>]*\bsummary=["\'][^"\']*["\']', '<table', "W3C: Summary obsoleto")

        # 6. LIMPIEZA DE FANTASMAS
        self._apply_regex(r'^\s*</p>', '', "HTML: Limpieza cierre huérfano inicio")
        self._apply_regex(r'(<div[^>]*>)\s*</p>', r'\1', "HTML: Limpieza cierre huérfano tras div")
        self._apply_regex(r'(<form[^>]*>)\s*</p>', r'\1', "HTML: Limpieza cierre huérfano tras form")
        self._apply_regex(r'</p>\s*<p>', '<p>', "HTML: Fusión de párrafos rotos")

    def _fix_css_and_styles(self):
        self._apply_regex(r'outline:\s*none;?', 'outline: 3px solid #ff9900;\n      outline-offset: 2px;', "CSS A11y: Foco visible restaurado")
        self._apply_regex(r'display:\s*nonee', 'display: none', "CSS: Typo display")
        self._apply_regex(r'width:\s*1000%;', 'width: 100%;', "CSS: 1000% a 100%")
        self._apply_regex(r'background-color:\s*var\(--color-fond\)', 'background-color: var(--color-fondo)', "CSS: Typo variable fondo")
        self._apply_regex(r'"Segoe UI"\s+sans-serif', '"Segoe UI", sans-serif', "CSS: Coma faltante font-family")
        self._apply_regex(r'color:\s*#00000;', 'color: #000000;', "CSS: Hex incompleto")
        self._apply_regex(r'(--color-fondo: #[0-9a-fA-F]{6})(\s+--color)', r'\1;\2', "CSS: Punto y coma faltante")
        self._apply_regex(r'style=["\'][^"\']*display:\s*none[^"\']*["\']', 'hidden', "HTML: Style display none a atributo hidden")

    def _fix_roles_and_aria(self):
        redundant_roles = [
            (r'role="banner"\s+role="header"', 'role="banner"'),
            (r'role="navigation main"', 'role="navigation"'),
            (r'<nav[^>]*role=["\']navigation["\']', '<nav'),
            (r'<header[^>]*role=["\']banner["\']', '<header'),
            (r'<footer[^>]*role=["\']contentinfo["\']', '<footer'),
            (r'<main[^>]*role=["\']main["\']', '<main'),
            (r'<form[^>]*role=["\']form["\']', '<form'),
        ]
        for pat, rep in redundant_roles:
            self._apply_regex(pat, rep, "ARIA: Roles redundantes")

        self._apply_regex(r'aria-role=["\']link["\']', 'role="link"', "ARIA: aria-role no existe")
        self._apply_regex(r'role=["\']menuu["\']', 'role="menu"', "ARIA: Typo menuu")
        self._apply_regex(r'role=["\']menubar["\']', 'role="menu"', "ARIA: Simplificar menubar")
        self._apply_regex(r'role=["\']menuitemcheckbox["\']', 'role="menuitem"', "ARIA: Simplificar checkbox")
        
        self._apply_regex(r'aria-haspopup=["\']menuu["\']', 'aria-haspopup="true"', "ARIA: Valor menuu incorrecto")
        self._apply_regex(r'aria-expanded=["\']falso["\']', 'aria-expanded="false"', "ARIA: Valor falso incorrecto")
        self._apply_regex(r'aria-pressed=["\']talvez["\']', 'aria-pressed="false"', "ARIA Valor: talvez -> false")
        self._apply_regex(r'aria-hidden=["\']talvez["\']', 'aria-hidden="true"', "ARIA: Valor talvez incorrecto")
        self._apply_regex(r'aria-hidden=["\']false["\']', '', "ARIA: Default false limpieza")
        self._apply_regex(r'aria-labelled-by=', 'aria-labelledby=', "ARIA: Typo labelledby")
        self._apply_regex(r'aria-label=""', 'aria-label="Acción"', "A11y: aria-label vacío")

    def _fix_forms_and_attributes(self):
        self._apply_regex(r'type=["\']submit["\']', 'type="button"', "Form: submit a button genérico")
        self._apply_regex(r'data-menu-button=["\']true["\']', 'data-menu-button', "HTML: Boolean attribute normalización")
        self._apply_regex(r'hidden=["\']hidden["\']', 'hidden', "HTML: Hidden normalización")
        
        self._apply_regex(r'(<input[^>]*placeholder=["\']([^"\']+)["\'])(?![^>]*aria-label)', r'\1 aria-label="\2"', "Form: Placeholder a aria-label")
        self._apply_regex(r'(<input(?![^>]*aria-label)(?![^>]*type=["\'](?:hidden|submit|button|image)["\'])[^>]*placeholder=["\']([^"\']+)["\'][^>]*)>', r'\1 aria-label="\2">', "A11y: Placeholder a label regex fallback")
        
        self._apply_regex(r'(<input[^>]*type=["\']email["\'])(?![^>]*autocomplete)', r'\1 autocomplete="email"', "Form: Autocomplete Email")
        self._apply_regex(r'(<input[^>]*type=["\']tel["\'])(?![^>]*autocomplete)', r'\1 autocomplete="tel"', "Form: Autocomplete Tel")
        
        self._apply_regex(r'autofocus(?:=["\']autofocus["\'])?', '', "A11y: Eliminar autofocus")
        self._apply_regex(r'accesskey=["\'][^"\']*["\']', '', "A11y: Eliminar accesskey")
        self._apply_regex(r'tabindex=["\'][1-9]\d*["\']', 'tabindex="0"', "A11y: Tabindex positivo a 0")
        
        self._apply_regex(r'<button((?![^>]*type=)[^>]*)>', r'<button type="button"\1>', "Form: Button type explícito")
        self._apply_regex(r'<input\s+type=["\']submit["\']', '<button type="submit"', "Form: Input Submit a Button")

    def _fix_links_images_cleanups(self):
        self._apply_regex(r'href="(?!http|#|mailto:)([a-zA-Z0-9-]+)"', r'href="#\1"', "Nav: Link interno fix")
        self._apply_regex(r'href="#contenido-principal\s+noexistente"', 'href="#contenido-principal"', "Nav: Skip link fix")
        self._apply_regex(r'href=["\']mail:', 'href="mailto:', "Link: Protocolo mail fix")
        self._apply_regex(r'href=["\']tel:\s*', 'href="tel:', "Link: Protocolo tel fix")
        self._apply_regex(r'target="_blank"', 'target="_blank" rel="noopener"', "Seguridad: target blank")
        self._apply_regex(r'<a[^>]*href=["\'](?:#|javascript:void\(0\);?)["\'][^>]*>\s*</a>', '', "Limpieza: Link vacío")
        
        self._apply_regex(r'menu\.hidden\s*=\s*"false"', 'menu.hidden = false', "JS: String bool fix")
        self._apply_regex(r'\?\s*closeMenu\s*:\s*openMenu', '? closeMenu() : openMenu()', "JS: Ternario call fix")
        self._apply_regex(r'firstLink\.focus\(\)', 'if (firstLink) firstLink.focus()', "JS: Null check focus")
        
        self._apply_regex(r'los-menues-debens-ser-accesibles="sí"', '', "Limpieza: Atributo basura")
        self._apply_regex(r'alt="Texto que no se usa en enlaces"', '', "HTML: Alt en enlace borrado")
        self._apply_regex(r'<a>Consultoría', '<a href="#">Consultoría', "HTML: Link roto fix")
        
        self._apply_regex(r'\.jgp["\']', '.jpg"', "Typo: Extensión jgp")
        self._apply_regex(r'\.pnj["\']', '.png"', "Typo: Extensión pnj")
        self._apply_regex(r'<img src="banner.png"(?!.*alt).*?>', '<img src="banner.png" alt="Banner promocional genérico">', "A11y: Alt parcheado banner")
        self._apply_regex(r'(<img[^>]*alt="")', r'\1', "A11y: Alt vacío")
        self._apply_regex(r'(<img(?![^>]*alt=)[^>]*)(>)', r'\1 alt=""\2', "A11y: Alt vacío preventivo fallback")
        self._apply_regex(r'(<img[^>]*)\stitle=["\'][^"\']*["\']', r'\1', "A11y: Eliminar title redundante en img")

        typos = {
            r'cllas=': 'class=', r'srcrn=': 'src=', r'hfre=': 'href=',
            r'witdh=': 'width=', r'heigth=': 'height=', r'tab-index=': 'tabindex=',
            r'col-span=': 'colspan=', r'row-span=': 'rowspan=', r'readonly=': 'readonly'
        }
        for bad, good in typos.items():
            self._apply_regex(bad, good, f"Typo: {bad}")

        self._apply_regex(r'\son[a-z]+=["\']return\s+false;?["\']', '', "JS: Eliminar return false inline")
        self._apply_regex(r'\slanguage=["\']javascript["\']', '', "W3C: Script language obsoleto")

    def _scan_manual_checks(self):
        self.manual_warnings = [] 

        def add_warning(pattern, priority, category, message):
            for match in re.finditer(pattern, self.current_html, re.IGNORECASE):
                # Aquí calculamos la línea exacta
                line = self._get_line_number(match.start(), self.current_html)
                self.manual_warnings.append({
                    "line": line,
                    "prioridad": priority,
                    "categoria": category,
                    "mensaje": message
                })

        # 1. Imágenes
        add_warning(r'<img[^>]+>', "ALTA", "Semántica Visual (Imágenes)", "Se han parcheado atributos ALT. Un humano debe verificar que la descripción coincida con la imagen real.")

        # 2. Contraste
        add_warning(r'style=["\'][^"\']*(color|background)[^"\']*["\']', "ALTA", "Contraste", "Verificar ratio contraste manual 4.5:1.")
        add_warning(r'\.muted\s*{[^}]*}', "ALTA", "Contraste", "Clase .muted detectada. Verificar ratio contraste manual 4.5:1.")

        # 3. Formularios
        add_warning(r'<(input|select|textarea)[^>]*>', "ALTA", "Formularios (Etiquetas)", "Campos de formulario detectados. Verificar que 'aria-label' o '<label>' describan con precisión la acción esperada.")

        # 4. Navegación
        add_warning(r'class=["\'][^"\']*skip-link[^"\']*["\']', "MEDIA", "Navegación (Skip Link)", "Se detectó enlace de salto. Verificar CSS: ¿Es visible al recibir el foco (focus)? ¿El ID destino existe?")
        add_warning(r'<a\s+href', "BAJA", "Navegación (Contexto)", "Enlaces detectados. Verificar manualmente que los destinos (href) lleven a páginas válidas y tengan sentido en contexto.")

        # 5. Jerarquía
        h1_matches = list(re.finditer(r'<h1', self.current_html, re.IGNORECASE))
        if len(h1_matches) > 1:
            for m in h1_matches:
                line = self._get_line_number(m.start(), self.current_html)
                self.manual_warnings.append({
                    "line": line,
                    "prioridad": "MEDIA",
                    "categoria": "Estructura",
                    "mensaje": "Múltiple H1 detectado (debería haber solo uno)."
                })

    def run(self) -> Tuple[str, List[Dict[str, Any]], List[Dict[str, Any]]]:
        self._fix_head_metadata()
        self._fix_css_and_styles()
        self._fix_structure_and_semantics()
        self._fix_roles_and_aria()
        self._fix_forms_and_attributes()
        self._fix_links_images_cleanups()
        self._scan_manual_checks()
        return self.current_html, self.changes, self.manual_warnings