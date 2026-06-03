/**
 * 京东外卖券自动领取 - 管理界面前端逻辑
 */

// ===== 应用状态 =====
const state = {
  schedulerRunning: false,
  logLines: [],
  lastLogCount: 0,
  logAutoScroll: true,  // 日志是否自动滚动到底部
};

// ===== Tab 切换 =====

function switchTab(name) {
  document.querySelectorAll('.tab-panel').forEach(p => p.style.display = 'none');
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + name).style.display = 'block';
  event.currentTarget.classList.add('active');
}

// ===== 页面加载 =====
document.addEventListener('DOMContentLoaded', () => {
  loadVersion();
  loadConfig();
  loadResult();
  loadLogs();
  pollStatus();
  pollLogs();
});

// ===== 版本号 =====
async function loadVersion() {
  try {
    const resp = await fetch('/api/version');
    if (!resp.ok) return;
    const data = await resp.json();
    const el = document.getElementById('app-version');
    if (el && data.version) {
      el.textContent = `v${data.version}`;
    }
  } catch (_) {
    // 版本号加载失败不影响主功能
  }
}

// ===== 配置管理 =====

/**
 * 从 GET /api/config 加载配置并填充表单
 */
async function loadConfig() {
  try {
    const resp = await fetch('/api/config');
    if (!resp.ok) {
      showToast('加载配置失败', 'error');
      return;
    }
    const data = await resp.json();

    // Cron 列表
    const cronList = document.getElementById('cron-list');
    cronList.innerHTML = '';
    const schedules = data.schedule || [];
    if (schedules.length === 0) {
      addCronRow('');
    } else {
      schedules.forEach(cron => addCronRow(cron));
    }

    // 活动 URL 列表
    document.getElementById('target-url-col').innerHTML  = '';
    document.getElementById('target-name-col').innerHTML = '';
    const targets = data.coupon_targets || [];
    if (targets.length === 0) {
      addTargetRow('', '');
    } else {
      targets.forEach(t => addTargetRow(t.url || '', t.name || ''));
    }

    // 推送服务（保留字段兼容旧配置，不在界面展示）
    // const notifier = data.notifier || {};

    // jd_area
    document.getElementById('jd-area').value = data.jd_area || '';

    // headless：True 表示后台静默，对应开关应为未勾选；
    // False（默认）表示弹出窗口，对应开关应勾选
    const headlessToggle = document.getElementById('headless-toggle');
    // headless=false 时弹出窗口， toggle 应为 checked
    headlessToggle.checked = data.headless === false || data.headless === undefined;

    // 刷新间隔
    document.getElementById('grab-interval').value = data.grab_interval_ms ?? 0;

    // 闲时找券开关
    const idleCheckToggle = document.getElementById('idle-check-toggle');
    idleCheckToggle.checked = data.idle_check_enabled === true;
    _updateIdleTimeRangeVisibility();

    // 闲时找券时间段
    _setTimePicker('idle-start-hour', data.idle_check_start_hour ?? 10);
    _setTimePicker('idle-end-hour',   data.idle_check_end_hour   ?? 18);

    // QQ 邮箱通知
    const emailCfg = data.notify_email;
    const emailToggle = document.getElementById('email-notify-toggle');
    const hasEmail = emailCfg && emailCfg.qq;
    emailToggle.checked = !!hasEmail;
    _updateEmailNotifyVisibility();
    if (emailCfg) {
      document.getElementById('email-qq').value           = emailCfg.qq       || '';
      document.getElementById('email-auth-code').value    = emailCfg.auth_code ? '••••••••' : '';
      document.getElementById('email-receiver').value     = emailCfg.receiver  || '';
    }

  } catch (err) {
    showToast('加载配置时发生错误', 'error');
    console.error('loadConfig error:', err);
  }
}

/**
 * 收集表单数据并 POST /api/config 保存
 */
async function saveConfig(event) {
  if (event) event.preventDefault();

  const saveBtn = document.getElementById('save-btn');
  saveBtn.disabled = true;
  saveBtn.textContent = '保存中...';

  try {
    // 收集触发时间列表（时间选择器 → cron 表达式）
    const cronRows = document.querySelectorAll('#cron-list .cron-row');
    const schedule = Array.from(cronRows).map(row => timeToCron(row));

    // 收集活动 URL 列表（URL 和名称分列存放，按顺序配对）
    const urlInputs  = document.querySelectorAll('#target-url-col .target-url');
    const nameInputs = document.querySelectorAll('#target-name-col .target-name');
    const coupon_targets = Array.from(urlInputs).map((urlEl, i) => ({
      url:  urlEl.value.trim(),
      name: nameInputs[i] ? nameInputs[i].value.trim() : '',
    })).filter(t => t.url !== '');

    // 推送服务（保留字段兼容旧配置，不在界面展示，保存时不覆盖）
    const jd_area = document.getElementById('jd-area').value.trim();

    // headless：开关勾选=弹出窗口（headless=false），未勾选=后台静默（headless=true）
    const headless = !document.getElementById('headless-toggle').checked;

    // 刷新间隔
    const grab_interval_ms = parseInt(document.getElementById('grab-interval').value) || 0;

    // 闲时找券开关
    const idle_check_enabled = document.getElementById('idle-check-toggle').checked;

    // 闲时找券时间段
    const idle_check_start_hour = parseInt(document.getElementById('idle-start-hour').dataset.value) || 10;
    const idle_check_end_hour   = parseInt(document.getElementById('idle-end-hour').dataset.value)   || 18;

    // QQ 邮箱通知
    const emailEnabled = document.getElementById('email-notify-toggle').checked;
    const emailQQ      = document.getElementById('email-qq').value.trim();
    const emailAuth    = document.getElementById('email-auth-code').value.trim();
    const emailRecv    = document.getElementById('email-receiver').value.trim();
    // auth_code 显示为掩码时不覆盖（保留服务端原值），用空字符串作为信号
    const notify_email = emailEnabled && emailQQ ? {
      qq: emailQQ,
      auth_code: emailAuth === '••••••••' ? '' : emailAuth,
      receiver: emailRecv,
    } : null;

    const payload = {
      credential: { cookie: '' },
      schedule,
      coupon_targets,
      jd_area,
      headless,
      grab_interval_ms,
      idle_check_enabled,
      idle_check_start_hour,
      idle_check_end_hour,
      notify_email,
    };

    const resp = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    const result = await resp.json();

    if (resp.ok) {
      showToast('保存成功', 'success');
    } else {
      showToast(result.message || '保存失败', 'error');
    }
  } catch (err) {
    showToast('保存配置时发生错误', 'error');
    console.error('saveConfig error:', err);
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = '保存配置';
  }
}

// ===== 调度器控制 =====

/**
 * 轮询调度器状态（每 5 秒）
 */
function pollStatus() {
  fetchStatus();
  setInterval(fetchStatus, 5000);
}

async function fetchStatus() {
  try {
    const resp = await fetch('/api/scheduler/status');
    if (!resp.ok) return;
    const data = await resp.json();
    updateStatusUI(data);
  } catch (err) {
    console.error('fetchStatus error:', err);
  }
}

function updateStatusUI(data) {
  const dot = document.getElementById('status-dot');
  const text = document.getElementById('status-text');
  const nextRunDiv = document.getElementById('next-run-times');
  const startBtn = document.getElementById('start-btn');
  const stopBtn = document.getElementById('stop-btn');

  state.schedulerRunning = data.running;

  if (data.running) {
    dot.className = 'status-indicator running';
    text.textContent = '运行中';
    startBtn.disabled = true;
    startBtn.style.opacity = '0.5';
    stopBtn.disabled = false;
    stopBtn.style.opacity = '1';
  } else {
    dot.className = 'status-indicator stopped';
    text.textContent = '已停止';
    startBtn.disabled = false;
    startBtn.style.opacity = '1';
    stopBtn.disabled = true;
    stopBtn.style.opacity = '0.5';
  }

  // 下次触发时间
  const times = data.next_run_times || [];
  if (times.length > 0) {
    nextRunDiv.innerHTML = '下次触发：' +
      times.map(t => `<span class="run-time-item">${t || '未知'}</span>`).join('');
  } else {
    nextRunDiv.innerHTML = '';
  }
}

/**
 * 启动调度器
 */
async function startScheduler() {
  const btn = document.getElementById('start-btn');
  btn.disabled = true;
  try {
    const resp = await fetch('/api/scheduler/start', { method: 'POST' });
    const data = await resp.json();
    if (resp.ok) {
      showToast(data.message || '任务已启动', 'success');
      await fetchStatus();
    } else {
      showToast(data.message || '启动失败', 'error');
    }
  } catch (err) {
    showToast('启动任务时发生错误', 'error');
    console.error('startScheduler error:', err);
  } finally {
    btn.disabled = false;
  }
}

/**
 * 停止调度器
 */
async function stopScheduler() {
  const btn = document.getElementById('stop-btn');
  btn.disabled = true;
  try {
    const resp = await fetch('/api/scheduler/stop', { method: 'POST' });
    const data = await resp.json();
    if (resp.ok) {
      showToast(data.message || '任务已停止', 'success');
      await fetchStatus();
      // 任务停止后主动拉一次最新日志，之后轮询不再更新
      await loadLogs();
    } else {
      showToast(data.message || '停止失败', 'error');
    }
  } catch (err) {
    showToast('停止任务时发生错误', 'error');
    console.error('stopScheduler error:', err);
  } finally {
    btn.disabled = false;
  }
}

/**
 * 立即执行一次任务
 */
async function runNow() {
  const btn = document.getElementById('run-now-btn');
  btn.disabled = true;
  btn.textContent = '测试中...';
  try {
    const resp = await fetch('/api/scheduler/run-now', { method: 'POST' });
    const data = await resp.json();
    if (resp.ok) {
      showToast(data.message || '任务已触发', 'info');
      setTimeout(() => loadResult(), 3000);
    } else {
      showToast(data.message || '触发失败', 'error');
    }
  } catch (err) {
    showToast('触发任务时发生错误', 'error');
    console.error('runNow error:', err);
  } finally {
    btn.disabled = false;
    btn.textContent = '测试效果';
  }
}

// ===== 日志 =====

/**
 * 加载日志并渲染
 */
async function loadLogs() {
  try {
    const resp = await fetch('/api/logs');
    if (!resp.ok) return;
    const data = await resp.json();
    const lines = data.lines || [];

    state.logLines = lines;
    state.lastLogCount = lines.length;

    renderLogs(lines);
  } catch (err) {
    console.error('loadLogs error:', err);
  }
}

/**
 * 将日志行渲染到 #log-content，并更新标题徽章
 * 若用户正在选中文字，或内容未发生变化，则跳过 DOM 更新以保护选区
 */
function renderLogs(lines) {
  const logEl = document.getElementById('log-content');

  if (!lines || lines.length === 0) {
    if (logEl.innerHTML !== '暂无日志') {
      logEl.innerHTML = '暂无日志';
    }
    _updateLogBadges(false, false);
    return;
  }

  const hasError   = lines.some(l => l.includes('ERROR'));
  const hasWarning = lines.some(l => l.includes('WARNING') || l.includes('WARN'));

  // 构建带颜色的 HTML
  const html = lines.map(line => {
    const escaped = escapeHtml(line);
    if (line.includes('ERROR')) {
      return `<span class="log-error">${escaped}</span>`;
    } else if (line.includes('WARNING') || line.includes('WARN')) {
      return `<span class="log-warning">${escaped}</span>`;
    }
    return escaped;
  }).join('\n');

  // 内容相同则不更新 DOM（避免破坏选区）
  if (logEl.innerHTML === html) {
    _updateLogBadges(hasWarning, hasError);
    return;
  }

  // 用户正在 log-content 内选中文字时，跳过本次更新
  const sel = window.getSelection();
  if (sel && sel.rangeCount > 0 && !sel.isCollapsed) {
    const range = sel.getRangeAt(0);
    if (logEl.contains(range.commonAncestorContainer)) {
      _updateLogBadges(hasWarning, hasError);
      return;
    }
  }

  logEl.innerHTML = html;
  _updateLogBadges(hasWarning, hasError);

  // 仅在自动滚动开启时滚动到底部
  if (state.logAutoScroll) {
    logEl.scrollTop = logEl.scrollHeight;
  }
}

/**
 * 更新日志标题区的警告/错误徽章
 */
function _updateLogBadges(hasWarning, hasError) {
  const warnBadge  = document.getElementById('log-warning-badge');
  const errorBadge = document.getElementById('log-error-badge');
  if (warnBadge)  warnBadge.style.display  = hasWarning ? '' : 'none';
  if (errorBadge) errorBadge.style.display = hasError   ? '' : 'none';
}

/**
 * 切换日志自动滚动状态
 */
function toggleLogScroll() {
  state.logAutoScroll = !state.logAutoScroll;
  const btn = document.getElementById('log-scroll-btn');
  if (state.logAutoScroll) {
    btn.textContent = '⏸ 暂停滚动';
    btn.classList.remove('btn-primary');
    btn.classList.add('btn-secondary');
    // 立即滚到底
    const logEl = document.getElementById('log-content');
    logEl.scrollTop = logEl.scrollHeight;
  } else {
    btn.textContent = '▶ 自动滚动';
    btn.classList.remove('btn-secondary');
    btn.classList.add('btn-primary');
  }
}

/**
 * 轮询日志（每 3 秒）
 * 仅在调度器运行中时才拉取新日志；停止后不再刷新
 */
function pollLogs() {
  setInterval(() => {
    if (state.schedulerRunning) {
      loadLogs();
    }
  }, 3000);
}

/**
 * 复制日志到剪贴板
 */
async function copyLogs() {
  const logEl = document.getElementById('log-content');
  const text = logEl.innerText || logEl.textContent || '';
  try {
    await navigator.clipboard.writeText(text);
    showToast('日志已复制', 'success');
  } catch (_) {
    // 降级：创建临时 textarea
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;opacity:0;';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showToast('日志已复制', 'success');
  }
}

/**
 * 清空日志
 */
async function clearLogs() {
  try {
    const resp = await fetch('/api/logs', { method: 'DELETE' });
    if (resp.ok) {
      state.logLines = [];
      state.lastLogCount = 0;
      document.getElementById('log-content').innerHTML = '暂无日志';
      showToast('日志已清空', 'success');
    } else {
      showToast('清空日志失败', 'error');
    }
  } catch (err) {
    showToast('清空日志时发生错误', 'error');
    console.error('clearLogs error:', err);
  }
}

// ===== 结果 =====

/**
 * 加载并渲染领券结果
 */
async function loadResult() {
  try {
    const resp = await fetch('/api/result');
    if (!resp.ok) return;
    const data = await resp.json();
    renderResult(data.result);
    renderHistory(data.history || []);
  } catch (err) {
    console.error('loadResult error:', err);
  }
}

/**
 * 渲染结果面板
 */
function renderResult(result) {
  const summaryEl = document.getElementById('result-summary');
  const tableWrapper = document.getElementById('result-table-wrapper');
  const tbody = document.getElementById('result-tbody');

  if (!result) {
    summaryEl.innerHTML = '<span style="color:#aaa;">尚未执行过任务</span>';
    tableWrapper.style.display = 'none';
    return;
  }

  // 汇总信息
  const summary = result.summary || {};
  const executedAt = result.executed_at
    ? new Date(result.executed_at).toLocaleString('zh-CN')
    : '未知时间';

  // 全为 0 时给出友好提示
  const total = (summary.success || 0) + (summary.failed || 0) + (summary.skipped || 0);
  const emptyHint = total === 0
    ? '<span style="color:#faad14;font-size:12px;margin-left:8px;">本次未找到可领取的券</span>'
    : '';

  summaryEl.innerHTML = `
    <div style="margin-bottom:8px;color:#aaa;font-size:12px;">执行时间：${executedAt}</div>
    <span class="summary-item summary-success">成功 <strong>${summary.success || 0}</strong></span>
    <span class="summary-item summary-failed">失败 <strong>${summary.failed || 0}</strong></span>
    <span class="summary-item summary-skipped">已领取 <strong>${summary.skipped || 0}</strong></span>
    ${emptyHint}
  `;

  // 详情表格
  const items = result.items || [];
  tbody.innerHTML = '';

  if (items.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#aaa;padding:16px;">本次未找到可领取的券</td></tr>';
  } else {
    items.forEach(item => {
      const statusClass = getStatusClass(item.status);
      const statusText = getStatusText(item.status);
      const claimedAt = item.claimed_at
        ? new Date(item.claimed_at).toLocaleString('zh-CN')
        : '-';
      const denomination = item.denomination != null ? `¥${item.denomination}` : '-';
      const minSpend = item.min_spend != null ? `¥${item.min_spend}` : '-';

      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${escapeHtml(item.name || '-')}</td>
        <td>${denomination}</td>
        <td>${minSpend}</td>
        <td><span class="${statusClass}">${statusText}</span></td>
        <td>${escapeHtml(translateFailReason(item.fail_reason))}</td>
        <td>${claimedAt}</td>
      `;
      tbody.appendChild(tr);
    });
  }

  tableWrapper.style.display = 'block';
}

/**
 * 渲染历史记录列表（从第2条开始，第1条已在最新结果中展示）
 */
function renderHistory(history) {
  const wrapper = document.getElementById('result-history-wrapper');
  const listEl = document.getElementById('result-history-list');
  const countEl = document.getElementById('history-count');

  // 历史记录从第2条开始（第1条是最新结果，已在上方展示）
  const older = history.slice(1);

  if (older.length === 0) {
    wrapper.style.display = 'none';
    return;
  }

  countEl.textContent = history.length;
  wrapper.style.display = 'block';

  listEl.innerHTML = older.map((entry, idx) => {
    const summary = entry.summary || {};
    const executedAt = entry.executed_at
      ? new Date(entry.executed_at).toLocaleString('zh-CN')
      : '未知时间';
    const successBadge = summary.success > 0
      ? `<span class="hist-badge hist-badge-success">✓ 成功 ${summary.success} 张</span>`
      : '';
    const failedBadge = summary.failed > 0
      ? `<span class="hist-badge hist-badge-failed">✗ 失败 ${summary.failed} 张</span>`
      : '';
    const skippedBadge = summary.skipped > 0
      ? `<span class="hist-badge hist-badge-skipped">已领取 ${summary.skipped} 张</span>`
      : '';
    const noBadge = (!summary.success && !summary.failed && !summary.skipped)
      ? `<span class="hist-badge hist-badge-empty">未找到可领券</span>`
      : '';

    // 明细表格
    const items = entry.items || [];
    const detailRows = items.map(item => {
      const statusClass = getStatusClass(item.status);
      const statusText = getStatusText(item.status);
      const claimedAt = item.claimed_at
        ? new Date(item.claimed_at).toLocaleString('zh-CN')
        : '-';
      const denomination = item.denomination != null ? `¥${item.denomination}` : '-';
      const minSpend = item.min_spend != null ? `¥${item.min_spend}` : '-';
      return `
        <tr>
          <td>${escapeHtml(item.name || '-')}</td>
          <td>${denomination}</td>
          <td>${minSpend}</td>
          <td><span class="${statusClass}">${statusText}</span></td>
          <td>${escapeHtml(translateFailReason(item.fail_reason))}</td>
          <td>${claimedAt}</td>
        </tr>`;
    }).join('');

    const detailTable = items.length > 0 ? `
      <table class="result-table" style="margin-top:6px;">
        <thead>
          <tr>
            <th>券名称</th><th>面额</th><th>最低消费</th>
            <th>状态</th><th>失败原因</th><th>领取时间</th>
          </tr>
        </thead>
        <tbody>${detailRows}</tbody>
      </table>` : '<div style="color:#aaa;font-size:12px;padding:4px 0;">无券详情</div>';

    return `
      <details style="border-bottom:1px solid #f0f0f0; padding:6px 0;">
        <summary style="cursor:pointer; font-size:13px; list-style:none; display:flex; align-items:center; gap:8px;">
          <span style="color:#888;">${executedAt}</span>
          <span>${successBadge}${failedBadge}${skippedBadge}${noBadge}</span>
        </summary>
        ${detailTable}
      </details>
    `;
  }).join('');
}

function getStatusClass(status) {
  switch (status) {
    case 'success': return 'status-success';
    case 'failed':  return 'status-failed';
    case 'skipped': return 'status-skipped';
    default:        return '';
  }
}

function getStatusText(status) {
  switch (status) {
    case 'success': return '✓ 成功';
    case 'failed':  return '✗ 失败';
    case 'skipped': return '已领取';
    default:        return status || '未知';
  }
}

/**
 * 将英文失败原因转为用户可读中文
 */
function translateFailReason(reason) {
  if (!reason || reason === '-') return '-';
  const map = {
    'out_of_stock':      '券已抢完',
    'not_found':         '未找到券',
    'timeout':           '请求超时',
    'login_required':    '需要重新登录',
    'already_claimed':   '已领取过',
    'not_started':       '活动未开始',
    'ended':             '活动已结束',
    'limit_reached':     '已达领取上限',
    'network_error':     '网络异常',
    'unknown':           '未知原因',
  };
  // 精确匹配
  if (map[reason]) return map[reason];
  // 模糊匹配常见关键词
  if (reason.toLowerCase().includes('timeout')) return '请求超时';
  if (reason.toLowerCase().includes('stock'))   return '券已抢完';
  if (reason.toLowerCase().includes('login'))   return '需要重新登录';
  return reason;
}

// ===== 闲时找券联动 =====

/**
 * 根据闲时找券开关状态控制时间段输入框的显示
 */
function _updateIdleTimeRangeVisibility() {
  const enabled = document.getElementById('idle-check-toggle').checked;
  const group = document.getElementById('idle-time-range-group');
  if (group) group.style.display = enabled ? '' : 'none';
}

/**
 * 根据邮件通知开关状态控制邮件配置区域的显示
 */
function _updateEmailNotifyVisibility() {
  const enabled = document.getElementById('email-notify-toggle').checked;
  const group = document.getElementById('email-notify-group');
  if (group) group.style.display = enabled ? '' : 'none';
}

// 绑定开关变化事件（在 DOMContentLoaded 后执行）
document.addEventListener('DOMContentLoaded', () => {
  // 初始化巡检时间段自定义时间选择器
  ['idle-start-hour', 'idle-end-hour'].forEach(id => {
    const picker = document.getElementById(id);
    if (!picker) return;
    _fillTimePicker(picker, 0, 23);
    _bindTimePicker(picker);
  });

  const idleToggle = document.getElementById('idle-check-toggle');
  if (idleToggle) idleToggle.addEventListener('change', _updateIdleTimeRangeVisibility);

  const emailToggle = document.getElementById('email-notify-toggle');
  if (emailToggle) emailToggle.addEventListener('change', _updateEmailNotifyVisibility);
});

// ===== 动态列表 =====

/**
 * 在触发时间列表中添加一行（自定义时间选择器）
 * @param {string} value - cron 表达式，如 "29 10 * * *"；空串则默认 10:00
 */
function addCronRow(value) {
  const list = document.getElementById('cron-list');
  const row = document.createElement('div');
  row.className = 'list-row cron-row';

  const time = cronToTime(value);

  row.innerHTML = `
    <span class="time-label">每天</span>
    <div class="time-picker cron-hour" data-value="${time.hour}">
      <div class="time-picker-val">
        <span class="tp-num">${String(time.hour).padStart(2,'0')}</span>
        <span class="tp-arrow">▾</span>
      </div>
      <div class="time-picker-dropdown"></div>
    </div>
    <span class="time-colon">:</span>
    <div class="time-picker cron-minute" data-value="${time.minute}">
      <div class="time-picker-val">
        <span class="tp-num">${String(time.minute).padStart(2,'0')}</span>
        <span class="tp-arrow">▾</span>
      </div>
      <div class="time-picker-dropdown"></div>
    </div>
    <span class="time-label">触发</span>
    <button type="button" class="btn-remove" aria-label="删除" onclick="this.parentElement.remove()">×</button>
  `;
  list.appendChild(row);

  // 填充下拉选项
  const hourPicker = row.querySelector('.cron-hour');
  const minPicker = row.querySelector('.cron-minute');
  _fillTimePicker(hourPicker, 0, 23);
  _fillTimePicker(minPicker, 0, 59);
  _bindTimePicker(hourPicker);
  _bindTimePicker(minPicker);
}

/**
 * 填充时间选择器下拉选项
 */
function _fillTimePicker(picker, min, max) {
  const dropdown = picker.querySelector('.time-picker-dropdown');
  const currentVal = parseInt(picker.dataset.value);
  for (let i = min; i <= max; i++) {
    const opt = document.createElement('div');
    opt.className = 'time-picker-option';
    if (i === currentVal) opt.classList.add('selected');
    opt.textContent = String(i).padStart(2, '0');
    opt.dataset.value = i;
    dropdown.appendChild(opt);
  }
}

/**
 * 绑定时间选择器交互逻辑
 */
function _bindTimePicker(picker) {
  const valEl = picker.querySelector('.time-picker-val');
  const dropdown = picker.querySelector('.time-picker-dropdown');
  const numEl = picker.querySelector('.tp-num');

  // 点击显示/隐藏下拉
  valEl.addEventListener('click', (e) => {
    e.stopPropagation();
    // 关闭其他打开的下拉
    document.querySelectorAll('.time-picker-dropdown.open').forEach(d => {
      if (d !== dropdown) d.classList.remove('open');
    });
    dropdown.classList.toggle('open');
  });

  // 点击选项
  dropdown.addEventListener('click', (e) => {
    if (e.target.classList.contains('time-picker-option')) {
      const val = parseInt(e.target.dataset.value);
      picker.dataset.value = val;
      numEl.textContent = String(val).padStart(2, '0');
      dropdown.querySelectorAll('.time-picker-option').forEach(o => o.classList.remove('selected'));
      e.target.classList.add('selected');
      dropdown.classList.remove('open');
    }
  });
}

// 全局点击关闭所有下拉
document.addEventListener('click', () => {
  document.querySelectorAll('.time-picker-dropdown.open').forEach(d => d.classList.remove('open'));
});

/**
 * 通过 id 设置自定义时间选择器的值
 */
function _setTimePicker(id, val) {
  const picker = document.getElementById(id);
  if (!picker) return;
  const v = parseInt(val);
  picker.dataset.value = v;
  const numEl = picker.querySelector('.tp-num');
  if (numEl) numEl.textContent = String(v).padStart(2, '0');
  picker.querySelectorAll('.time-picker-option').forEach(o => {
    o.classList.toggle('selected', parseInt(o.dataset.value) === v);
  });
}

/**
 * 在活动 URL 列表中添加一行（URL 和名称分列）
 * @param {string} url  - 活动 URL
 * @param {string} name - 活动名称
 */
function addTargetRow(url, name) {
  const urlCol  = document.getElementById('target-url-col');
  const nameCol = document.getElementById('target-name-col');
  const idx = urlCol.children.length;

  const urlInput = document.createElement('input');
  urlInput.type = 'text';
  urlInput.className = 'target-url target-input';
  urlInput.dataset.idx = idx;
  urlInput.value = url;
  urlInput.placeholder = 'https://waimai.jd.com/...';
  urlInput.style.cssText = 'width:100%; max-width:none; margin-bottom:6px;';

  const nameWrap = document.createElement('div');
  nameWrap.style.cssText = 'display:flex; align-items:center; gap:6px; margin-bottom:6px;';
  const nameInput = document.createElement('input');
  nameInput.type = 'text';
  nameInput.className = 'target-name target-input';
  nameInput.dataset.idx = idx;
  nameInput.value = name;
  nameInput.placeholder = '备注名称（可选）';
  nameInput.style.cssText = 'flex:1; max-width:none;';

  const removeBtn = document.createElement('button');
  removeBtn.type = 'button';
  removeBtn.className = 'btn-remove';
  removeBtn.setAttribute('aria-label', '删除');
  removeBtn.textContent = '×';
  removeBtn.onclick = () => {
    // 同步删除 URL 列和名称列对应行
    urlInput.remove();
    nameWrap.remove();
  };

  nameWrap.appendChild(nameInput);
  nameWrap.appendChild(removeBtn);
  urlCol.appendChild(urlInput);
  nameCol.appendChild(nameWrap);
}

/**
 * 将 cron 表达式解析为 {hour, minute}
 * 仅支持 "MM HH * * *" 格式，失败返回默认 {hour:10, minute:0}
 */
function cronToTime(expr) {
  if (!expr || !expr.trim()) return { hour: 10, minute: 0 };
  const parts = expr.trim().split(/\s+/);
  if (parts.length === 5) {
    const min  = parseInt(parts[0]);
    const hour = parseInt(parts[1]);
    if (!isNaN(min) && !isNaN(hour) && min >= 0 && min <= 59 && hour >= 0 && hour <= 23) {
      return { hour, minute: min };
    }
  }
  return { hour: 10, minute: 0 };
}

/**
 * 将时间选择器的值转换为 cron 表达式
 * @param {HTMLElement} row
 * @returns {string}
 */
function timeToCron(row) {
  const h = row.querySelector('.cron-hour').dataset.value;
  const m = row.querySelector('.cron-minute').dataset.value;
  return `${m} ${h} * * *`;
}

/**
 * 将五字段 cron 表达式解析为人类可读描述（供旧数据降级展示用）
 * @param {string} expr
 * @returns {string}
 */
function parseCronDesc(expr) {
  if (!expr || !expr.trim()) return '';
  const parts = expr.trim().split(/\s+/);
  if (parts.length !== 5) return '格式不正确';
  const [min, hour, dom, month, dow] = parts;
  const isNum = s => /^\d+$/.test(s);
  const star  = s => s === '*';
  if (isNum(min) && isNum(hour) && star(dom) && star(month) && star(dow)) {
    return `每天 ${String(hour).padStart(2,'0')}:${String(min).padStart(2,'0')} 触发`;
  }
  return '自定义计划';
}

// ===== Toast 提示 =====

let _toastTimer = null;

/**
 * 显示临时提示
 * @param {string} message - 提示内容
 * @param {'success'|'error'|'info'} type - 提示类型
 */
function showToast(message, type = 'info') {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.className = `toast ${type} show`;

  if (_toastTimer) clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => {
    toast.className = 'toast';
  }, 3000);
}

// ===== 工具函数 =====

function escapeHtml(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escapeAttr(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
