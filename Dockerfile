# Stage 1: Build Tailwind CSS
FROM node:20-alpine AS css-builder

WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci

COPY assets/ ./assets/
COPY server/ ./server/
COPY staticfiles/ ./staticfiles/
RUN npm run build:css


# Stage 2: Django application
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies for Pillow
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libjpeg62-turbo-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Copy built CSS from stage 1 into staticfiles source directory
COPY --from=css-builder /build/staticfiles/css/app.css /app/staticfiles/css/app.css

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
