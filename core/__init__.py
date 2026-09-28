"""
core package init — Cấu hình driver MySQL sớm trước khi Django load settings.

Project dùng MySQL làm CSDL chính (theo CLBIP_Frontend_Integration_Prompt.md).
PyMySQL đóng vai trò driver thuần Python thay cho mysqlclient (không cần
biên dịch C extension, chạy được trên mọi môi trường: Windows/macOS/Linux/Render).
"""
try:  # pragma: no cover - import guard đơn giản
    import pymysql

    pymysql.install_as_MySQLdb()  # Django.db.backends.mysql sẽ nạp pymysql như MySQLdb
except ImportError:  # Môi trường chưa cài pymysql (ví dụ Render dùng PostgreSQL)
    pass
