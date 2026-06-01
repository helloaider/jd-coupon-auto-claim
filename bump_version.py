"""自动递增 src/version.py 中的补丁版本号"""
import re

path = "src/version.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

m = re.search(r"(\d+)\.(\d+)\.(\d+)", content)
if not m:
    print("未找到版本号，跳过")
    raise SystemExit(1)

major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
new_ver = f"{major}.{minor}.{patch + 1}"
new_content = content.replace(m.group(0), new_ver, 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(new_content)

print(f"版本号更新：{m.group(0)} -> {new_ver}")
