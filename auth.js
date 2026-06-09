'use strict';

// ── Unified Login ─────────────────────────────────────────────
async function doLogin() {
  const email = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value;
  const err = document.getElementById('login-error');
  const btn = document.getElementById('login-btn');
  err.style.display = 'none';
  btn.textContent = '...';
  btn.disabled = true;
  try {
    const r = await fetch(API_BASE + '/api/v1/portal/auth', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-SOC-Key': SOC_KEY},
      body: JSON.stringify({email, password})
    });
    if (r.status === 429) {
      err.textContent = 'Príliš veľa pokusov. Počkajte minútu a skúste znova.';
      err.style.display = 'block';
      return;
    }
    const d = await r.json();
    if (!d.success) {
      err.textContent = d.error || 'Nesprávny email alebo heslo';
      err.style.display = 'block';
      return;
    }
    if (d.multiple) {
      showProfileSelector(d.profiles);
    } else {
      handleProfileLogin(d.profile);
    }
  } catch {
    err.textContent = 'Chyba pripojenia k serveru';
    err.style.display = 'block';
  } finally {
    btn.textContent = 'Prihlásiť sa';
    btn.disabled = false;
  }
}

function showProfileSelector(profiles) {
  document.getElementById('ls-credentials').style.display = 'none';
  document.getElementById('ls-profiles').style.display = 'block';
  const icons = {customer: '🏢', partner: '🤝', operator: '⚙️'};
  const roleNames = {customer: 'Zákazník', partner: 'Partner', operator: 'Operátor'};
  document.getElementById('profile-list').innerHTML = profiles.map((p, i) => `
    <div class="profile-item" onclick="selectProfile(${i})">
      <div class="profile-icon ${p.role}">${icons[p.role] || '👤'}</div>
      <div class="profile-info">
        <div class="profile-role">${roleNames[p.role] || p.role}</div>
        <div class="profile-name">${p.name}</div>
        <div class="profile-company">${p.company || ''}</div>
      </div>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
    </div>
  `).join('');
  window._loginProfiles = profiles;
}

function selectProfile(idx) {
  handleProfileLogin(window._loginProfiles[idx]);
}

function backToCredentials() {
  document.getElementById('ls-credentials').style.display = 'block';
  document.getElementById('ls-profiles').style.display = 'none';
}

function handleProfileLogin(profile) {
  if (profile.role === 'customer') {
    regData.slug = profile.slug;
    regData.name = profile.name;
    regData.company = profile.company || '';
    _currentTenantSlug = profile.slug;
    sessionStorage.setItem('soc_session', JSON.stringify({slug: profile.slug, name: profile.name, role: 'customer'}));
    showPage('dashboard');
    loadDashboard(profile.slug);
  } else if (profile.role === 'partner') {
    sessionStorage.setItem('partner_session', JSON.stringify(profile));
    window.location.href = '/partner';
  } else if (profile.role === 'operator') {
    sessionStorage.setItem('op_session', JSON.stringify(profile));
    window.location.href = '/operator';
  }
}

// ── Reset hesla ───────────────────────────────────────────────
function openResetModal() {
  document.getElementById('modal-reset').style.display = 'flex';
  document.getElementById('reset-ok').style.display = 'none';
  document.getElementById('reset-err').style.display = 'none';
  document.getElementById('reset-email').value = '';
}

function closeResetModal() {
  document.getElementById('modal-reset').style.display = 'none';
}

async function doResetRequest() {
  const email = document.getElementById('reset-email').value.trim();
  const ok = document.getElementById('reset-ok');
  const err = document.getElementById('reset-err');
  ok.style.display = 'none';
  err.style.display = 'none';
  if (!email) { err.textContent = 'Zadajte email'; err.style.display = 'block'; return; }
  try {
    await fetch(API_BASE + '/api/v1/auth/reset-password-request', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-SOC-Key': SOC_KEY},
      body: JSON.stringify({email})
    });
    ok.style.display = 'block';
    document.getElementById('reset-email').value = '';
  } catch {
    err.textContent = 'Chyba pripojenia';
    err.style.display = 'block';
  }
}

async function doResetConfirm() {
  const token = window._resetToken || '';
  const pw1 = document.getElementById('newpw-1').value;
  const pw2 = document.getElementById('newpw-2').value;
  const ok = document.getElementById('newpw-ok');
  const err = document.getElementById('newpw-err');
  ok.style.display = 'none';
  err.style.display = 'none';
  if (pw1 !== pw2) { err.textContent = 'Heslá sa nezhodujú'; err.style.display = 'block'; return; }
  if (pw1.length < 8) { err.textContent = 'Min. 8 znakov'; err.style.display = 'block'; return; }
  try {
    const r = await fetch(API_BASE + '/api/v1/auth/reset-password', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-SOC-Key': SOC_KEY},
      body: JSON.stringify({token, new_password: pw1})
    });
    const d = await r.json();
    if (d.success) {
      ok.textContent = 'Heslo nastavené. Môžete sa prihlásiť.';
      ok.style.display = 'block';
      setTimeout(() => { document.getElementById('modal-newpw').style.display = 'none'; showPage('login'); }, 2000);
    } else {
      err.textContent = d.error || 'Chyba';
      err.style.display = 'block';
    }
  } catch {
    err.textContent = 'Chyba pripojenia';
    err.style.display = 'block';
  }
}

// ── Zmena hesla ───────────────────────────────────────────────
async function doChangePassword() {
  const slug = _currentTenantSlug || window._dashTenant || '';
  const oldPw = document.getElementById('pw-old').value;
  const newPw = document.getElementById('pw-new').value;
  const newPw2 = document.getElementById('pw-new2').value;
  const ok = document.getElementById('pw-change-ok');
  const err = document.getElementById('pw-change-err');
  ok.style.display = 'none';
  err.style.display = 'none';
  if (!oldPw || !newPw || !newPw2) { err.textContent = 'Vyplňte všetky polia'; err.style.display = 'block'; return; }
  if (newPw !== newPw2) { err.textContent = 'Nové heslá sa nezhodujú'; err.style.display = 'block'; return; }
  if (newPw.length < 8) { err.textContent = 'Heslo musí mať aspoň 8 znakov'; err.style.display = 'block'; return; }
  try {
    const r = await fetch(API_BASE + '/api/v1/portal/change-password', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-SOC-Key': SOC_KEY},
      body: JSON.stringify({tenant: slug, old_password: oldPw, new_password: newPw})
    });
    const d = await r.json();
    if (d.success) {
      ok.style.display = 'block';
      document.getElementById('pw-old').value = '';
      document.getElementById('pw-new').value = '';
      document.getElementById('pw-new2').value = '';
    } else {
      err.textContent = d.error || 'Chyba';
      err.style.display = 'block';
    }
  } catch {
    err.textContent = 'Chyba pripojenia';
    err.style.display = 'block';
  }
}

// ── Reset token z URL ─────────────────────────────────────────
(function () {
  const params = new URLSearchParams(window.location.search);
  const token = params.get('reset_token');
  if (token) {
    window._resetToken = token;
    document.getElementById('modal-newpw').style.display = 'flex';
  }
})();
