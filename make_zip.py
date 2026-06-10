"""打包发布 zip：exe + config.yaml + 使用说明.txt + data/ + logs/"""
import glob
import os
import re
import shutil
import zipfile

with open("src/version.py", encoding="utf-8") as f:
    ver_content = f.read()

m = re.search(r"\d+\.\d+\.\d+", ver_content)
if not m:
    print("未找到版本号，终止")
    raise SystemExit(1)

v = m.group()
zip_name = "dist/京东外卖定时优惠券领券助手.zip"
exe_pattern = "dist/京东外卖定时优惠券领券助手.exe"
readme_src  = "dist/使用说明.txt"
readme_dst  = f"dist/使用说明_v{v}.txt"

exe_files = glob.glob(exe_pattern)
if not exe_files:
    print(f"未找到 exe 文件：{exe_pattern}")
    raise SystemExit(1)

# 生成带版本号的使用说明副本
shutil.copy2(readme_src, readme_dst)

files = exe_files + ["dist/config.yaml", readme_dst]

with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as z:
    for f in files:
        z.write(f, os.path.basename(f))

    # 打入空目录（写入占位文件后删除，确保目录结构完整）
    # data/ 和 logs/ 必须存在，否则首次运行时相对路径写入会失败
    for empty_dir in ["data/", "logs/"]:
        z.mkdir(empty_dir)

# 清理临时副本
os.remove(readme_dst)

print(f"zip 已生成：{zip_name}")
