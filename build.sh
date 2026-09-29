#!/usr/bin/env bash
# =====================================================================
# Render Build Script — CLB IP ĐHSP Huế 2.0
# Chạy mỗi lần deploy: cài deps → collectstatic → migrate
# Seed demo CHỈ chạy khi: SEED_DEMO=1 VÀ DJANGO_ENV != production.
# (Chặn tài khoản demo lọt vào môi trường thật — xem README "Triển khai an toàn")
# =====================================================================
set -o errexit

echo ">>> [1/4] Cài đặt dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ">>> [2/4] Collect static files (WhiteNoise)..."
python manage.py collectstatic --no-input

echo ">>> [3/4] Tạo bảng cache dùng chung cho throttle/axes (DatabaseCache)..."
python manage.py createcachetable

echo ">>> [4/4] Chạy database migrations..."
python manage.py migrate

echo ">>> Seed dữ liệu demo (tuỳ chọn, idempotent — không nhân đôi)..."
if [ "${SEED_DEMO}" = "1" ] && [ "${DJANGO_ENV}" != "production" ]; then
  python manage.py seed_demo || echo "⚠ seed_demo bị bỏ qua (không chặn deploy)"
else
  echo "    → Bỏ qua seed demo (yêu cầu SEED_DEMO=1 và DJANGO_ENV != production)."
fi

echo ">>> BUILD HOÀN TẤT — sẵn sàng khởi động Gunicorn!"
