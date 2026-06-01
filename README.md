# 京东外卖定时优惠券抢券助手

基于 Playwright 浏览器自动化的桌面工具，在京东外卖（hour.jd.com）平台定时自动抢领优惠券。

## 功能

- 按 cron 表达式定时触发，精确到分钟
- Playwright 控制 Edge 浏览器模拟真实用户操作，内置反检测
- Cookie 加密存储，支持浏览器扫码自动续期
- 内置 Web 管理界面（Flask），在线配置、启停任务、查看日志与结果
- 系统托盘图标，后台静默运行，无终端窗口

## 系统要求

- Windows 10 或更高版本
- Microsoft Edge 浏览器（Windows 默认自带）
- Python 3.10+（源码运行）或直接使用打包好的 exe

## 快速开始

### 方式一：使用打包好的 exe（推荐）

1. 从 [Releases](../../releases) 下载最新版 exe
2. 双击运行，系统托盘出现图标，浏览器自动打开 `http://localhost:5000`
3. 在「配置管理」Tab 填写配置，点击「启动任务」

### 方式二：源码运行

```bash
# 安装依赖
pip install -r requirements.txt
playwright install msedge

# 启动
python main.py
```

## 配置

复制 `config.example.yaml` 为 `config.yaml` 并填写：

| 字段 | 说明 |
|------|------|
| `credential.cookie` | 京东 Cookie，留空则启动时弹出浏览器扫码 |
| `schedule` | cron 触发时间列表，建议开抢前 1 分钟，如 `29 10 * * *` |
| `coupon_targets[].url` | 优惠券活动页面 URL |
| `jd_area` | 京东收货地址编码，影响可见券范围 |
| `headless` | `false`=弹出浏览器窗口，`true`=后台静默 |
| `grab_interval_ms` | 抢券刷新间隔（毫秒），建议 100~2000 |

也可以直接在 Web 界面配置，无需手动编辑文件。

## 抢券逻辑

触发时间点 T（如配置 `29 10 * * *`，T = 10:29）：

- **T:30** — 打开活动页面预备
- **T:50** — 预热刷新一次（±1s 随机）
- **T:55** — 开始高频刷新轮询
- 发现「立即抢券」按钮 → 1 秒内随机间隔连点 3 次
- **T+1:20** — 停止轮询

## 常用命令

```bash
# 独立登录工具（重新获取 Cookie）
python login.py

# 临时测试（立即执行一次，跳过时间窗口）
python worker.py --once

# 打包 exe
打包.bat
```

## 安全说明

- Cookie 使用 Fernet（AES-128-CBC + HMAC）加密存储，密钥独立文件
- Web 界面默认只监听 `127.0.0.1`，不对外暴露
- 可通过 `WEB_PASSWORD` 环境变量启用 Basic Auth（仅 `web_app.py`）

## 项目结构

```
src/
├── auth_manager.py      # Cookie 加密管理
├── config_loader.py     # 配置加载与校验
├── coupon_crawler.py    # Playwright 浏览器自动化
├── task_runner.py       # 任务编排器
├── scheduler.py         # APScheduler 封装（cron 校验）
├── logger_setup.py      # 日志初始化
├── models.py            # Pydantic 数据模型
└── web/                 # Flask Web 管理界面
```

详细文档见 [CODE_WIKI.md](CODE_WIKI.md)。

## License

MIT
