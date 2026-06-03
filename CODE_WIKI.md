# 京东外卖定时优惠券抢券助手 — Code Wiki

## 一、项目概述

**项目名称**：京东外卖定时优惠券抢券助手  
**版本**：v1.0.17  
**项目定位**：一个基于 Playwright 浏览器自动化的桌面工具，用于在京东外卖（hour.jd.com）平台定时自动抢领优惠券。  
**核心能力**：

- 按 cron 表达式定时触发领券任务
- 使用 Playwright 控制 Edge 浏览器模拟真实用户操作
- Cookie 加密存储，支持浏览器中扫码自动续期
- 内置 Web 管理界面（Flask），可通过浏览器远程管理
- 支持系统托盘图标，后台静默运行
- 支持历史领券记录查询

---

## 二、项目目录结构

```
jd-coupon-auto-claim/
├── main.py                  # 主入口（系统托盘 + Web 服务）
├── web_app.py               # Web 管理界面独立入口
├── worker.py                # 抢券工作进程入口
├── login.py                 # 京东登录工具（获取 Cookie）
├── config.yaml              # 配置文件（YAML 格式）
├── build.spec               # PyInstaller 打包配置
├── requirements.txt         # Python 依赖清单
├── .gitignore               # Git 忽略规则
├── 启动.bat                 # Windows 启动脚本
├── 直接抢券.bat             # Windows 快捷启动（带浏览器界面）
├── 打包.bat                 # Windows 打包脚本（自动递增版本号）
│
├── src/                     # 核心业务逻辑包
│   ├── __init__.py
│   ├── version.py           # 版本号管理
│   ├── models.py            # Pydantic 数据模型 + 运行时数据类
│   ├── config_loader.py     # 配置加载与校验
│   ├── auth_manager.py      # 登录凭证管理（加密存储/读取）
│   ├── coupon_crawler.py    # 领券执行器（Playwright 浏览器自动化）
│   ├── task_runner.py       # 任务编排器
│   ├── scheduler.py         # 定时调度器（APScheduler 封装）
│   ├── logger_setup.py      # 日志初始化
│   │
│   └── web/                 # Web 管理界面包
│       ├── __init__.py
│       ├── app.py           # Flask 应用工厂
│       ├── auth_middleware.py  # Basic Auth 中间件
│       ├── config_api.py    # 配置管理 API
│       ├── scheduler_controller.py  # 调度器控制器（子进程管理）
│       ├── log_reader.py    # 日志读取 API
│       ├── result_api.py    # 领券结果 API
│       └── result_writer.py # 领券结果写入器
│
├── static/                  # 前端静态文件
│   ├── index.html           # 管理界面 HTML
│   ├── style.css            # 样式表
│   ├── app.js               # 前端 JavaScript 逻辑
│   ├── logo.ico             # 应用图标
│   ├── logo.png
│   └── logo.jpg
│
├── data/                    # 运行时数据目录
│   ├── credentials.enc      # 加密存储的 Cookie
│   ├── fernet.key           # Fernet 加密密钥
│   └── last_result.json     # 最近领券结果
│
├── logs/                    # 日志目录
│   └── app.log
│
└── dist/                    # 打包输出目录
    ├── config.yaml
    ├── 使用说明.txt
    └── 京东外卖定时优惠券抢券助手_v1.0.17.exe
```

---

## 三、整体架构

### 3.1 架构分层

```
┌──────────────────────────────────────────────────────────┐
│                      用户交互层                            │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │ 系统托盘图标  │  │ Web 管理界面  │  │ 命令行/批处理  │  │
│  │ (pystray)    │  │ (Flask + JS) │  │ (.bat脚本)    │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
├─────────┼─────────────────┼─────────────────┼───────────┤
│         └────────┬────────┘                 │           │
│                  ▼                          │           │
│  ┌──────────────────────────────┐           │           │
│  │       Web API 层             │           │           │
│  │  ┌────────┐┌───────┐┌─────┐ │           │           │
│  │  │配置API ││调度API││日志 │ │           │           │
│  │  │结果API ││版本API││API  │ │           │           │
│  │  └───┬────┘└──┬────┘└──┬──┘ │           │           │
│  └──────┼────────┼────────┼────┘           │           │
├─────────┼────────┼────────┼────────────────┼───────────┤
│         │        │        │                │           │
│         ▼        ▼        ▼                ▼           │
│  ┌──────────────────────────────────────────────────┐  │
│  │                 业务逻辑层                         │  │
│  │  ┌──────────┐ ┌─────────────┐ ┌──────────────┐  │  │
│  │  │ 配置加载  │ │ 凭证管理    │ │ 任务编排器   │  │  │
│  │  │ConfigLoad│ │CredentialMgr│ │TaskRunner    │  │  │
│  │  └────┬─────┘ └──────┬──────┘ └──────┬───────┘  │  │
│  │       │              │               │          │  │
│  │  ┌────▼──────────────▼───────────────▼───────┐  │  │
│  │  │          领券执行器 (CouponCrawler)        │  │  │
│  │  │         Playwright 浏览器自动化            │  │  │
│  │  └───────────────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────┘  │
├───────────────────────────────────────────────────────┤
│                     基础设施层                          │
│  ┌──────────┐ ┌────────┐ ┌──────────┐  │
│  │ 日志系统  │ │ 数据模型│ │ 定时调度 │  │
│  │LoggerSet.│ │ Models │ │Scheduler │  │
│  └──────────┘ └────────┘ └──────────┘  │
└───────────────────────────────────────────────────────┘
```

### 3.2 进程模型

项目采用**双进程架构**：

| 进程 | 职责 | 关键技术 |
|------|------|----------|
| **主进程** (`main.py`) | 系统托盘 + Flask Web 服务 | pystray, waitress |
| **工作进程** (`worker.py`) | Playwright 浏览器控制 + 定时调度循环 | Playwright, subprocess |

**通信方式**：主进程通过 `subprocess.Popen` 启动工作进程，通过 `.stop_worker` 标志文件和子进程 stdout 管道通信。

### 3.3 完整运行流程

**启动阶段**

1. 双击 exe，`main.py` 主进程启动
2. 后台线程启动 Flask + Waitress Web 服务（端口 5000）
3. 系统托盘图标出现，自动打开浏览器访问管理界面

**启动任务**

1. 用户点「启动任务」
2. `SchedulerController` 通过 `subprocess.Popen` 启动 `worker.py` 子进程
3. worker 加载配置、初始化 `AuthManager`、`CouponCrawler`
4. worker 自动查找 Edge 安装路径（兼容系统级和用户级安装），启动浏览器
5. 注入反检测脚本（覆盖 `navigator.webdriver`）和模拟移动端 User-Agent
6. 注入登录凭证，打开活动页面预热，等待 `.coupon-button-section` 元素出现
7. 若检测到跳转登录页，等用户扫码（最多 5 分钟），登录后自动提取并加密保存凭证
8. 浏览器就绪，worker 进入主循环每秒检测 cron 触发时间

**到点抢券**（以 `29 10 * * *` 触发，T = 10:29 为例）

| 时间 | 动作 |
|------|------|
| T:00 ~ T:30 | 等待阶段，每 5 秒检测一次 |
| T:30 | `page.goto()` 打开活动页面 |
| T:49~51（随机，仅随机一次） | `page.reload()` 预热刷新，让数据提前加载 |
| T:55 | 开始正式轮询 |
| 每轮循环 | `page.reload(wait_until="commit")` → 监听 `hours_home_pub` 接口响应（超时 1500ms） → 等待 `grab_interval_ms` |
| 每轮检测 | 检测登录跳转；检测「销售火爆」风控（连续 8 次才判定可能为风控暂时终止）；切换「正在抢券中」tab；扫描按钮文字 |
| 发现「立即抢券」/「立即领取」 | 随机间隔（200~500ms）连点 3 次 |
| T+0:06 起 | 「已领取」→ 成功；「已抢光/已售罄/库存不足」→ 失败 |
| 每轮耗时不足 1.3~1.6s | 补足等待（随机） |
| T+1:20 | 停止轮询，结果写入 `data/last_result.json` |

**停止任务**

1. 用户点「停止任务」或托盘「退出」
2. 主进程写入 `data/.stop_worker` 标志文件
3. worker 主循环每秒检测该文件，检测到后删除文件并跳出循环
4. `crawler.close()`：先 `goto("about:blank")` 再关闭 context 和 browser（先跳空白页避免 Edge 崩溃恢复弹窗）
5. 主进程等待 worker 退出（最多 10 秒），超时则强制 kill
6. 主进程 `os._exit(0)` 终止

**测试效果**

点「测试效果」，启动临时 worker 子进程（`--once` 参数），`force=True` 跳过时间窗口，最多刷新 20 次后自动退出，不影响正在运行的调度器。

---

## 四、核心模块详解

### 4.1 入口模块

#### 4.1.1 `main.py` — 主入口

| 函数 | 职责 |
|------|------|
| `main()` | 解析命令行参数，分发到 worker 模式或托盤模式 |
| `_start_web_server()` | 后台线程启动 Flask Web 服务（waitress） |
| `_run_tray()` | 启动 pystray 系统托盘图标，含"打开管理界面"和"退出"菜单 |

**启动模式**：

```bash
python main.py                          # 默认：系统托盘 + Web 界面
python main.py --port 8080              # 指定 Web 端口
python main.py --config my_config.yaml  # 指定配置文件
python main.py --worker ...             # 内部用，由 Web 界面启动工作进程
```

#### 4.1.2 `worker.py` — 工作进程

工作进程是独立子进程，核心逻辑在主线程中轮询。

| 函数 | 职责 |
|------|------|
| `_parse_cron_minutes()` | 从 cron 表达式提取分钟数 |
| `_should_trigger()` | 检查当前时间是否应触发任务（按分钟匹配，防重复） |
| `main()` | 工作进程主逻辑：加载配置 → 初始化 CredentialManager → 启动浏览器 → 轮询调度 |

**执行模式**：

- `--once`：立即执行一次后退出（测试用）
- `--run-now`：立即执行一次后继续等待调度
- 默认：等待 cron 时间点触发

#### 4.1.3 `login.py` — 登录工具

独立的登录辅助脚本，打开 Edge 浏览器让用户手动扫码登录京东，自动提取 Cookie 并保存到 `config.yaml`。

#### 4.1.4 `web_app.py` — Web 独立入口

独立启动 Web 管理界面（无系统托盘），通过环境变量 `WEB_PORT` 和 `CONFIG_PATH` 配置。

---

### 4.2 数据模型层 `src/models.py`

#### Pydantic 配置模型

| 模型类 | 用途 | 关键字段 |
|--------|------|----------|
| `CredentialConfig` | 京东账号凭证 | `cookie: str` |
| `CouponTargetConfig` | 优惠券活动目标 | `url: str`, `name: str` |
| `LogConfig` | 日志配置 | `path`, `max_bytes`, `backup_count` |
| `AppConfig` | 应用全局配置 | `credential`, `schedule`, `coupon_targets`, `log`, `request_timeout`, `jd_area`, `headless`, `grab_interval_ms` |

#### 运行时数据模型

| 类/枚举 | 用途 | 关键字段 |
|---------|------|----------|
| `ClaimStatus` (Enum) | 领券状态 | `SUCCESS`, `FAILED`, `SKIPPED` |
| `FailReason` (Enum) | 失败原因 | `ALREADY_CLAIMED`, `NOT_STARTED`, `OUT_OF_STOCK`, `LOGIN_EXPIRED`, `HTTP_ERROR`, `UNKNOWN` |
| `CouponInfo` (dataclass) | 优惠券信息 | `coupon_id`, `name`, `denomination`, `min_spend`, `claim_url` |
| `ClaimResult` (dataclass) | 领取结果 | `coupon_info`, `status`, `fail_reason`, `claimed_at` |

---

### 4.3 配置加载层 `src/config_loader.py`

#### `ConfigLoader` 类

| 方法 | 职责 | 关键逻辑 |
|------|------|----------|
| `load(path)` | 加载并校验配置文件 | 自动检测 YAML/JSON 格式，Pydantic 校验 |
| `_detect_format(path)` | 检测文件格式 | 扩展名判断：`.yaml/.yml` → yaml，`.json` → json |
| `_validate(raw)` | 校验配置字典 | 捕获 `ValidationError` 并转换为 `ConfigValidationError` |

**自定义异常**：

| 异常类 | 触发条件 |
|--------|----------|
| `ConfigValidationError` | 配置校验失败，包含字段名和原因 |

---

### 4.4 凭证管理层 `src/auth_manager.py`

#### `CredentialManager` 类

**加密方案**：使用 `cryptography.fernet.Fernet`（AES-128-CBC + HMAC）对称加密。

| 方法 | 职责 | 关键逻辑 |
|------|------|----------|
| `_load_or_create_key()` | 加载或创建 Fernet 密钥 | 密钥文件不存在时自动生成 |
| `_encrypt(plaintext)` | 加密字符串 | Fernet 加密 |
| `_decrypt(ciphertext)` | 解密字节 | Fernet 解密 |
| `initialize()` | 初始化凭证存储 | 优先使用 config.yaml 中的凭证覆盖加密存储 |
| `get_headers()` | 返回含登录凭证的请求头 | 从加密文件解密凭证 |
| `update_credential(session_cookie)` | 更新登录凭证 | 浏览器扫码登录后回调，覆盖加密存储 |
| `mark_invalid()` | 标记登录失效 | 设置 `_valid = False` |
| `is_valid()` | 检查登录有效性 | 返回 `_valid` |

**自定义异常**：

| 异常类 | 触发条件 |
|--------|----------|
| `LoginExpiredError` | 登录过期或未登录 |
| `KeyFileNotFoundError` | Fernet 密钥文件丢失 |

---

### 4.5 领券执行器 `src/coupon_crawler.py`

#### `CouponCrawler` 类

核心自动化组件，使用 Playwright 控制 Microsoft Edge 浏览器。

| 方法 | 职责 | 关键逻辑 |
|------|------|----------|
| `set_session_cookie(session_cookie)` | 注入登录凭证 | 设置内部 `_session_cookie` 属性 |
| `_parse_cookies()` | 解析 Cookie 字符串 | 将 `key=value;` 格式转为 Playwright cookie 对象 |
| `_ensure_browser()` | 确保浏览器已启动 | 检测浏览器是否存活，自动重启；注入反检测脚本 |
| `_wait_for_login_if_needed()` | 检测并等待登录 | 检测登录页域名，等待用户手动扫码，自动提取新 Cookie |
| `_extract_cookie_from_browser()` | 从浏览器提取 Cookie | 从 Playwright context 获取所有 `.jd.com` Cookie |
| `warmup()` | 浏览器预热 | 兼容接口，实际在 `run()` 中延迟启动 |
| `close()` | 关闭浏览器 | 先导航到 `about:blank`，避免 Edge 崩溃恢复弹窗 |
| `run(force)` | 执行领券流程 | 确保浏览器存活 → 调用 `_grab_coupons()` |
| `_grab_coupons(page, force)` | 轮询刷新抢券 | **核心领券逻辑**，见下方详述 |
| `_switch_to_ongoing_tab()` | 切换到"正在抢券中"tab | 点击抢券 tab |
| `_check_result()` | 检查领券结果 | 根据页面文本判断成功/失败/已领取 |
| `_close_popup()` | 关闭弹窗 | 点击关闭按钮 |

**抢券策略**（`_grab_coupons` 方法）：

```
触发时间点 T（如 10:29）
  │
  ├── T:00 ~ T:30    等待阶段
  ├── T:30 ~ T:55    预备阶段 ── 打开活动页面
  │     └── T:50     预热刷新（随机 ±1s）
  ├── T:55 ~ T+1:20  高频刷新轮询
  │     ├── 每轮检测"立即抢券"按钮 → 连点 3 次
  │     ├── 检测风控提示"销售火爆" → 终止
  │     ├── 切换到"正在抢券中"tab
  │     └── 检测"已领取"/"已抢光" → 返回结果
  └── T+1:20         停止轮询
```

**反检测措施**：

- 覆盖 `navigator.webdriver` 标志
- 设置移动端 User-Agent
- 注入 `window.chrome` 对象
- 设置真实浏览器请求头
- 随机刷新间隔（1300~1600ms）

**自定义异常**：

| 异常类 | 说明 |
|--------|------|
| `CrawlerError` | 领券执行器基础异常 |
| `CrawlerTimeoutError` | 操作超时异常 |

---

### 4.6 任务编排器 `src/task_runner.py`

#### `TaskRunner` 类

| 方法 | 职责 | 执行步骤 |
|------|------|----------|
| `run(force)` | 执行一次完整领券任务 | ① 检查凭证有效性 → ② 注入 Cookie → ③ 执行领券 → ④ 写入结果 → ⑤ 记录完成日志 |

---

### 4.7 定时调度器 `src/scheduler.py`

#### `Scheduler` 类

封装 APScheduler，支持两种运行模式。

| 方法 | 职责 | 关键逻辑 |
|------|------|----------|
| `_register_jobs()` | 注册 cron 任务 | 遍历 schedule 列表，每个 cron 注册一个 Job |
| `start()` | 启动调度器 | blocking 模式阻塞主线程，background 模式立即返回 |
| `stop()` | 停止调度器 | shutdown(wait=True) |
| `get_job_count()` | 获取任务数量 | 返回注册的 Job 数 |

**配置参数**：

- `misfire_grace_time`: 60s（错过任务后的宽限期）
- `coalesce`: True（合并多次错过）
- `max_instances`: 1（不允许并发）

---

### 4.8 Web 层 `src/web/`

#### 4.8.1 `app.py` — Flask 应用工厂

| 函数 | 职责 |
|------|------|
| `create_app(config_path)` | 创建 Flask 应用，注册蓝图、中间件、静态路由、版本 API |

**注册的蓝图**：

| 蓝图 | 路由前缀 | 功能 |
|------|----------|------|
| `config_bp` | `/api/config` | 配置读取/保存 |
| `scheduler_bp` | `/api/scheduler/status`, `/api/scheduler/start`, `/api/scheduler/stop`, `/api/scheduler/run-now` | 调度器控制 |
| `log_bp` | `/api/logs` | 日志读取/清空 |
| `result_bp` | `/api/result` | 领券结果查询 |

**静态路由**：

| 路由 | 说明 |
|------|------|
| `GET /` | 返回 `index.html` |
| `GET /static/<path>` | 静态文件 |
| `GET /api/version` | 返回版本号 `{"version": "1.0.17"}` |

#### 4.8.2 `auth_middleware.py` — Basic Auth 中间件

| 函数 | 职责 |
|------|------|
| `check_auth(password, auth_header)` | 常量时间比较验证 Basic Auth（用户名任意，只校验密码） |
| `require_auth()` | Flask before_request 钩子，校验认证，静态资源和主页放行 |
| `init_auth(app)` | 注册认证钩子到应用 |

#### 4.8.3 `config_api.py` — 配置管理 API

| 辅助函数 | 职责 |
|----------|------|
| `validate_cron(cron)` | 校验 cron 表达式合法性 |
| `validate_url(url)` | 校验 URL 格式（http/https） |
| `atomic_write_yaml(path, data)` | 原子写入 YAML（先写临时文件，再 `os.replace`） |

**API 端点**：

| 方法 | 路由 | 功能 |
|------|------|------|
| GET | `/api/config` | 读取配置（不含 credential，由 CredentialManager 独立管理） |
| POST | `/api/config` | 保存配置（校验 cron/URL，credential.cookie 始终保持为空） |

#### 4.8.4 `scheduler_controller.py` — 调度器控制器

**关键设计**：工作进程在独立子进程中运行，避免 Playwright 的 greenlet 跨线程限制。

| 方法 | 职责 |
|------|------|
| `start(config_path)` | 启动子进程运行 worker.py |
| `stop()` | 写 `.stop_worker` 标志文件优雅停止 → 超时强杀 |
| `run_now(config_path)` | 启动临时子进程执行一次（--once 模式） |
| `get_status()` | 返回运行状态 `{"running": bool, ...}` |
| `is_running()` | 检查子进程是否在运行 |
| `_pipe_output(proc)` | 后台线程将子进程 stdout 转发到日志 |

**API 端点**：

| 方法 | 路由 | 功能 |
|------|------|------|
| GET | `/api/scheduler/status` | 获取调度器状态 |
| POST | `/api/scheduler/start` | 启动调度器 |
| POST | `/api/scheduler/stop` | 停止调度器 |
| POST | `/api/scheduler/run-now` | 立即执行一次 |

#### 4.8.5 `log_reader.py` — 日志读取器

| 函数 | 职责 |
|------|------|
| `read_last_lines(path, n)` | 高效反向扫描读取日志文件最后 N 行 |
| `clear_log(path)` | 清空日志文件 |

**API 端点**：

| 方法 | 路由 | 功能 |
|------|------|------|
| GET | `/api/logs?lines=N` | 读取最新 N 行日志 |
| DELETE | `/api/logs` | 清空日志 |

#### 4.8.6 `result_api.py` — 领券结果 API

| 方法 | 路由 | 功能 |
|------|------|------|
| GET | `/api/result` | 读取最近领券结果及历史（支持 schema 版本兼容） |

#### 4.8.7 `result_writer.py` — 结果写入器

| 函数 | 职责 |
|------|------|
| `write_result(results, task_time, path)` | 将领券结果原子写入 JSON 文件，保留最多 50 条历史 |

---

### 4.9 日志系统 `src/logger_setup.py`

#### `setup_logger(config, name)` 函数

- 日志级别：`INFO`
- 输出目标：滚动文件（`RotatingFileHandler`）+ 控制台（`StreamHandler`）
- 日志格式：`%(asctime)s [%(levelname)s] %(name)s: %(message)s`
- 默认配置：单文件最大 10MB，保留 7 个备份

---

### 4.10 前端静态文件

#### `static/index.html`

Web 管理界面，包含两个 Tab：

1. **任务控制 Tab**：调度器状态指示、启动/停止按钮、"测试效果"按钮、运行日志面板、领券结果展示
2. **配置管理 Tab**：Cron 时间列表（两列网格）、活动 URL 列表、JD Area 编码、浏览器模式开关、刷新间隔、闲时找券开关（含时间段配置）、QQ 邮箱通知配置、保存按钮

#### `static/app.js`

前端核心逻辑：

| 函数 | 职责 |
|------|------|
| `switchTab(name)` | Tab 切换 |
| `loadVersion()` | 加载版本号 |
| `loadConfig()` | 加载配置填充表单 |
| `saveConfig()` | 收集表单数据 POST 保存 |
| `pollStatus()` / `fetchStatus()` | 轮询调度器状态（每 5 秒） |
| `startScheduler()` / `stopScheduler()` | 启停调度器 |
| `runNow()` | 立即执行一次 |
| `loadLogs()` / `renderLogs()` | 加载并渲染日志 |
| `pollLogs()` | 轮询日志（每 3 秒） |
| `clearLogs()` | 清空日志 |
| `loadResult()` / `renderResult()` | 加载并渲染领券结果（含历史记录） |
| `_updateIdleTimeRangeVisibility()` | 闲时找券开关联动显示/隐藏时间段 |
| `_updateEmailNotifyVisibility()` | 邮件通知开关联动显示/隐藏配置区 |

---

## 五、配置说明 (`config.yaml`)

```yaml
schedule:
  - '29 10 * * *'   # 每天 10:29 开始抢
  - '29 11 * * *'
  - '29 16 * * *'
  - '29 17 * * *'
coupon_targets:
  - name: 京东外卖百补好运券
    url: https://hour.jd.com/...
jd_area: '17_1381_50713_62969'
headless: false
grab_interval_ms: 200
idle_check_enabled: false       # 闲时找券开关
idle_check_start_hour: 10       # 巡检开始小时
idle_check_end_hour: 18         # 巡检结束小时
notify_email:                   # 可选，不填则不发通知
  qq: '123456789'
  auth_code: 'xxxxxxxxxxxx'     # QQ 邮箱授权码（非登录密码）
  receiver: ''                  # 留空则发给自己
```

**关键配置项说明**：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `coupon_targets` | 数组 | 必填 | 优惠券活动目标列表 |
| `schedule` | 数组 | 必填 | cron 表达式列表 |
| `headless` | 布尔 | false | 浏览器模式 |
| `jd_area` | 字符串 | 空 | 影响可见券范围 |
| `grab_interval_ms` | 整数 | 200 | 抢券刷新间隔（毫秒） |
| `request_timeout` | 元组 | (5, 15) | HTTP 超时（连接秒数, 读取秒数） |
| `idle_check_enabled` | 布尔 | false | 是否启用闲时找券 |
| `idle_check_start_hour` | 整数 | 10 | 闲时巡检开始小时（0~23） |
| `idle_check_end_hour` | 整数 | 18 | 闲时巡检结束小时（0~23） |
| `notify_email.qq` | 字符串 | 空 | QQ 号（发件邮箱 = QQ号@qq.com） |
| `notify_email.auth_code` | 字符串 | 空 | QQ 邮箱授权码 |
| `notify_email.receiver` | 字符串 | 空 | 收件人邮箱，留空则发给自己 |

---

## 六、数据流

### 6.1 配置加载流

```
config.yaml / config.json
    │
    ▼
ConfigLoader.load()
    │
    ├── _detect_format() → 判定 YAML / JSON
    ├── 解析文件 → raw dict
    └── _validate() → Pydantic AppConfig
                           │
                           ▼
                   CredentialManager / CouponCrawler / Scheduler
```

### 6.2 领券任务执行流

```
定时触发 / 手动触发 (--once / --run-now)
    │
    ▼
TaskRunner.run()
    │
    ├── ① CredentialManager.is_valid() → 检查登录有效性
    ├── ② CredentialManager.get_headers() → 获取登录凭证
    ├── ③ CouponCrawler.set_session_cookie() → 注入登录凭证
    ├── ④ CouponCrawler.run(force) → 执行领券
    │       │
    │       ├── _ensure_browser() → 预热浏览器
    │       └── _grab_coupons() → 轮询抢券（T:55 ~ T+1:20）
    │               │
    │               ├── 刷新页面 → 扫描按钮 → 点击
    │               ├── 检测风控 / 登录过期
    │               └── 返回 ClaimResult[]
    │
    ├── ⑤ result_writer.write_result() → 写入 last_result.json
    ├── ⑥ email_notifier.send_result_email() → 发送 QQ 邮箱通知（若已配置）
    └── ⑦ 记录完成日志
```

### 6.4 闲时找券流

```
worker.py 主循环（每秒检测）
    │
    ├── 未到节拍时间 → 跳过
    ├── 不在时间段内（start_hour:01 ~ end_hour:56）→ 跳过，等下一节拍
    ├── 处于定点抢券忙时窗口（触发分钟:25 ~ 开抢分钟:25）→ 60s 后重判
    └── 正常 → CouponCrawler.idle_check()
                │
                ├── 浏览器未启动 → 直接返回（不重新弹出）
                ├── page.reload() → 等待接口响应
                ├── 扫描 .coupon-button-section
                ├── 发现「立即抢券」→ 连点 3 次，记录日志
                └── 无按钮 → 静默返回，等待下一节拍
```

### 6.3 Web API 请求流

```
浏览器 (index.html)
    │
    ├── GET/POST /api/config → ConfigAPI → config.yaml
    ├── GET/POST /api/scheduler/* → SchedulerController → subprocess worker.py
    ├── GET/DELETE /api/logs → LogReader → logs/app.log
    ├── GET /api/result → ResultAPI → data/last_result.json
    └── GET /api/version → 返回版本号
```

---

## 七、安全设计

| 安全措施 | 实现方式 |
|----------|----------|
| Cookie 加密存储 | Fernet (AES-128-CBC + HMAC)，密钥存独立文件，不通过 config.yaml 传递 |
| 密钥自动生成 | 首次运行时自动生成 `fernet.key` |
| 凭证失效标记 | 内部 `_valid` 标志，失效后拒绝使用 |
| 日志脱敏 | Cookie 等敏感信息不记录到日志 |
| Web 界面认证 | Basic Auth，密码通过环境变量 `WEB_PASSWORD` 设置 |
| 常量时间比较 | 使用 `hmac.compare_digest` 防时序攻击 |
| 原子文件写入 | `os.replace` 原子替换，防写入中断损坏 |
| 无数据外传 | 程序不向任何第三方服务器发送数据，所有操作在本机浏览器中执行 |

---

## 八、依赖关系

### Python 依赖 (`requirements.txt`)

| 包名 | 版本 | 用途 |
|------|------|------|
| `flask` | >=3.0.0 | Web 框架 |
| `waitress` | >=3.0.0 | 生产级 WSGI 服务器 |
| `playwright` | >=1.44.0 | 浏览器自动化 |
| `apscheduler` | ==3.10.4 | 定时任务调度 |
| `pydantic` | >=2.7.0 | 配置数据校验 |
| `pyyaml` | >=6.0.0 | YAML 配置解析 |
| `cryptography` | >=42.0.0 | Fernet 加密 |
| `requests` | >=2.32.0 | HTTP 请求 |
| `pystray` | (隐式依赖) | 系统托盘图标 |
| `Pillow` | (隐式依赖) | 托盘图标生成 |

### 模块依赖图

```
main.py
  ├── src.web.app (Flask app)
  │     ├── src.web.auth_middleware
  │     ├── src.web.config_api → src.config_loader
  │     ├── src.web.scheduler_controller → subprocess → worker.py
  │     ├── src.web.log_reader
  │     ├── src.web.result_api → data/last_result.json
  │     └── src.version
  └── pystray (系统托盘)

worker.py
  ├── src.config_loader → src.models
  ├── src.auth_manager → src.models
  ├── src.coupon_crawler → src.models
  ├── src.task_runner
  │     ├── src.auth_manager
  │     ├── src.coupon_crawler
  │     ├── src.email_notifier → src.models
  │     └── src.web.result_writer → src.models
  └── src.logger_setup → src.models

login.py
  ├── playwright.sync_api
  ├── yaml
  └── src.models (间接)
```

---

## 九、运行方式

### 9.1 开发环境运行

**第一步：安装依赖**

```bash
pip install -r requirements.txt
playwright install msedge
```

**第二步：获取 Cookie**

```bash
# 打开浏览器手动登录京东，自动保存 Cookie
python login.py
```

**第三步：启动应用**

```bash
# 方式一：托盘 + Web 界面（推荐）
python main.py

# 方式二：仅 Web 界面（无托盘）
python web_app.py

# 方式三：直接启动抢券（带浏览器窗口）
python worker.py
```

### 9.2 Windows 快捷方式

| 脚本 | 用途 |
|------|------|
| `启动.bat` | 启动管理界面（优先运行 exe，否则运行 `python main.py`） |
| `直接抢券.bat` | 直接启动抢券进程（不开管理界面） |
| `打包.bat` | 自动递增版本号 → PyInstaller 打包 → 清理敏感文件 |

### 9.3 生产环境（打包后）

1. 运行 `打包.bat` 生成 `.exe` 文件到 `dist/` 目录
2. 分发 `dist/` 目录给最终用户
3. 用户双击 `京东外卖定时优惠券抢券助手_v1.0.17.exe` 即可运行
4. 首次运行需在 Web 界面配置 Cookie 或使用 `login.py`

### 9.4 命令行参数

| 入口 | 参数 | 说明 |
|------|------|------|
| `main.py` | `--config` | 指定配置文件路径 |
| `main.py` | `--port` | 指定 Web 端口（默认 5000） |
| `main.py` | `--worker` | 工作进程模式（内部使用） |
| `worker.py` | `--once` | 立即执行一次后退出 |
| `worker.py` | `--run-now` | 立即执行一次后继续等待调度 |
| `web_app.py` | `WEB_PORT` 环境变量 | Web 端口（默认 8080） |

---

## 十、打包部署

### `build.spec` (PyInstaller)

```
输入: main.py + worker.py
输出: 京东外卖定时优惠券抢券助手_v{version}.exe
图标: static/logo.ico
模式: 无控制台窗口 (console=False)
数据文件: static/ → static/
排除项: Anaconda 大型包 (numpy, pandas, matplotlib, IPython, jupyter 等)
隐藏导入: waitress, flask, apscheduler, cryptography, playwright, pystray, PIL 等
```

### `打包.bat` 流程

```
① 自动递增 src/version.py 补丁版本号
② 杀掉残留进程
③ 清理 build/ 和 dist/ 旧文件
④ pyinstaller build.spec --clean --noconfirm
⑤ 清理 dist/ 中的敏感文件 (data/, logs/)
⑥ 复制并清理 dist/config.yaml（清空 Cookie）
```

---

## 十一、测试

项目包含 `tests/` 包结构，但未提供具体测试用例。依赖清单中包含测试工具：

| 包 | 用途 |
|----|------|
| `pytest` | 测试框架 |
| `pytest-cov` | 覆盖率报告 |
| `hypothesis` | 属性基测试 |
| `responses` | HTTP 请求模拟 |

---

## 十二、版本历史

| 版本 | 说明 |
|------|------|
| 1.0.0 | 初始发布版本 |
| 1.0.17 | 新增闲时找券、QQ 邮箱通知；抢券结束时间改为开抢分钟 :20 |