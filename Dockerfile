# Usamos una imagen oficial de Microsoft que ya viene preparada para Playwright
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Configurar carpeta de trabajo
WORKDIR /app

# Copiar dependencias e instalarlas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar solo el navegador Chromium necesario
RUN playwright install chromium

# Copiar todos tus archivos (main.py, axe.min.js, etc.) al servidor
COPY . .

# Comando para arrancar la API escuchando en el puerto que asigne Render
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]