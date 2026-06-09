'use strict';

const API_BASE = 'https://swprobe.innovativeit.sk';
const SOC_KEY = 'soc-key-prod-b153c299eea49ca8e7b3c791069fe6ad3af5efefcae58c1c';

let selectedOS = 'windows';
let regData = {};
let dashRefreshInterval = null;
let _currentTenantSlug = null;

// ── Nav scroll effect ─────────────────────────────────────────
window.addEventListener('scroll', () => {
  document.getElementById('main-nav').classList.toggle('scrolled', window.scrollY > 20);
});

// ── Page switching ────────────────────────────────────────────
function showPage(pg) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById('pg-' + pg).classList.add('active');
  window.scrollTo(0, 0);
  const canvas = document.getElementById('nodes-canvas');
  if (canvas) canvas.style.display = pg === 'landing' ? 'block' : 'none';
  const isDash = pg === 'dashboard';
  document.getElementById('nav-links-public').style.display = isDash ? 'none' : 'flex';
  document.getElementById('nav-links-dash').style.display = isDash ? 'flex' : 'none';
  if (pg === 'dashboard') {
    const tenant = _currentTenantSlug || window._dashTenant || 'c001';
    loadDashboard(tenant);
    if (dashRefreshInterval) clearInterval(dashRefreshInterval);
    dashRefreshInterval = setInterval(() => loadDashboard(tenant), 60000);
    const n = regData.name || 'Demo Zákazník';
    const c = regData.company || 'firma.sk';
    document.getElementById('dash-username').textContent = n;
    document.getElementById('dash-greeting').textContent = n.split(' ')[0];
    document.getElementById('dash-usermeta').textContent = c + ' · SOC';
  }
  if (pg === 'register') {
    document.querySelectorAll('.register-step').forEach(s => s.classList.remove('active'));
    document.getElementById('rstep-1').classList.add('active');
  }
}

function scrollToSection(id) {
  const el = document.getElementById(id);
  if (!el) return;
  const offset = el.getBoundingClientRect().top + window.pageYOffset - 72;
  window.scrollTo({top: Math.max(0, offset), behavior: 'smooth'});
}

// ── Dashboard view switching ──────────────────────────────────
function showDash(view, el) {
  document.querySelectorAll('.dash-view').forEach(v => v.classList.remove('active'));
  document.querySelectorAll('.sidebar-nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById('dv-' + view).classList.add('active');
  if (el) el.classList.add('active');
  if (view === 'notifications') loadNotifications();
  if (view === 'devices') loadDevices();
}

// ── Clock in dashboard ────────────────────────────────────────
setInterval(() => {
  const el = document.getElementById('dash-time-sub');
  if (el) el.textContent = 'Posledná aktualizácia: ' + new Date().toLocaleTimeString('sk-SK', {hour12: false});
}, 30000);

// ── Registration flow ─────────────────────────────────────────
function regNext(step) {
  if (step === 2) {
    regData.name = document.getElementById('reg-name').value || 'Ján Novák';
    regData.email = document.getElementById('reg-email').value || 'jan@firma.sk';
    regData.company = document.getElementById('reg-company').value || 'Firma s.r.o.';
    regData.phone = document.getElementById('reg-phone').value;
  }
  if (step === 3) {
    document.getElementById('conf-name').textContent = regData.name;
    document.getElementById('conf-email').textContent = regData.email;
    document.getElementById('conf-company').textContent = regData.company;
    document.getElementById('conf-os').textContent = selectedOS === 'windows' ? 'Windows' : 'Linux';
    document.getElementById('conf-notify').textContent = document.getElementById('reg-notify').value;
  }
  document.querySelectorAll('.register-step').forEach(s => s.classList.remove('active'));
  document.getElementById('rstep-' + step).classList.add('active');
}

function selectOS(os) {
  selectedOS = os;
  document.getElementById('os-win').classList.toggle('selected', os === 'windows');
  document.getElementById('os-lin').classList.toggle('selected', os === 'linux');
}

async function doRegister() {
  const btn = document.querySelector('#rstep-3 .reg-btn');
  btn.textContent = 'Vytvára sa účet...';
  btn.disabled = true;
  const pw = document.getElementById('reg-password').value;
  const pw2 = document.getElementById('reg-password2').value;
  const pwErr = document.getElementById('reg-pw-error');
  pwErr.style.display = 'none';
  if (!pw || pw.length < 8) {
    pwErr.textContent = 'Heslo musí mať aspoň 8 znakov';
    pwErr.style.display = 'block';
    btn.textContent = 'Vytvoriť účet a stiahnuť Probe';
    btn.disabled = false;
    return;
  }
  if (pw !== pw2) {
    pwErr.textContent = 'Heslá sa nezhodujú';
    pwErr.style.display = 'block';
    btn.textContent = 'Vytvoriť účet a stiahnuť Probe';
    btn.disabled = false;
    return;
  }
  try {
    const r = await fetch(API_BASE + '/api/v1/swprobe/register', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-SOC-Key': SOC_KEY},
      body: JSON.stringify({
        name: regData.name, email: regData.email, company: regData.company,
        phone: regData.phone || '', notification_channel: document.getElementById('reg-notify').value || 'email',
        language: 'sk', password: pw
      })
    });
    const {status, data} = await r.json().then(d => ({status: r.status, data: d}));
    if (status === 201) {
      window._regSlug = data.tenant_slug;
      window._dashTenant = data.tenant_slug;
      window._regOS = selectedOS || 'windows';
      document.querySelectorAll('.register-step').forEach(s => s.classList.remove('active'));
      document.getElementById('rstep-success').classList.add('active');
    } else {
      btn.textContent = 'Chyba: ' + (data.error || 'Skúste znova');
      btn.disabled = false;
    }
  } catch {
    btn.textContent = 'Chyba spojenia';
    btn.disabled = false;
  }
}

async function doDownload(os) {
  const btn = event.target.closest('button');
  const orig = btn.innerHTML;
  const slug = window._regSlug || '';
  const dlOS = os || (window._regOS || 'windows');
  if (!slug) { btn.innerHTML = 'Chyba: slug chýba'; return; }
  btn.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg> Pripravujem...';
  btn.disabled = true;
  try {
    const r = await fetch(API_BASE + '/api/v1/swprobe/token?tenant=' + slug + '&os=' + dlOS, {
      headers: {'X-SOC-Key': SOC_KEY}
    });
    const d = await r.json();
    if (d.url) {
      window.location.href = API_BASE + d.url;
      btn.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg> Stiahnuté!';
      setTimeout(() => { btn.innerHTML = orig; btn.disabled = false; }, 3000);
    } else {
      btn.innerHTML = 'Probe sa buduje, skúste o chvíľu';
      setTimeout(() => { btn.innerHTML = orig; btn.disabled = false; }, 3000);
    }
  } catch {
    btn.innerHTML = 'Chyba spojenia';
    setTimeout(() => { btn.innerHTML = orig; btn.disabled = false; }, 2000);
  }
}

// ── Partner Inquiry ───────────────────────────────────────────
function submitPartnerInquiry() {
  const name = document.getElementById('pi-name').value || '';
  const company = document.getElementById('pi-company').value || '';
  const email = document.getElementById('pi-email').value || '';
  const phone = document.getElementById('pi-phone').value || '';
  const clients = document.getElementById('pi-clients').value || '';
  const msg = document.getElementById('pi-msg');
  const btn = document.getElementById('pi-btn');
  if (!name.trim() || !company.trim() || !email.trim()) {
    msg.style.display = 'block';
    msg.style.background = 'rgba(248,113,113,.1)';
    msg.style.color = '#f87171';
    msg.textContent = 'Vyplnte povinné polia: Meno, Firma, Email.';
    return;
  }
  btn.disabled = true;
  btn.textContent = 'Odosielam...';
  msg.style.display = 'none';
  fetch(API_BASE + '/api/v1/partner/register', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name, company, email, phone, notes: clients ? 'Potenciálnych klientov: ' + clients : ''})
  })
  .then(r => r.json())
  .then(d => {
    msg.style.display = 'block';
    if (d.success || d.message) {
      msg.style.background = 'rgba(34,197,94,.1)';
      msg.style.color = '#4ade80';
      msg.textContent = 'Ďakujeme! Budeme vás kontaktovať do 24 hodín.';
      btn.textContent = 'Odoslané';
      ['pi-name', 'pi-company', 'pi-email', 'pi-phone', 'pi-clients'].forEach(id => { document.getElementById(id).value = ''; });
    } else {
      msg.style.background = 'rgba(248,113,113,.1)';
      msg.style.color = '#f87171';
      msg.textContent = d.error || 'Chyba pri odosielaní.';
      btn.disabled = false;
      btn.textContent = 'Odoslať žiadosť';
    }
  })
  .catch(() => {
    msg.style.display = 'block';
    msg.style.background = 'rgba(248,113,113,.1)';
    msg.style.color = '#f87171';
    msg.textContent = 'Sieťová chyba.';
    btn.disabled = false;
    btn.textContent = 'Odoslať žiadosť';
  });
}

function togglePw(id, btn) {
  const inp = document.getElementById(id);
  const show = inp.type === 'password';
  inp.type = show ? 'text' : 'password';
  const eyeOpen = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
  const eyeClosed = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';
  btn.innerHTML = show ? eyeClosed : eyeOpen;
}
