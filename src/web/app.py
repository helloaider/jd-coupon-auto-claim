"""Flask 应用工厂"""
from __future__ import annotations
import os
from flask import Flask, jsonify, send_from_directory
from src.web.auth_middleware import init_auth
from src.web.config_api import config_bp
from src.web.scheduler_controller import scheduler_bp, SchedulerController
from src.web.log_reader import log_bp
from src.web.result_api import result_bp
from src.version import __version__


def create_app(config_path: str = "config.yaml") -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["CONFIG_PATH"] = config_path

    # 注入 SchedulerController 单例
    app.extensions["scheduler_controller"] = SchedulerController()

    # 注册 Basic Auth 中间件
    init_auth(app)

    # 注册蓝图
    app.register_blueprint(config_bp)
    app.register_blueprint(scheduler_bp)
    app.register_blueprint(log_bp)
    app.register_blueprint(result_bp)

    # 静态文件路由
    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static")

    @app.route("/")
    def index():
        return send_from_directory(static_dir, "index.html")

    @app.route("/static/<path:filename>")
    def static_files(filename):
        return send_from_directory(static_dir, filename)

    @app.route("/api/version", methods=["GET"])
    def get_version():
        """返回当前应用版本号。"""
        return jsonify({"version": __version__}), 200

    return app
