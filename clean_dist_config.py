"""
生成 dist/config.yaml：
直接以 config.example.yaml 为模板写入，确保分发时配置干净、
不含个人信息，且包含所有最新字段。
"""
import shutil

shutil.copy("config.example.yaml", "dist/config.yaml")
print("dist/config.yaml 已从 config.example.yaml 生成")
