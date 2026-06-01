"""清理 dist/config.yaml：清空 cookie"""
import yaml

path = "dist/config.yaml"
with open(path, "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)

cfg["credential"] = {"cookie": ""}

with open(path, "w", encoding="utf-8") as f:
    yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)

print("dist/config.yaml 已清理")
