/**
 * 京东外卖券自动领取 - 管理界面前端逻辑
 */

// ===== 应用状态 =====
const state = {
  schedulerRunning: false,
  logLines: [],
  lastLogCount: 0,
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
    const targetList = document.getElementById('target-list');
    targetList.innerHTML = '';
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
    // 收集 Cron 列表
    const cronInputs = document.querySelectorAll('#cron-list .cron-input');
    const schedule = Array.from(cronInputs)
      .map(el => el.value.trim())
      .filter(v => v !== '');

    // 收集活动 URL 列表
    const targetRows = document.querySelectorAll('#target-list .target-row');
    const coupon_targets = Array.from(targetRows).map(row => ({
      url: row.querySelector('.target-url').value.trim(),
      name: row.querySelector('.target-name').value.trim(),
    })).filter(t => t.url !== '');

    // 推送服务（保留字段兼容旧配置，不在界面展示，保存时不覆盖）
    const jd_area = document.getElementById('jd-area').value.trim();

    // headless：开关勾选=弹出窗口（headless=false），未勾选=后台静默（headless=true）
    const headless = !document.getElementById('headless-toggle').checked;

    // 刷新间隔
    const grab_interval_ms = parseInt(document.getElementById('grab-interval').value) || 0;

    const payload = {
      credential: { cookie: '' },
      schedule,
      coupon_targets,
      jd_area,
      headless,
      grab_interval_ms,
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
 * 将日志行渲染到 #log-content
 */
function renderLogs(lines) {
  const logEl = document.getElementById('log-content');

  if (!lines || lines.length === 0) {
    logEl.innerHTML = '暂无日志';
    return;
  }

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

  logEl.innerHTML = html;

  // 自动滚动到底部
  logEl.scrollTop = logEl.scrollHeight;
}

/**
 * 轮询日志（每 3 秒）
 */
function pollLogs() {
  setInterval(loadLogs, 3000);
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
    summaryEl.textContent = '尚未执行过任务';
    tableWrapper.style.display = 'none';
    return;
  }

  // 汇总信息
  const summary = result.summary || {};
  const executedAt = result.executed_at
    ? new Date(result.executed_at).toLocaleString('zh-CN')
    : '未知时间';

  summaryEl.innerHTML = `
    <div style="margin-bottom:8px;color:#888;font-size:13px;">执行时间：${executedAt}</div>
    <span class="summary-item summary-success">成功 <strong>${summary.success || 0}</strong></span>
    <span class="summary-item summary-failed">失败 <strong>${summary.failed || 0}</strong></span>
    <span class="summary-item summary-skipped">已领取 <strong>${summary.skipped || 0}</strong></span>
  `;

  // 详情表格
  const items = result.items || [];
  tbody.innerHTML = '';

  if (items.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#888;">无券详情</td></tr>';
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
        <td>${escapeHtml(item.fail_reason || '-')}</td>
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
      ? `<span class="summary-item summary-success" style="font-size:12px;">成功 ${summary.success}</span>`
      : '';
    const failedBadge = summary.failed > 0
      ? `<span class="summary-item summary-failed" style="font-size:12px;">失败 ${summary.failed}</span>`
      : '';
    const skippedBadge = summary.skipped > 0
      ? `<span class="summary-item summary-skipped" style="font-size:12px;">已领取 ${summary.skipped}</span>`
      : '';
    const noBadge = (!summary.success && !summary.failed && !summary.skipped)
      ? `<span style="color:#aaa;font-size:12px;">无结果</span>`
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
          <td>${escapeHtml(item.fail_reason || '-')}</td>
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
    case 'success': return '成功';
    case 'failed':  return '失败';
    case 'skipped': return '已领取';
    default:        return status || '未知';
  }
}

// ===== 动态列表 =====

/**
 * 在 Cron 列表中添加一行
 * @param {string} value - 初始 cron 表达式值
 */
function addCronRow(value) {
  const list = document.getElementById('cron-list');
  const row = document.createElement('div');
  row.className = 'list-row';
  row.innerHTML = `
    <input type="text" class="cron-input" value="${escapeAttr(value)}" placeholder="0 12 * * *" />
    <button type="button" class="btn-remove" onclick="this.parentElement.remove()">删除</button>
  `;
  list.appendChild(row);
}

/**
 * 在活动 URL 列表中添加一行
 * @param {string} url  - 活动 URL
 * @param {string} name - 活动名称
 */
function addTargetRow(url, name) {
  const list = document.getElementById('target-list');
  const row = document.createElement('div');
  row.className = 'list-row target-row';
  row.innerHTML = `
    <input type="text" class="target-url" value="${escapeAttr(url)}" placeholder="https://waimai.jd.com/..." style="flex:2" />
    <input type="text" class="target-name" value="${escapeAttr(name)}" placeholder="活动名称（可选）" style="flex:1" />
    <button type="button" class="btn-remove" onclick="this.parentElement.remove()">删除</button>
  `;
  list.appendChild(row);
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
