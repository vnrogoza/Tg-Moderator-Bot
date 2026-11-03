FROM node:20-bookworm-slim

WORKDIR /app

# Install Python 3 and pip
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY package*.json ./
RUN npm install --no-audit --no-fund

COPY . .
RUN npm run build \
    && npm prune --omit=dev --no-audit --no-fund \
    && npm cache clean --force

ENV NODE_ENV=production
ENV PORT=3000

EXPOSE 3000

CMD ["python3", "server.py"]