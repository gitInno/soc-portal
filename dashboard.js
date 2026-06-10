'use strict';

// ── Aktívny alert filter ──────────────────────────────────────
let _alertStatusFilter = 'open';
let _alertSeverityFilter = 'all';
let _notifChannels = [];

// ── Load Dashboard ────────────────────────────────────────────
async function loadDashboard(tenantSlug) {
  if (!tenantSlug) return;
  _currentTenantSlug = tenantSlug;
  try {
    const r = await fetch(API_BASE + '/api/v1/portal/dashboard?tenant=' + tenantSlug, {
      headers: {'X-Portal-Token': getPortalToken()}
    });
    const d = await r.json();
    if (d.error) { console.error('Dashboard error:', d.error); return; }

    // Meno + greeting
    const firstName = (d.name || '').split(' ')[0];
    const el = document.getElementById('dash-username');
    if (el) el.textContent = d.name || tenantSlug;
    const meta = document.getElementById('dash-usermeta');
    if (meta) meta.textContent = (d.company || tenantSlug) + ' · SOC';
    const gr = document.getElementById('dash-greeting');
    if (gr) gr.textContent = firstName || tenantSlug;

    // Stats
    const s = d.stats || {};
    const dcA = document.getElementById('dc-alerts24');
    if (dcA) dcA.textContent = s.alerts_24h ?? '-';
    const dcC = document.getElementById('dc-critical');
    if (dcC) dcC.textContent = s.critical_24h ?? '-';

    // Probe status
    const probeEl = document.getElementById('dc-probe');
    const probeBadge = document.querySelector('.dash-user-badge');
    if (d.probe) {
      const online = d.probe.online;
      if (probeEl) { probeEl.textContent = online ? 'OK' : 'OFFLINE'; probeEl.className = 'stat-card-val ' + (online ? 'green' : 'red'); }
      const trend = probeEl ? probeEl.closest('.stat-card').querySelector('.stat-card-trend') : null;
      if (trend && d.probe.last_seen) {
        const ago = Math.round((Date.now() - new Date(d.probe.last_seen).getTime()) / 1000);
        trend.textContent = 'Heartbeat pred ' + ago + 's';
      }
      if (probeBadge) {
        probeBadge.innerHTML = '<div class="dash-user-badge-dot"></div>Probe ' + (online ? 'online' : 'offline');
        probeBadge.style.borderColor = online ? 'rgba(34,197,94,.2)' : 'rgba(239,68,68,.2)';
      }
    } else {
      if (probeEl) { probeEl.textContent = 'N/A'; probeEl.className = 'stat-card-val'; }
      if (probeBadge) probeBadge.innerHTML = '<div class="dash-user-badge-dot" style="background:#94a3b8"></div>Probe neznáma';
    }

    // Alert preview (top 3)
    const preview = document.getElementById('dash-alert-preview');
    if (preview && d.alerts && d.alerts.length > 0) {
      const top3 = d.alerts.slice(0, 3);
      preview.innerHTML = top3.map(a => {
        const sev = (a.severity || 'low').toLowerCase();
        const badgeClass = sev === 'critical' ? 'badge-red' : sev === 'high' ? 'badge-amber' : sev === 'medium' ? 'badge-blue' : 'badge-green';
        const time = a.timestamp ? new Date(a.timestamp).toLocaleTimeString('sk-SK', {hour: '2-digit', minute: '2-digit'}) : '';
        return '<div class="alert-list-item">' +
          '<div class="alert-sev-bar ' + sev + '"></div>' +
          '<div class="alert-info">' +
            '<div class="alert-rule">' + (a.description || 'Alert') + '</div>' +
            '<div class="alert-meta-line">' + (a.agent_name || '') + (a.source_ip ? ' · ' + a.source_ip : '') + '</div>' +
          '</div>' +
          '<div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px">' +
            '<span class="badge ' + badgeClass + '">' + sev.toUpperCase() + '</span>' +
            '<span class="alert-time">' + time + '</span>' +
          '</div>' +
        '</div>';
      }).join('');
    } else if (preview) {
      preview.innerHTML = '<div style="padding:24px;text-align:center;color:var(--text3)">Žiadne alerty za posledných 24h</div>';
    }

    // Update time
    const timeSub = document.getElementById('dash-time-sub');
    if (timeSub) timeSub.textContent = 'Posledná aktualizácia: ' + new Date().toLocaleTimeString('sk-SK', {hour12: false});

    // Načítaj alerts tab s aktívnym filtrom
    await loadAlerts(tenantSlug, _alertStatusFilter, _alertSeverityFilter);
    // Zariadenia overview (bez await — nenblokuje dashboard)
    loadDevices();
  } catch (e) {
    console.error('Dashboard fetch error:', e);
  }
}

// ── Load Alerts (s API filtrom) ───────────────────────────────
async function loadAlerts(tenantSlug, status, severity) {
  status = status || 'open';
  severity = severity || 'all';
  let url = API_BASE + '/api/v1/portal/alerts?tenant=' + tenantSlug + '&status=' + status + '&limit=100';
  const alertList = document.querySelector('#dv-alerts .panel-body-flush');
  if (!alertList) return;
  alertList.innerHTML = '<div style="padding:24px;text-align:center;color:var(--text3)">Načítavam alerty...</div>';
  try {
    const r = await fetch(url, {headers: {'X-Portal-Token': getPortalToken()}});
    const d = await r.json();
    if (!d.success) { alertList.innerHTML = '<div style="padding:24px;color:#f87171">Chyba načítania alertov</div>'; return; }
    let alerts = d.alerts || [];
    if (severity !== 'all') {
      alerts = alerts.filter(a => (a.severity || '').toLowerCase() === severity);
    }
    if (alerts.length === 0) {
      alertList.innerHTML = '<div style="padding:32px;text-align:center;color:var(--text3)">Žiadne alerty ✓</div>';
      return;
    }
    alertList.innerHTML = alerts.map(a => {
      const sev = (a.severity || 'low').toLowerCase();
      const badgeClass = sev === 'critical' ? 'badge-red' : sev === 'high' ? 'badge-amber' : sev === 'medium' ? 'badge-blue' : 'badge-green';
      const time = a.created_at ? new Date(a.created_at).toLocaleString('sk-SK', {hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit'}) : '';
      const st = a.status || 'open';
      const stLabel = {open: 'Nový', in_progress: 'Rieši sa', closed: 'Uzavretý'}[st] || st;
      const stColor = {open: 'color:#f59e0b', in_progress: 'color:#3b82f6', closed: 'color:#22c55e'}[st] || '';
      const nextAction = st === 'open'
        ? `<button onclick="setAlertStatus('${a.id}','in_progress','${tenantSlug}')" style="font-size:11px;padding:3px 8px;background:rgba(59,130,246,.15);border:1px solid rgba(59,130,246,.3);color:#3b82f6;border-radius:4px;cursor:pointer">▶ Riešiť</button>`
        : st === 'in_progress'
        ? `<button onclick="setAlertStatus('${a.id}','closed','${tenantSlug}')" style="font-size:11px;padding:3px 8px;background:rgba(34,197,94,.15);border:1px solid rgba(34,197,94,.3);color:#22c55e;border-radius:4px;cursor:pointer">✓ Uzavrieť</button>`
        : `<button onclick="setAlertStatus('${a.id}','open','${tenantSlug}')" style="font-size:11px;padding:3px 8px;background:rgba(100,116,139,.15);border:1px solid rgba(100,116,139,.3);color:#94a3b8;border-radius:4px;cursor:pointer">↩ Znovu otvoriť</button>`;
      return '<div class="alert-list-item" id="ali-' + a.id + '" data-status="' + st + '" data-severity="' + sev + '">' +
        '<div class="alert-sev-bar ' + sev + '"></div>' +
        '<div class="alert-info">' +
          '<div class="alert-rule">' + (a.summary || 'Alert') + '</div>' +
          '<div class="alert-meta-line">Agent: ' + (a.agent_name || '-') + (a.recommended_action ? ' · ' + a.recommended_action.substring(0, 80) : '') + '</div>' +
        '</div>' +
        '<div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px">' +
          '<span class="badge ' + badgeClass + '">' + sev.toUpperCase() + '</span>' +
          '<span style="font-size:11px;' + stColor + '">' + stLabel + '</span>' +
          '<span class="alert-time">' + time + '</span>' +
          nextAction +
        '</div>' +
      '</div>';
    }).join('');
  } catch (e) {
    alertList.innerHTML = '<div style="padding:24px;color:#f87171">Chyba spojenia</div>';
    console.error('loadAlerts error:', e);
  }
}

// ── Filter Alerts ─────────────────────────────────────────────
function filterAlerts(status) {
  _alertStatusFilter = status;
  document.querySelectorAll('[id^=fbtn-]').forEach(b => {
    b.style.fontWeight = '400';
    b.style.background = 'transparent';
    b.style.borderColor = 'var(--border)';
    b.style.color = 'var(--text2)';
  });
  const active = document.getElementById('fbtn-' + status);
  if (active) {
    active.style.fontWeight = '600';
    active.style.background = 'rgba(99,102,241,.15)';
    active.style.borderColor = 'rgba(99,102,241,.4)';
    active.style.color = 'var(--accent)';
  }
  const tenant = _currentTenantSlug || window._dashTenant || '';
  if (tenant) loadAlerts(tenant, status, _alertSeverityFilter);
}

function filterAlertsBySeverity(severity) {
  _alertSeverityFilter = severity;
  document.querySelectorAll('[id^=sbtn-]').forEach(b => {
    b.style.fontWeight = '400';
    b.style.background = 'transparent';
    b.style.borderColor = 'var(--border)';
    b.style.color = 'var(--text2)';
  });
  const active = document.getElementById('sbtn-' + severity);
  if (active) {
    active.style.fontWeight = '600';
    active.style.background = 'rgba(99,102,241,.15)';
    active.style.borderColor = 'rgba(99,102,241,.4)';
    active.style.color = 'var(--accent)';
  }
  const tenant = _currentTenantSlug || window._dashTenant || '';
  if (tenant) loadAlerts(tenant, _alertStatusFilter, severity);
}

// ── Set Alert Status ──────────────────────────────────────────
async function setAlertStatus(alertId, newStatus, tenantSlug) {
  try {
    const r = await fetch(API_BASE + '/api/v1/portal/alert/status', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-Portal-Token': getPortalToken()},
      body: JSON.stringify({alert_id: alertId, status: newStatus, tenant: tenantSlug})
    });
    const d = await r.json();
    if (d.success) {
      await loadAlerts(tenantSlug, _alertStatusFilter, _alertSeverityFilter);
    } else {
      console.error('setAlertStatus error:', d.error);
    }
  } catch (e) {
    console.error('setAlertStatus:', e);
  }
}

// ── NIS2 Report ───────────────────────────────────────────────
async function generateReport() {
  const slug = _currentTenantSlug || window._dashTenant || '';
  if (!slug) { alert('Chyba: tenant nie je prihlásený.'); return; }
  const days = document.getElementById('report-days').value || '30';
  const btn = document.getElementById('report-btn');
  const statusEl = document.getElementById('report-status');
  btn.disabled = true;
  btn.textContent = 'Generujem...';
  if (statusEl) {
    statusEl.style.display = 'block';
    statusEl.style.borderLeftColor = 'var(--accent)';
    statusEl.style.color = 'var(--text2)';
    statusEl.textContent = 'Generujem NIS2 report za posledných ' + days + ' dní...';
  }
  try {
    const r = await fetch(API_BASE + '/api/v1/report/generate?tenant=' + encodeURIComponent(slug) + '&days=' + days, {
      headers: {'X-Portal-Token': getPortalToken()}
    });
    if (!r.ok) {
      const e = await r.json();
      throw new Error(e.error || 'HTTP ' + r.status);
    }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'SOC-NIS2-Report-' + slug + '-' + days + 'd.pdf';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    if (statusEl) {
      statusEl.style.borderLeftColor = '#22c55e';
      statusEl.style.color = '#22c55e';
      statusEl.textContent = 'Report bol úspešne vygenerovaný a stiahnutý.';
    }
  } catch (err) {
    if (statusEl) {
      statusEl.style.borderLeftColor = 'var(--red)';
      statusEl.style.color = 'var(--red)';
      statusEl.textContent = 'Chyba: ' + err.message;
    }
  } finally {
    btn.disabled = false;
    btn.textContent = 'Generovať NIS2 report';
  }
}

// ── Notifications ─────────────────────────────────────────────
async function loadNotifications() {
  const tenant = _currentTenantSlug || window._dashTenant || '';
  if (!tenant) return;
  try {
    const r = await fetch(API_BASE + '/api/v1/portal/notifications?tenant=' + tenant, {
      headers: {'X-Portal-Token': getPortalToken()}
    });
    const d = await r.json();
    if (!d.success) return;
    _notifChannels = d.channels || [];
    renderNotifications();
  } catch(e) { console.error('loadNotifications:', e); }
}

function renderNotifications() {
  const emailRec = _notifChannels.find(c => c.channel === 'email');
  const tgRec    = _notifChannels.find(c => c.channel === 'telegram');

  // Email
  const emailAddr = document.getElementById('notif-email-addr');
  const emailTog  = document.getElementById('notif-email-toggle');
  if (emailAddr && emailRec) {
    emailAddr.textContent = emailRec.address;
    emailTog.checked = emailRec.active;
    emailTog.dataset.id = emailRec.id;
  }

  // Telegram
  const tgInput = document.getElementById('notif-tg-input');
  const tgTog   = document.getElementById('notif-tg-toggle');
  if (tgRec) {
    if (tgInput) tgInput.value = tgRec.address;
    if (tgTog)  { tgTog.checked = tgRec.active; tgTog.dataset.id = tgRec.id; }
  }
}

async function toggleNotification(id, active) {
  const tenant = _currentTenantSlug || window._dashTenant || '';
  try {
    await fetch(API_BASE + '/api/v1/portal/notifications', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-Portal-Token': getPortalToken()},
      body: JSON.stringify({tenant, id, active})
    });
    await loadNotifications();
  } catch(e) { console.error('toggleNotification:', e); }
}

// ── Devices (Zariadenia) ──────────────────────────────────────
async function loadDevices() {
  const tenant = _currentTenantSlug || window._dashTenant || '';
  if (!tenant) return;
  const tbody = document.getElementById('devices-table');
  if (tbody) tbody.innerHTML = '<tr><td colspan="5" style="padding:24px;text-align:center;color:var(--text3)">Načítavam zariadenia...</td></tr>';
  try {
    const r = await fetch(API_BASE + '/api/v1/portal/devices?tenant=' + tenant, {
      headers: {'X-Portal-Token': getPortalToken()}
    });
    const d = await r.json();
    if (!d.success) throw new Error(d.error || 'Chyba API');
    renderDevices(d.devices || []);
    const dcDev = document.getElementById('dc-devices');
    if (dcDev) dcDev.textContent = d.online;
    const overviewList = document.getElementById('overview-devices-list');
    if (overviewList) {
      if (!d.devices.length) {
        overviewList.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text3);font-size:13px">Žiadne zariadenia</div>';
      } else {
        overviewList.innerHTML = d.devices.slice(0, 5).map(dev =>
          '<div class="device-row">' +
          '<div class="device-status-dot ' + (dev.online ? 'online' : 'offline') + '"></div>' +
          '<div class="device-name">' + dev.hostname + '</div>' +
          '<div class="device-ip">' + (dev.ip || '') + '</div>' +
          '</div>'
        ).join('');
      }
    }
  } catch(e) {
    if (tbody) tbody.innerHTML = '<tr><td colspan="5" style="padding:24px;text-align:center;color:var(--red)">Chyba načítania zariadení</td></tr>';
    console.error('loadDevices:', e);
  }
}

function renderDevices(devices) {
  const tbody = document.getElementById('devices-table');
  if (!tbody) return;
  if (!devices.length) {
    tbody.innerHTML = '<tr><td colspan="5" style="padding:32px;text-align:center;color:var(--text3)">Žiadne zariadenia. Nainštalujte SW Probe u zákazníka.</td></tr>';
    return;
  }
  tbody.innerHTML = devices.map((d, i) => {
    const isLast = i === devices.length - 1;
    const border = isLast ? '' : 'border-bottom:1px solid var(--border)';
    const dotCls = d.online ? 'online' : (d.status === 'unknown' ? 'unknown' : 'offline');
    const badgeSt = d.online ? 'badge-green' : (d.status === 'unknown' ? 'badge-gray' : 'badge-red');
    const stLabel = d.online ? 'Online' : (d.status === 'unknown' ? 'Neznámy' : 'Offline');
    const typeBadge = d.probe_type === 'SOC Agent' ? 'badge-blue' : 'badge-gray';
    return '<tr style="' + border + '">' +
      '<td style="padding:12px 20px"><div style="display:flex;align-items:center;gap:10px"><div class="device-status-dot ' + dotCls + '"></div><strong>' + d.hostname + '</strong>' + (d.version ? '<span style="font-size:10px;color:var(--text3);margin-left:4px">v' + d.version + '</span>' : '') + '</div></td>' +
      '<td style="padding:12px 20px;font-family:var(--mono);font-size:12px;color:var(--text2)">' + (d.ip || '—') + '</td>' +
      '<td style="padding:12px 20px"><span class="badge ' + typeBadge + '">' + d.probe_type + '</span></td>' +
      '<td style="padding:12px 20px"><span class="badge ' + badgeSt + '">' + stLabel + '</span></td>' +
      '<td style="padding:12px 20px;font-family:var(--mono);font-size:11px;color:var(--text3)">' + (d.last_seen || '—') + '</td>' +
    '</tr>';
  }).join('');
}

async function saveTelegram() {
  const tenant = _currentTenantSlug || window._dashTenant || '';
  const input  = document.getElementById('notif-tg-input');
  const btn    = document.getElementById('notif-tg-btn');
  const msg    = document.getElementById('notif-tg-msg');
  const address = (input ? input.value : '').trim();
  if (!address) { if(msg){msg.textContent='Zadajte Telegram Chat ID';msg.style.color='var(--red)';msg.style.display='block';} return; }
  if (btn) { btn.disabled = true; btn.textContent = 'Ukladám...'; }
  if (msg) msg.style.display = 'none';
  try {
    const r = await fetch(API_BASE + '/api/v1/portal/notifications', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-Portal-Token': getPortalToken()},
      body: JSON.stringify({tenant, channel: 'telegram', address, label: 'Telegram', active: true})
    });
    const d = await r.json();
    if (d.success) {
      if (msg) { msg.textContent = 'Telegram uložený'; msg.style.color = 'var(--green)'; msg.style.display = 'block'; }
      await loadNotifications();
    } else {
      if (msg) { msg.textContent = d.error || 'Chyba'; msg.style.color = 'var(--red)'; msg.style.display = 'block'; }
    }
  } catch(e) {
    if (msg) { msg.textContent = 'Chyba spojenia'; msg.style.color = 'var(--red)'; msg.style.display = 'block'; }
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Uložiť'; }
  }
}
