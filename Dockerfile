# Usamos la imagen oficial de Playwright (ya tiene Python y navegadores)
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# 1. Instalar Node.js y NPM (Necesario para Lighthouse y Pa11y)
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean

# 2. Configurar directorio de trabajo
WORKDIR /app

# 3. Instalar dependencias de Node.js (Lighthouse + Pa11y)
COPY package.json ./
RUN npm install

# 4. Instalar dependencias de Python
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 5. Instalar navegadores de Playwright (Solo Chromium para ahorrar espacio)
RUN playwright install chromium

# 6. Copiar el código fuente (Incluyendo carpeta modules/)
COPY . .

# 7. Exponer puerto para Render
EXPOSE 10000

# 8. Comando de arranque
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]