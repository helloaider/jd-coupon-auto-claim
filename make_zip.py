"""打包发布 zip：exe + config.yaml + 使用说明.txt"""
import glob
import os
import re
import zipfile

with open("src/version.py", encoding="utf-8") as f:
    ver_content = f.read()

m = re.search(r"\d+\.\d+\.\d+", ver_content)
if not m:
    print("未找到版本号，终止")
    raise SystemExit(1)

v = m.group()
zip_name = f"dist/京东外卖定时优惠券抢券助手_v{v}.zip"
exe_pattern = f"dist/京东外卖定时优惠券抢券助手_v{v}.exe"

exe_files = glob.glob(exe_pattern)
if not exe_files:
    print(f"未找到 exe 文件：{exe_pattern}")
    raise SystemExit(1)

files = exe_files + ["dist/config.yaml", "dist/使用说明.txt"]

with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as z:
    for f in files:
        z.write(f, os.path.basename(f))

print(f"zip 已生成：{zip_name}")
