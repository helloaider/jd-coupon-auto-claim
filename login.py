"""
京东登录工具

用法：python login.py
- 会打开 Edge 浏览器窗口
- 你手动扫码或输入账号密码登录
- 登录成功后自动保存 Cookie 到 config.yaml
- 后续运行 main.py 直接使用保存的 Cookie，无需重新登录
"""
import sys
import os
import yaml
import time

def main():
    from playwright.sync_api import sync_playwright

    print("正在打开京东登录页面，请在浏览器中完成登录...")
    print("登录成功后程序会自动检测并保存 Cookie\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="msedge",
            headless=False,  # 必须有头，让你手动登录
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
            ),
            viewport={"width": 390, "height": 844},
            is_mobile=True,
        )

        page = context.new_page()

        # 打开京东登录页
        page.goto("https://plogin.m.jd.com/login/login", timeout=30000)
        print("请在浏览器中完成登录（扫码或账号密码）...")
        print("登录成功后会自动跳转，程序将自动保存 Cookie\n")

        # 等待登录成功：检测跳转到非登录页
        max_wait = 120  # 最多等 2 分钟
        for i in range(max_wait):
            time.sleep(1)
            current_url = page.url
            # 登录成功后会跳转离开登录页
            if "plogin" not in current_url and "login" not in current_url.lower():
                print(f"检测到登录成功，当前页面：{current_url}")
                break
            if i % 10 == 0 and i > 0:
                print(f"等待登录中... ({i}/{max_wait}秒)")
        else:
            # 超时后也尝试保存
            print("等待超时，尝试保存当前 Cookie...")

        # 等一下让 Cookie 完全写入
        time.sleep(2)

        # 获取所有 Cookie
        cookies = context.cookies()
        print(f"\n获取到 {len(cookies)} 个 Cookie")

        # 过滤出京东相关 Cookie
        jd_cookies = [c for c in cookies if "jd.com" in c.get("domain", "")]
        print(f"其中京东域名 Cookie：{len(jd_cookies)} 个")

        if not jd_cookies:
            print("未获取到京东 Cookie，请确认已成功登录")
            browser.close()
            sys.exit(1)

        # 检查关键 Cookie
        cookie_names = {c["name"] for c in jd_cookies}
        if "pt_key" not in cookie_names or "pt_pin" not in cookie_names:
            print("警告：未找到 pt_key 或 pt_pin，Cookie 可能不完整")
            print(f"已有的 Cookie 名称：{', '.join(sorted(cookie_names))}")

        # 拼接 Cookie 字符串
        cookie_str = "; ".join(
            f"{c['name']}={c['value']}"
            for c in jd_cookies
        )

        # 保存到 config.yaml
        config_path = "config.yaml"
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}

        if "credential" not in config:
            config["credential"] = {}
        config["credential"]["cookie"] = cookie_str

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        print(f"\n✅ Cookie 已保存到 {config_path}")
        print(f"   pt_pin: {next((c['value'] for c in jd_cookies if c['name'] == 'pt_pin'), '未找到')}")

        # 同时删除旧的加密凭证，强制重新加密
        for f in ["data/credentials.enc", "data/fernet.key"]:
            if os.path.exists(f):
                os.remove(f)
                print(f"   已删除旧凭证文件：{f}")

        print("\n现在可以运行 python main.py 启动自动领券了")
        browser.close()


if __name__ == "__main__":
    main()
