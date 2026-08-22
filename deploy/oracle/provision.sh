#!/usr/bin/env bash
# Oracle Cloud Always Free provisioning script for the AI Books backend.
# Run as root on the VM:  sudo bash provision.sh
# Assumes the app code + textbooks are already at /opt/aibooks
# (copied from your Windows machine via scp).
set -euo pipefail

APP_DIR="/opt/aibooks"
APP_USER="ubuntu"
SERVICE_NAME="aibooks"

echo "==> Updating system packages..."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3.11 python3.11-venv python3.11-dev \
  build-essential git curl nginx ufw

echo "==> Preparing app directory..."
mkdir -p "$APP_DIR"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "==> Creating virtualenv and installing dependencies (CPU torch)..."
sudo -u "$APP_USER" python3.11 -m venv "$APP_DIR/.venv"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install --no-cache-dir \
  -r "$APP_DIR/requirements-space.txt"

echo "==> Creating .env (fill in your keys after this script finishes)..."
if [ ! -f "$APP_DIR/.env" ]; then
  cat > "$APP_DIR/.env" <<'EOF'
HF_TOKEN=
GROQ_API_KEY=
QWEN_BASE_URL=
QWEN_API_KEY=none
QWEN_MODEL_NAME=Qwen/Qwen3.8-27B
MISTRAL_API_KEY=
TEXTBOOK_ROOT=/opt/aibooks/Nepal Textbooks Grade 1-10
EOF
  chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
  echo "    .env created - EDIT IT and paste your real API keys"
fi

echo "==> Creating systemd service..."
cat > /etc/systemd/system/$SERVICE_NAME.service <<EOF
[Unit]
Description=AI Books RAG backend
After=network.target

[Service]
User=$APP_USER
WorkingDirectory=$APP_DIR
Environment=PORT=8000
ExecStart=$APP_DIR/.venv/bin/python $APP_DIR/rag_api.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl start $SERVICE_NAME

echo "==> Configuring firewall..."
ufw allow OpenSSH
ufw allow 'Nginx Full'
echo "y" | ufw enable

echo "==> Configuring nginx reverse proxy..."
cat > /etc/nginx/sites-available/$SERVICE_NAME <<'EOF'
server {
    listen 80;
    server_name _;

    client_max_body_size 50m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
EOF
ln -sf /etc/nginx/sites-available/$SERVICE_NAME /etc/nginx/sites-enabled/$SERVICE_NAME
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable nginx
systemctl restart nginx

echo "==> Verifying backend is up..."
sleep 3
curl -s http://127.0.0.1:8000/api/books | head -c 300 || true
echo ""
echo "==> Done. Backend: http://127.0.0.1:8000"
echo "    Public:  http://$(curl -s ifconfig.me)"
echo ""
echo "NEXT: 1) nano $APP_DIR/.env  -> paste your real API keys"
echo "       2) sudo systemctl restart $SERVICE_NAME"
echo "       3) For HTTPS: sudo apt install certbot python3-certbot-nginx && sudo certbot --nginx"