#!/usr/bin/env bash
# =====================================================================
# Render Build Script — CLB IP ĐHSP Huế 2.0
# Chạy mỗi lần deploy: cài deps → collectstatic → migrate → seed demo
# =====================================================================
set -o errexit

echo ">>> [1/4] Cài đặt dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ">>> [2/4] Collect static files (WhiteNoise)..."
python manage.py collectstatic --no-input

echo ">>> [3/4] Chạy database migrations..."
python manage.py migrate

echo ">>> [4/4] Seed dữ liệu demo (idempotent — không nhân đôi)..."
python manage.py seed_demo || echo "⚠ seed_demo bị bỏ qua (không chặn deploy)"

echo ">>> BUILD HOÀN TẤT — sẵn sàng khởi động Gunicorn!"
