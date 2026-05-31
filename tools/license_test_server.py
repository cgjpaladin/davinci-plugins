#!/usr/bin/env python3
"""License 本地测试服务器 — 模拟腾讯云 SCF 环境。

使用 Python 内置 http.server，方便本地开发测试。
"""
import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["HMAC_SECRET"] = "local_dev_secret_key_32_bytes_min!"
os.environ["DB_PATH"] = "/tmp/local_license_test.db"

from cloud.license_server import main_handler


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers["Content-Length"])
        body = self.rfile.read(length).decode("utf-8")
        event = {
            "body": body,
            "path": self.path,
        }
        result = main_handler(event, None)
        self.send_response(result["statusCode"])
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(result["body"].encode("utf-8"))

    def log_message(self, format, *args):
        print(f"  {args[0]}")


if __name__ == "__main__":
    port = 18999
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"🧪 License 测试服务器: http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 服务器关闭")
        server.shutdown()
