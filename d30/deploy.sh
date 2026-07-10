#!/bin/bash
# d30: деплой AI-сервиса на Ubuntu VPS
# Использование: bash deploy.sh

set -e

echo "=== Деплой AI-сервиса ==="

# 1. Ollama
if ! command -v ollama &> /dev/null; then
    echo "Устанавливаем Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
fi

echo "Скачиваем модель..."
ollama pull qwen2.5:3b

# 2. Python-зависимости
pip3 install fastapi uvicorn requests --quiet

# 3. systemd-сервис для сервера
cat > /etc/systemd/system/ai-service.service << EOF
[Unit]
Description=Private AI Service
After=network.target

[Service]
WorkingDirectory=$(pwd)
ExecStart=$(which uvicorn) server:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ai-service
systemctl start ai-service

echo ""
echo "=== Готово ==="
echo "Сервис запущен на порту 8000"
echo "Health check: curl http://localhost:8000/health"
