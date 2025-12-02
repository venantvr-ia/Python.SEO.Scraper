# =============================================================================
# SEO Scraper Service - Dockerfile
# =============================================================================
FROM python:3.11-slim

# Métadonnées
LABEL maintainer="RVV"
LABEL description="Micro-service FastAPI de scraping avec Crawl4AI"
LABEL version="1.0.0"

# Variables d'environnement
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOST=0.0.0.0 \
    PORT=8001

# Répertoire de travail
WORKDIR /app

# Installer les dépendances système pour Playwright/Chromium
# Dépendances Playwright/Chromium
# Utilitaires
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libatspi2.0-0 \
    libgtk-3-0 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copier les fichiers de configuration
COPY pyproject.toml ./

# Installer les dépendances Python
RUN pip install --upgrade pip setuptools wheel \
    && pip install .

# Installer Playwright et les navigateurs
RUN crawl4ai-setup

# Copier le code source
COPY src/ ./src/

# Réinstaller en mode editable pour inclure le code source
RUN pip install -e .

# Exposer le port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Commande de démarrage
CMD ["python", "-m", "seo_scraper"]
