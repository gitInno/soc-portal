#!/usr/bin/env python3
# SOC SW Probe API v1.0
# Flask API pre download SW Probe balickov
# Port: 5050 | Auth: X-SOC-Key header

from flask import Flask, request, jsonify, send_file, abort, redirect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import json
import subprocess
import secrets
import time
import psycopg2
from datetime import datetime
import bcrypt
import smtplib, ssl as _ssl
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText as MIMETextEmail
import io
from fpdf import FPDF
import requests as _requests_lib

app = Flask(__name__)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://"
)

ALLOWED_ORIGINS = {
    "https://portal.innovativeit.sk",
    "https://portal-dev.innovativeit.sk",
    "https://soc-dev.innovativeit.sk",
}

@app.after_request
def add_cors_headers(response):
    from flask import request as _req
    origin = _req.headers.get("Origin", "")
    if origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
    else:
        response.headers["Access-Control-Allow-Origin"] = "https://portal.innovativeit.sk"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-SOC-Key"
    return response

@app.route("/api/v1/probe/heartbeat", methods=["OPTIONS"])
@app.route("/api/v1/portal/login", methods=["OPTIONS"])
@app.route("/api/v1/swprobe/register", methods=["OPTIONS"])
@app.route("/api/v1/swprobe/token", methods=["OPTIONS"])
@app.route("/api/v1/swprobe/status", methods=["OPTIONS"])
@app.route("/api/v1/portal/dashboard", methods=["OPTIONS"])
@app.route("/api/v1/portal/notify", methods=["OPTIONS"])
@app.route("/api/v1/report/generate", methods=["OPTIONS"])
@app.route("/api/v1/portal/alerts", methods=["OPTIONS"])
@app.route("/api/v1/portal/auth", methods=["OPTIONS"])
@app.route("/api/v1/auth/login", methods=["OPTIONS"])
@app.route("/api/v1/auth/reset-password-request", methods=["OPTIONS"])
@app.route("/api/v1/auth/reset-password", methods=["OPTIONS"])
@app.route("/api/v1/portal/change-password", methods=["OPTIONS"])
@app.route("/api/v1/portal/notifications", methods=["OPTIONS"])
@app.route("/api/v1/portal/devices", methods=["OPTIONS"])
def handle_options(**kwargs):
    return "", 204

API_KEY = "soc-key-prod-b153c299eea49ca8e7b3c791069fe6ad3af5efefcae58c1c"
PACKAGES_DIR = "/opt/soc/swprobe/packages"

# SMTP konfig
SMTP_HOST = "smtp.innovativeit.sk"
SMTP_HOST_FALLBACK = "45.13.137.117"
SMTP_PORT = 587
SMTP_USER = "portal@innovativeit.sk"
SMTP_PASS = ""
SMTP_FROM = "portal@innovativeit.sk"

def send_registration_email(to_email, name, tenant_slug):
    win_url = f"https://swprobe.innovativeit.sk/api/v1/swprobe/public-register?slug={tenant_slug}&os=windows"
    lin_url = f"https://swprobe.innovativeit.sk/api/v1/swprobe/public-register?slug={tenant_slug}&os=linux"
    subject = "SOC Portal  -  váš bezpečnostný monitoring je pripravený"
    body_html = f"""
<html><body style="font-family:Arial,sans-serif;color:#222;max-width:600px;margin:0 auto">
<div style="background:#0f172a;padding:32px;border-radius:8px 8px 0 0">
  <h1 style="color:#38bdf8;margin:0">SOC Portal</h1>
  <p style="color:#94a3b8;margin:8px 0 0">Bezpečnostný monitoring</p>
</div>
<div style="background:#f8fafc;padding:32px;border-radius:0 0 8px 8px;border:1px solid #e2e8f0">
  <h2>Vitajte, {name}!</h2>
  <p>Váš SOC monitoring účet bol úspešne vytvorený. SW Probe je pripravená na stiahnutie.</p>
  <p><strong>Stiahnite si SW Probe:</strong></p>
  <p>
    <a href="{win_url}" style="background:#38bdf8;color:#0f172a;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold;display:inline-block;margin:4px">
      Windows (.exe)
    </a>
    &nbsp;
    <a href="{lin_url}" style="background:#1e293b;color:#38bdf8;padding:12px 24px;border-radius:6px;text-decoration:none;font-weight:bold;display:inline-block;margin:4px;border:1px solid #38bdf8">
      Linux (.deb)
    </a>
  </p>
  <p style="color:#64748b;font-size:14px">
    Po inštalácii sa SW Probe automaticky pripojí k SOC infraštruktúre.<br>
    Váš identifikátor: <strong>{tenant_slug}</strong>
  </p>
  <hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0">
  <p style="color:#94a3b8;font-size:12px">InnovativeIT SOC Portal | portal@innovativeit.sk</p>
</div>
</body></html>"""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg.attach(MIMETextEmail(body_html, "html"))
    return send_email(to_email, subject, body_html=body_html)
BUILD_SCRIPT = "/opt/soc/swprobe/soc-build-swprobe.sh"

DB_CONFIG = {
    "host": "172.21.0.3",
    "port": 5432,
    "database": "soc",
    "user": "soc_admin",
    "password": "SocPg2026RAND=a9fb4ccd137146cd{RAND}"
}

# Jednorazove tokeny: {token: {tenant, os, expires}}
tokens = {}

# WG IP pool - next available
WG_IP_START = 6  # 10.0.0.6+

def send_email(to_email, subject, body_text=None, body_html=None):
    import ssl as _ssl_fn
    from email.mime.multipart import MIMEMultipart as _MM
    from email.mime.text import MIMEText as _MT
    if body_html:
        msg = _MM("alternative")
        if body_text:
            msg.attach(_MT(body_text, "plain", "utf-8"))
        msg.attach(_MT(body_html, "html", "utf-8"))
    else:
        msg = _MT(body_text or "", "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    for host in [SMTP_HOST, SMTP_HOST_FALLBACK]:
        try:
            ctx = _ssl_fn.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = _ssl_fn.CERT_NONE
            with smtplib.SMTP(host, SMTP_PORT, timeout=10) as s:
                s.ehlo()
                s.starttls(context=ctx)
                s.ehlo()
                s.login(SMTP_USER, SMTP_PASS)
                s.sendmail(SMTP_FROM, [to_email], msg.as_string())
            print("Email odoslany cez " + host, flush=True)
            return True
        except Exception as e:
            print("SMTP FAIL " + host + ": " + str(e), flush=True)
    return False


def check_auth():
    key = request.headers.get("X-SOC-Key", "")
    if key != API_KEY:
        abort(401, "Unauthorized")

def get_db():
    return psycopg2.connect(**DB_CONFIG)

def get_tenant(slug):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, slug, wg_ip, name FROM tenants WHERE slug=%s AND active=true", (slug,))
    row = cur.fetchone()
    conn.close()
    return row

def next_wg_ip():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT wg_ip FROM tenants WHERE wg_ip IS NOT NULL ORDER BY wg_ip")
    used = [r[0] for r in cur.fetchall()]
    conn.close()
    for i in range(WG_IP_START, 254):
        ip = f"10.0.0.{i}"
        if ip not in used:
            return ip
    return None

def get_package_path(tenant_slug, os_type):
    if os_type == "windows":
        # Preferuj ZIP, fallback na EXE
        for ext in ("zip", "exe"):
            fname = f"swprobe-{tenant_slug}_1.0.1_windows.{ext}"
            path = os.path.join(PACKAGES_DIR, fname)
            if os.path.exists(path):
                return path
        return os.path.join(PACKAGES_DIR, f"swprobe-{tenant_slug}_1.0.1_windows.zip")
    else:
        return os.path.join(PACKAGES_DIR, f"swprobe-{tenant_slug}_1.0.1_amd64.deb")

# ─────────────────────────────────────────
# GET /api/v1/swprobe/download
# ─────────────────────────────────────────
@app.route("/api/v1/swprobe/download")
def download():
    tenant_slug = request.args.get("tenant", "")
    os_type = request.args.get("os", "").lower()

    # OS detekcia z User-Agent ak nie je zadany
    if not os_type:
        ua = request.headers.get("User-Agent", "").lower()
        os_type = "linux" if "linux" in ua else "windows"

    if not tenant_slug:
        return jsonify({"error": "tenant parameter required"}), 400

    tenant = get_tenant(tenant_slug)
    if not tenant:
        return jsonify({"error": f"Tenant '{tenant_slug}' not found"}), 404

    pkg_path = get_package_path(tenant_slug, os_type)
    if not os.path.exists(pkg_path):
        return jsonify({
            "error": "Package not built yet",
            "hint": f"POST /api/v1/swprobe/build with tenant_id first"
        }), 404

    return send_file(
        pkg_path,
        as_attachment=True,
        download_name=os.path.basename(pkg_path)
    )

# ─────────────────────────────────────────
# GET /api/v1/swprobe/token
# ─────────────────────────────────────────
@app.route("/api/v1/swprobe/token")
def get_token():
    check_auth()
    tenant_slug = request.args.get("tenant", "")
    os_type = request.args.get("os", "windows").lower()

    if not tenant_slug:
        return jsonify({"error": "tenant parameter required"}), 400

    tenant = get_tenant(tenant_slug)
    if not tenant:
        return jsonify({"error": f"Tenant '{tenant_slug}' not found"}), 404

    pkg_path = get_package_path(tenant_slug, os_type)
    if not os.path.exists(pkg_path):
        return jsonify({
            "error": "Package not built yet",
            "built": False
        }), 404

    token = secrets.token_urlsafe(32)
    tokens[token] = {
        "tenant": tenant_slug,
        "os": os_type,
        "expires": time.time() + 300  # 5 minut
    }

    return jsonify({
        "token": token,
        "url": f"/api/v1/swprobe/public?token={token}",
        "expires_in": 300,
        "tenant": tenant_slug,
        "os": os_type
    })

# ─────────────────────────────────────────
# GET /api/v1/swprobe/public (bez auth, s tokenom)
# ─────────────────────────────────────────
@app.route("/api/v1/swprobe/public")
def public_download():
    token = request.args.get("token", "")
    if not token or token not in tokens:
        abort(403, "Invalid or expired token")

    t = tokens[token]
    if time.time() > t["expires"]:
        del tokens[token]
        abort(403, "Token expired")

    tenant_slug = t["tenant"]
    os_type = t["os"]

    # Jednorazovy - zmazat
    del tokens[token]

    pkg_path = get_package_path(tenant_slug, os_type)
    if not os.path.exists(pkg_path):
        abort(404, "Package not found")

    return send_file(
        pkg_path,
        as_attachment=True,
        download_name=os.path.basename(pkg_path)
    )

# ─────────────────────────────────────────
# POST /api/v1/swprobe/build
# ─────────────────────────────────────────
@app.route("/api/v1/swprobe/build", methods=["POST"])
def build():
    check_auth()
    data = request.get_json() or {}
    tenant_id = data.get("tenant_id", "")
    tenant_slug = data.get("tenant", "")

    # Podpor aj slug priamo
    if tenant_slug:
        tenant = get_tenant(tenant_slug)
    elif tenant_id:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, slug, wg_ip, name FROM tenants WHERE id=%s", (tenant_id,))
        tenant = cur.fetchone()
        conn.close()
        if tenant:
            tenant_slug = tenant[1]
    else:
        return jsonify({"error": "tenant or tenant_id required"}), 400

    if not tenant:
        return jsonify({"error": "Tenant not found"}), 404

    # Pridelit WG IP ak nema
    wg_ip = tenant[2]
    if not wg_ip:
        wg_ip = next_wg_ip()
        if not wg_ip:
            return jsonify({"error": "No free WG IP addresses"}), 500

    # Spusti build skript
    result = subprocess.run(
        ["sudo", "bash", BUILD_SCRIPT, tenant_slug, wg_ip, "auto"],
        capture_output=True,
        text=True,
        timeout=120
    )

    if result.returncode != 0:
        return jsonify({
            "error": "Build failed",
            "details": result.stderr[-500:]
        }), 500

    return jsonify({
        "success": True,
        "tenant": tenant_slug,
        "wg_ip": wg_ip,
        "packages": {
            "windows": f"swprobe-{tenant_slug}_1.0.1_windows.zip",
            "linux": f"swprobe-{tenant_slug}_1.0.1_amd64.deb"
        },
        "download_url": f"https://swprobe.innovativeit.sk/api/v1/swprobe/download?tenant={tenant_slug}"
    })

# ─────────────────────────────────────────
# POST /api/v1/swprobe/register
# Registracia noveho tenanta z portalu
# ─────────────────────────────────────────

def swprobe_register_impl(data):
    """Spolocna logika registracie tenanta. Volana z register() aj partner_tenant_register().
    data["_partner_id"] je volitelne — priradi tenanta k partnerovi."""
    required = ["name", "email", "company", "password"]
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"Field '{field}' is required"}), 400

    if len(data["password"]) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    email = data["email"].lower()
    slug = email.split("@")[0].replace(".", "-").replace("+", "-")[:30]
    slug = ''.join(c for c in slug if c.isalnum() or c == '-')

    wg_ip = next_wg_ip()
    if not wg_ip:
        return jsonify({"error": "No free WG IP addresses"}), 500

    partner_id = data.get("_partner_id") or None

    try:
        conn = get_db()
        cur = conn.cursor()

        cur.execute("SELECT id FROM tenants WHERE slug=%s OR email=%s", (slug, email))
        if cur.fetchone():
            conn.close()
            return jsonify({"error": "Email already registered"}), 409

        pw_hash = bcrypt.hashpw(data["password"].encode(), bcrypt.gensalt()).decode()

        cur.execute("""
            INSERT INTO tenants
                (name, slug, email, phone, company, contact_name,
                 notification_channel, wg_ip, language, sla_tier,
                 test_account, active, password_hash, partner_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, slug
        """, (
            data.get("company", data["name"]),
            slug,
            email,
            data.get("phone", ""),
            data.get("company", ""),
            data.get("name", ""),
            data.get("notification_channel", "email"),
            wg_ip,
            data.get("language", "sk"),
            "basic",
            True,
            True,
            pw_hash,
            partner_id
        ))

        tenant_id, tenant_slug = cur.fetchone()

        cur.execute("""
            INSERT INTO tenant_notifications (tenant_id, channel, address, label, active)
            VALUES (%s, 'email', %s, 'Primárny email', true)
        """, (tenant_id, email))

        conn.commit()
        conn.close()

        subprocess.Popen(
            ["sudo", "bash", BUILD_SCRIPT, tenant_slug, wg_ip, "auto"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        threading.Thread(
            target=send_registration_email,
            args=(email, data.get("name", ""), tenant_slug),
            daemon=True
        ).start()

        return jsonify({
            "success": True,
            "tenant_id": str(tenant_id),
            "tenant_slug": tenant_slug,
            "wg_ip": wg_ip,
            "message": "Registration successful. Probe is being built.",
            "download_ready_in": 60,
            "download_url": f"https://swprobe.innovativeit.sk/api/v1/swprobe/public-register?slug={tenant_slug}"
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/v1/swprobe/register", methods=["POST"])
def register():
    check_auth()
    return swprobe_register_impl(request.get_json() or {})

# ─────────────────────────────────────────

# GET /api/v1/swprobe/public-register (bez auth, z emailu)
# Generuje token a presmeruje na download
@app.route("/api/v1/swprobe/public-register")
def public_register_download():
    tenant_slug = request.args.get("slug", "")
    os_type = request.args.get("os", "windows")
    if not tenant_slug:
        return "Chýba parameter slug", 400
    pkg_path = get_package_path(tenant_slug, os_type)
    if not os.path.exists(pkg_path):
        return "Probe pre tohto zákazníka nie je dostupná. Kontaktujte support@innovativeit.sk", 404
    token = secrets.token_urlsafe(32)
    expires = time.time() + 300
    tokens[token] = {
        "tenant": tenant_slug,
        "os": os_type,
        "expires": expires
    }
    return redirect(f"/api/v1/swprobe/public?token={token}", code=302)

# GET /api/v1/swprobe/status
# ─────────────────────────────────────────
@app.route("/api/v1/swprobe/status")
def status():
    check_auth()
    tenant_slug = request.args.get("tenant", "")
    if not tenant_slug:
        return jsonify({"error": "tenant required"}), 400

    win_path = get_package_path(tenant_slug, "windows")
    lin_path = get_package_path(tenant_slug, "linux")

    return jsonify({
        "tenant": tenant_slug,
        "windows": {
            "built": os.path.exists(win_path),
            "size": os.path.getsize(win_path) if os.path.exists(win_path) else 0
        },
        "linux": {
            "built": os.path.exists(lin_path),
            "size": os.path.getsize(lin_path) if os.path.exists(lin_path) else 0
        }
    })

# ─────────────────────────────────────────

# ─────────────────────────────────────────
# GET /api/v1/portal/dashboard
# Dashboard data pre customer portal
# ─────────────────────────────────────────
@app.route("/api/v1/portal/dashboard")
def portal_dashboard():
    tenant_slug = request.args.get("tenant", "")
    if not tenant_slug:
        return jsonify({"error": "tenant required"}), 400
    try:
        conn = get_db()
        cur = conn.cursor()

        # Tenant info
        cur.execute("SELECT id, name, company FROM tenants WHERE slug=%s AND active=true", (tenant_slug,))
        tenant = cur.fetchone()
        if not tenant:
            return jsonify({"error": "Tenant not found"}), 404
        tenant_id, tenant_name, tenant_company = tenant

        # Alerty poslednych 24h
        cur.execute("""
            SELECT id, rule_level, description, agent_name, source_ip::text,
                   severity, created_at, ai_summary, status
            FROM alerts
            WHERE tenant_id=%s AND created_at > now() - interval '24 hours'
            ORDER BY created_at DESC LIMIT 50
        """, (tenant_id,))
        rows = cur.fetchall()
        alerts = []
        for r in rows:
            alerts.append({
                "id": str(r[0]),
                "rule_level": r[1],
                "description": r[2],
                "agent_name": r[3],
                "source_ip": r[4],
                "severity": r[5] or ("critical" if r[1]>=12 else "high" if r[1]>=8 else "medium" if r[1]>=5 else "low"),
                "timestamp": r[6].isoformat() if r[6] else None,
                "ai_summary": r[7],
                "status": r[8]
            })

        # Pocty
        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE created_at > now() - interval '24 hours') as today,
                COUNT(*) FILTER (WHERE created_at > now() - interval '24 hours'
                    AND rule_level >= 12) as critical,
                COUNT(*) FILTER (WHERE created_at > now() - interval '48 hours'
                    AND created_at <= now() - interval '24 hours') as yesterday
            FROM alerts WHERE tenant_id=%s
        """, (tenant_id,))
        counts = cur.fetchone()

        # Probe heartbeat
        cur.execute("""
            SELECT probe_hostname, last_seen, ip_address, version
            FROM probe_heartbeats
            WHERE tenant_id=%s
            ORDER BY last_seen DESC LIMIT 1
        """, (tenant_id,))
        hb = cur.fetchone()
        probe = None
        if hb:
            import datetime as dt
            age_sec = (dt.datetime.now(dt.timezone.utc) - hb[1]).total_seconds()
            probe = {
                "hostname": hb[0],
                "last_seen": hb[1].isoformat(),
                "ip": hb[2],
                "version": hb[3],
                "online": age_sec < 300
            }

        conn.close()
        return jsonify({
            "tenant": tenant_slug,
            "name": tenant_name,
            "company": tenant_company,
            "alerts": alerts,
            "stats": {
                "alerts_24h": counts[0] or 0,
                "critical_24h": counts[1] or 0,
                "alerts_yesterday": counts[2] or 0
            },
            "probe": probe
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────
# POST /api/v1/portal/notify
# Multi-channel notifikacie podla v_active_notifications
# ─────────────────────────────────────────
@app.route("/api/v1/portal/notify", methods=["POST"])
def portal_notify():
    data = request.get_json() or {}
    tenant_id = data.get("tenant_id","")
    severity  = data.get("severity","high")
    summary   = data.get("summary","")
    description = data.get("description","")
    agent_name  = data.get("agent_name","")
    recommended_action = data.get("recommended_action","")

    if not tenant_id:
        return jsonify({"error": "tenant_id required"}), 400

    results = []
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT channel, address, label
            FROM v_active_notifications
            WHERE tenant_id=%s::uuid AND allowed=true
        """, (tenant_id,))
        notifications = cur.fetchall()
        conn.close()

        sev_emoji = {"critical":"🔴","high":"🟠","medium":"🟡","low":"🟢"}.get(severity,"🔵")
        msg_text = (
            f"{sev_emoji} <b>SOC ALERT</b>\n\n"
            f"<b>Severity:</b> {severity}\n"
            f"<b>Agent:</b> {agent_name}\n"
            f"<b>Popis:</b> {description}\n"
            f"<b>Zhrnutie:</b> {summary}\n"
            f"<b>Odporúčaná akcia:</b> {recommended_action}"
        )

        for channel, address, label in notifications:
            if channel == "telegram":
                try:
                    import json
                    import urllib.request as ur
                    BOT_TOKEN = "8608991033:AAEgLkTRp0hlQ1BHIE1s6dPCXtsrmAOc71Q"
                    tg_data = json.dumps({
                        "chat_id": address,
                        "text": msg_text,
                        "parse_mode": "HTML"
                    }).encode()
                    req = ur.Request(
                        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                        data=tg_data,
                        headers={"Content-Type": "application/json"}
                    )
                    ur.urlopen(req, timeout=10)
                    results.append({"channel":"telegram","address":address,"status":"ok"})
                except Exception as e:
                    results.append({"channel":"telegram","address":address,"status":f"error:{e}"})

            elif channel == "email":
                try:
                    msg_html = f"""
<html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
<div style="background:#0f172a;padding:24px;border-radius:8px 8px 0 0">
  <h2 style="color:#f87171;margin:0">{sev_emoji} SOC Alert  -  {severity.upper()}</h2>
</div>
<div style="background:#f8fafc;padding:24px;border:1px solid #e2e8f0;border-radius:0 0 8px 8px">
  <p><b>Agent:</b> {agent_name}</p>
  <p><b>Popis:</b> {description}</p>
  <p><b>AI Zhrnutie:</b> {summary}</p>
  <p><b>Odporúčaná akcia:</b> {recommended_action}</p>
  <hr style="border:none;border-top:1px solid #e2e8f0">
  <p style="color:#94a3b8;font-size:12px">InnovativeIT SOC Portal</p>
</div>
</body></html>"""
                    subject = f"[SOC Alert] {severity.upper()}  -  {description[:60]}"
                    ok = send_email(address, subject, body_html=msg_html)
                    results.append({"channel": "email", "address": address, "status": "ok" if ok else "smtp_fail"})
                except Exception as e:
                    results.append({"channel":"email","address":address,"status":f"error:{e}"})

        return jsonify({"sent": len(results), "results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# GET /health
# ─────────────────────────────────────────

@app.route("/api/v1/portal/login", methods=["GET", "POST"])
@app.route("/api/v1/portal/auth-legacy", methods=["POST"])
@limiter.limit("10 per minute")
def portal_login():
    """Legacy endpoint — deleguje na auth_login pre jednotnú logiku."""
    return auth_login()

@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})


# ============================================================
# B2B PARTNER API
# ============================================================

@app.route("/api/v1/partner/register", methods=["POST"])
def partner_register():
    data = request.get_json()
    required = ["name", "email", "company"]
    for f in required:
        if not data.get(f):
            return jsonify({"error": f"Chýba pole: {f}"}), 400

    import secrets
    raw_pw = data.get("password") or secrets.token_urlsafe(16)
    pw_hash = bcrypt.hashpw(raw_pw.encode(), bcrypt.gensalt(12)).decode()

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO partners (name, email, password_hash, company, phone, approved)
            VALUES (%s, %s, %s, %s, %s, false)
            RETURNING id, slug
        """, (data["name"], data["email"], pw_hash, data["company"], data.get("phone", "")))
        # partners nemá slug  -  opravíme
        row = cur.fetchone()
        partner_id = row[0] if row else None
        conn.commit()
        cur.close()
        conn.close()

        # Email notifikácia Super Adminovi
        send_registration_email(
            "admin@innovativeit.sk",
            "Nova ziadost o partnerstvo",
            "Partner " + data["name"] + " ziada o pristup. Email: " + data["email"]
        )

        return jsonify({
            "success": True,
            "message": "Žiadosť o partnerstvo odoslaná. Čakajte na schválenie.",
            "partner_id": str(partner_id)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/v1/partner/login", methods=["POST"])
@limiter.limit("10 per minute")
def partner_login():
    data = request.get_json()
    email = data.get("email", "")
    password = data.get("password", "")

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, name, company, password_hash, approved
            FROM partners WHERE email = %s
        """, (email,))
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            return jsonify({"error": "Nesprávny email alebo heslo"}), 401

        partner_id, name, company, pw_hash, approved = row

        if not bcrypt.checkpw(password.encode(), pw_hash.encode()):
            return jsonify({"error": "Nesprávny email alebo heslo"}), 401

        if not approved:
            return jsonify({"error": "Účet čaká na schválenie administrátorom"}), 403

        return jsonify({
            "success": True,
            "partner_id": str(partner_id),
            "name": name,
            "company": company
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/v1/partner/dashboard", methods=["GET"])
def partner_dashboard():
    partner_id = request.args.get("partner_id", "")
    if not partner_id:
        return jsonify({"error": "Chýba partner_id"}), 400

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT t.id, t.slug, t.name, t.company, t.email, t.wg_ip,
                   t.test_account, t.expires_at, t.created_at,
                   COUNT(DISTINCT a.id) as alert_count,
                   MAX(ph.last_seen) as last_heartbeat
            FROM tenants t
            LEFT JOIN alerts a ON a.tenant_id = t.id
                AND a.created_at > NOW() - INTERVAL '24 hours'
            LEFT JOIN probe_heartbeats ph ON ph.tenant_id = t.id
            WHERE t.partner_id = %s
            GROUP BY t.id
            ORDER BY t.created_at DESC
        """, (partner_id,))
        tenants = []
        for row in cur.fetchall():
            tenants.append({
                "id": str(row[0]),
                "slug": row[1],
                "name": row[2],
                "company": row[3],
                "email": row[4],
                "wg_ip": row[5],
                "test_account": row[6],
                "expires_at": str(row[7]) if row[7] else None,
                "created_at": str(row[8]),
                "alerts_24h": row[9],
                "last_heartbeat": str(row[10]) if row[10] else None
            })
        cur.close()
        conn.close()
        return jsonify({"tenants": tenants, "total": len(tenants)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/v1/partner/tenant/register", methods=["POST"])
def partner_tenant_register():
    """Partner registruje zákazníka  -  rovnaká logika ako /register ale s partner_id"""
    data = request.get_json()
    partner_id = data.get("partner_id", "")
    if not partner_id:
        return jsonify({"error": "Chýba partner_id"}), 400

    # Zavolaj existujúcu register logiku s partner_id
    data["_partner_id"] = partner_id
    return swprobe_register_impl(data)


# ============================================================
# OPERATOR API (Super Admin)
# ============================================================

OPERATOR_PASSWORD_HASH = bcrypt.hashpw(b"OperatorSOC2026!", bcrypt.gensalt(12)).decode()


@app.route("/api/v1/operator/create", methods=["POST"])
def operator_create():
    data = request.get_json()
    role = data.get("role", "partner")  # partner alebo operator
    required = ["name", "email", "company", "password"]
    for f in required:
        if not data.get(f):
            return jsonify({"error": f"Chyba pole: {f}"}), 400
    if role not in ("partner", "operator"):
        return jsonify({"error": "Neplatna rola"}), 400
    import secrets
    raw_pw = data.get("password") or secrets.token_urlsafe(16)
    pw_hash = bcrypt.hashpw(raw_pw.encode(), bcrypt.gensalt(12)).decode()
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO partners (name, email, password_hash, company, phone, approved, role)
            VALUES (%s, %s, %s, %s, %s, true, %s)
            RETURNING id, slug
        """, (data["name"], data["email"], pw_hash, data["company"], data.get("phone", ""), role))
        row = cur.fetchone()
        partner_id = row[0] if row else None
        conn.commit()
        cur.close()
        conn.close()
        send_registration_email(
            data["email"],
            "Vitajte v SOC platforme",
            f"Vas ucet bol vytvoreny.\nEmail: {data['email']}\nHeslo: {data['password']}\nRola: {role}"
        )
        return jsonify({"success": True, "id": str(partner_id), "role": role})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/v1/operator/login", methods=["POST"])
@limiter.limit("10 per minute")
def operator_login():
    data = request.get_json()
    password = data.get("password", "")
    if bcrypt.checkpw(password.encode(), OPERATOR_PASSWORD_HASH.encode()):
        return jsonify({"success": True, "role": "operator"})
    return jsonify({"error": "Nesprávne heslo"}), 401


@app.route("/api/v1/operator/dashboard", methods=["GET"])
def operator_dashboard():
    check_auth()
    try:
        conn = get_db()
        cur = conn.cursor()

        # Všetci partneri
        cur.execute("""
            SELECT p.id, p.name, p.company, p.email, p.approved, p.created_at,
                   COUNT(t.id) as tenant_count
            FROM partners p
            LEFT JOIN tenants t ON t.partner_id = p.id
            GROUP BY p.id
            ORDER BY p.created_at DESC
        """)
        partners = []
        for row in cur.fetchall():
            partners.append({
                "id": str(row[0]),
                "name": row[1],
                "company": row[2],
                "email": row[3],
                "approved": row[4],
                "created_at": str(row[5]),
                "tenant_count": row[6]
            })

        # Všetci tenanty
        cur.execute("""
            SELECT t.slug, t.name, t.company, t.wg_ip, t.test_account,
                   t.created_at, p.name as partner_name,
                   COUNT(a.id) as alerts_24h
            FROM tenants t
            LEFT JOIN partners p ON p.id = t.partner_id
            LEFT JOIN alerts a ON a.tenant_id = t.id
                AND a.created_at > NOW() - INTERVAL '24 hours'
            GROUP BY t.id, p.name
            ORDER BY t.created_at DESC
        """)
        tenants = []
        for row in cur.fetchall():
            tenants.append({
                "slug": row[0],
                "name": row[1],
                "company": row[2],
                "wg_ip": row[3],
                "test_account": row[4],
                "created_at": str(row[5]),
                "partner": row[6] or "InnovativeIT (priamy)",
                "alerts_24h": row[7]
            })

        cur.close()
        conn.close()

        return jsonify({
            "partners": partners,
            "tenants": tenants,
            "stats": {
                "total_partners": len(partners),
                "total_tenants": len(tenants),
                "approved_partners": sum(1 for p in partners if p["approved"])
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/v1/operator/partner/approve", methods=["POST"])
def operator_partner_approve():
    check_auth()
    data = request.get_json()
    partner_id = data.get("partner_id", "")
    approved = data.get("approved", True)

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            UPDATE partners SET approved = %s WHERE id = %s
            RETURNING name, email
        """, (approved, partner_id))
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if row and approved:
            send_registration_email(
                row[1],
                "Váš partnerský účet bol schválený",
                f"Dobrý deň {row[0]},\n\nVáš partnerský účet bol schválený.\nPrihláste sa na: https://portal.innovativeit.sk/partner"
            )

        return jsonify({"success": True, "approved": approved})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# UNIFIED AUTH API
# ============================================================

@app.route("/api/v1/auth/login", methods=["POST"])
@app.route("/api/v1/portal/auth", methods=["POST"])
@limiter.limit("10 per minute")
def auth_login():
    """Jednotný login  -  rozpozná customer/partner/operator podľa emailu"""
    data = request.get_json()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "Chýba email alebo heslo"}), 400

    profiles = []

    try:
        conn = get_db()
        cur = conn.cursor()

        # 1. Skontroluj customers (tenants)
        cur.execute("""
            SELECT id, name, slug, company, password_hash
            FROM tenants
            WHERE LOWER(email) = %s AND password_hash IS NOT NULL
        """, (email,))
        for row in cur.fetchall():
            tenant_id, name, slug, company, pw_hash = row
            if pw_hash and bcrypt.checkpw(password.encode(), pw_hash.encode()):
                profiles.append({
                    "role": "customer",
                    "id": str(tenant_id),
                    "name": name,
                    "slug": slug,
                    "company": company or name,
                    "label": f"Zákazník  -  {company or name}"
                })

        # 2. Skontroluj partners/operators
        cur.execute("""
            SELECT id, name, company, password_hash, role, approved
            FROM partners
            WHERE LOWER(email) = %s
        """, (email,))
        for row in cur.fetchall():
            partner_id, name, company, pw_hash, role, approved = row
            if pw_hash and bcrypt.checkpw(password.encode(), pw_hash.encode()):
                if not approved:
                    profiles.append({
                        "role": "pending",
                        "name": name,
                        "label": f"Čaká na schválenie  -  {company or name}"
                    })
                else:
                    label = f"{'Operator' if role == 'operator' else 'Partner'}  -  {company or name}"
                    profiles.append({
                        "role": role,
                        "id": str(partner_id),
                        "name": name,
                        "company": company,
                        "label": label
                    })

        cur.close()
        conn.close()

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    if not profiles:
        return jsonify({"error": "Nesprávny email alebo heslo"}), 401

    # Ak len jeden profil  -  priamo vrátime
    if len(profiles) == 1:
        p = profiles[0]
        if p["role"] == "pending":
            return jsonify({"error": "Účet čaká na schválenie administrátorom"}), 403
        role = p.get("role", "")
        redirect = {}
        if role == "customer": redirect = {"page": "dashboard", "slug": p.get("slug")}
        elif role == "partner": redirect = {"page": "/partner", "partner_id": p.get("id")}
        elif role == "operator": redirect = {"page": "/operator"}
        return jsonify({"success": True, "multiple": False, "role": role, "profile": p, "redirect": redirect})

    # Viac profilov  -  vrátime zoznam na výber
    # Filtruj pending z výberu
    selectable = [p for p in profiles if p["role"] != "pending"]
    if not selectable:
        return jsonify({"error": "Účet čaká na schválenie administrátorom"}), 403

    if len(selectable) == 1:
        p2 = selectable[0]
        role2 = p2.get("role", "")
        redirect2 = {}
        if role2 == "customer": redirect2 = {"page": "dashboard", "slug": p2.get("slug")}
        elif role2 == "partner": redirect2 = {"page": "/partner", "partner_id": p2.get("id")}
        elif role2 == "operator": redirect2 = {"page": "/operator"}
        return jsonify({"success": True, "multiple": False, "role": role2, "profile": p2, "redirect": redirect2})

    return jsonify({"success": True, "multiple": True, "profiles": selectable})


@app.route("/api/v1/auth/select", methods=["POST"])
def auth_select():
    import bcrypt as _bcrypt
    data = request.get_json() or {}
    email    = (data.get("email") or "").lower().strip()
    password = data.get("password") or ""
    role     = data.get("role") or ""
    pid      = data.get("profile_id") or ""

    if not all([email, password, role, pid]):
        return jsonify({"error": "email, password, role, profile_id su povinne"}), 400

    try:
        conn = get_db()
        cur = conn.cursor()

        if role == "customer":
            cur.execute("SELECT t.id, t.slug, t.name, t.password_hash FROM tenants t WHERE t.id=%s AND t.active=true", (pid,))
            row = cur.fetchone()
            conn.close()
            if not row: return jsonify({"error": "Profil nenajdeny"}), 404
            tid, slug, name, pw_hash = row
            if not pw_hash or not _bcrypt.checkpw(password.encode(), pw_hash.encode()):
                return jsonify({"error": "Nespravne heslo"}), 401
            p = {"role": "customer", "id": str(tid), "slug": slug, "name": name}
            return jsonify({"success": True, "multiple": False, "role": "customer", "profile": p, "redirect": {"page": "dashboard", "slug": slug}})

        elif role in ("partner", "operator"):
            cur.execute("SELECT id, name, password_hash, role FROM partners WHERE id=%s", (pid,))
            row = cur.fetchone()
            conn.close()
            if not row: return jsonify({"error": "Profil nenajdeny"}), 404
            pid2, pname, pw_hash, prole = row
            if not pw_hash or not _bcrypt.checkpw(password.encode(), pw_hash.encode()):
                return jsonify({"error": "Nespravne heslo"}), 401
            actual_role = prole or role
            p = {"role": actual_role, "id": str(pid2), "name": pname}
            redir = {"/operator": {"page": "/operator"}, "/partner": {"page": "/partner", "partner_id": str(pid2)}}.get("/" + actual_role, {"page": "/" + actual_role})
            return jsonify({"success": True, "multiple": False, "role": actual_role, "profile": p, "redirect": redir})

        return jsonify({"error": "Neznama rola"}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500



# ─────────────────────────────────────────
# POST /api/v1/portal/alert/<id>/status
# Zmena stavu alertu: open -> in_progress -> closed
# ─────────────────────────────────────────
VALID_STATUSES = ['open', 'in_progress', 'closed']

@app.route('/api/v1/portal/alert/<alert_id>/status', methods=['POST'])
def alert_set_status(alert_id):
    key = request.headers.get('X-SOC-Key')
    if key != API_KEY:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json() or {}
    new_status = data.get('status', '').strip()
    if new_status not in VALID_STATUSES:
        return jsonify({'error': 'Neplatny status. Povolene: open, in_progress, closed'}), 400
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            'UPDATE alerts SET status=%s WHERE id=%s RETURNING id, status',
            (new_status, alert_id)
        )
        row = cur.fetchone()
        conn.commit()
        conn.close()
        if not row:
            return jsonify({'error': 'Alert nenajdeny'}), 404
        return jsonify({'success': True, 'id': str(row[0]), 'status': row[1]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/v1/portal/alert/<alert_id>/status', methods=['OPTIONS'])
def cors_alert_status(alert_id):
    return '', 204

# ─────────────────────────────────────────
# GET /api/v1/portal/alerts
# Zoznam alertov pre tenanta s filtrovaním
# Params: tenant (slug), status (open|in_progress|closed|all), limit
# ─────────────────────────────────────────
@app.route('/api/v1/portal/alerts', methods=['GET'])
def portal_alerts_list():
    key = request.headers.get('X-SOC-Key')
    if key != API_KEY:
        return jsonify({'error': 'Unauthorized'}), 401
    tenant_slug = request.args.get('tenant', '')
    status_filter = request.args.get('status', 'open')
    limit = min(int(request.args.get('limit', 50)), 200)
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT id FROM tenants WHERE slug=%s AND active=true', (tenant_slug,))
        t = cur.fetchone()
        if not t:
            conn.close()
            return jsonify({'error': 'Tenant nenajdeny'}), 404
        tenant_id = t[0]
        if status_filter == 'all':
            cur.execute(
                'SELECT id, severity, status, summary, agent_name, created_at, recommended_action '
                'FROM alerts WHERE tenant_id=%s ORDER BY created_at DESC LIMIT %s',
                (tenant_id, limit)
            )
        else:
            cur.execute(
                'SELECT id, severity, status, summary, agent_name, created_at, recommended_action '
                'FROM alerts WHERE tenant_id=%s AND status=%s ORDER BY created_at DESC LIMIT %s',
                (tenant_id, status_filter, limit)
            )
        rows = cur.fetchall()
        conn.close()
        alerts = [
            {'id': str(r[0]), 'severity': r[1], 'status': r[2],
             'summary': r[3], 'agent_name': r[4],
             'created_at': r[5].isoformat() if r[5] else None,
             'recommended_action': r[6]}
            for r in rows
        ]
        return jsonify({'success': True, 'alerts': alerts, 'total': len(alerts)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─────────────────────────────────────────
# POST /api/v1/swprobe/webhook
# Prijíma alerty z n8n  -  validuje X-Webhook-Token hlavičku
# ─────────────────────────────────────────
@app.route('/api/v1/swprobe/webhook', methods=['POST'])
def swprobe_webhook():
    token = request.headers.get('X-Webhook-Token', '')
    if not token:
        return jsonify({'error': 'Chyba: X-Webhook-Token hlavicka chyba'}), 401
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT id, slug FROM tenants WHERE webhook_token=%s AND active=true', (token,))
        tenant = cur.fetchone()
        conn.close()
        if not tenant:
            return jsonify({'error': 'Neplatny webhook token'}), 401
        tenant_id, tenant_slug = tenant
        return jsonify({'success': True, 'tenant_id': str(tenant_id), 'slug': tenant_slug})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────
# GET /api/v1/report/generate
# NIS2 PDF report pre tenanta  -  on-demand
# Query params: tenant=<slug>&days=30|90
# Auth: X-SOC-Key header
# ─────────────────────────────────────────
REPORTS_DIR = "/opt/soc/swprobe/static/reports"


class NIS2Report(FPDF):
    def __init__(self, tenant_name, company, period_label):
        super().__init__()
        self.tenant_name = tenant_name
        self.company = company or tenant_name
        self.period_label = period_label
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(20, 20, 20)

    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(60, 60, 60)
        self.cell(0, 8, "SOC Report  |  " + self.company + "  |  " + self.period_label, align="R")
        self.ln(4)
        self.set_draw_color(180, 180, 180)
        self.line(20, self.get_y(), 190, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-18)
        self.set_draw_color(180, 180, 180)
        self.line(20, self.get_y(), 190, self.get_y())
        self.ln(2)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 6, "Strana " + str(self.page_no()) + " | InnovativeIT s.r.o. | Dokument generovany automaticky SOC platformou", align="C")

    def section_title(self, text):
        self.set_font("Helvetica", "B", 12)
        self.set_fill_color(30, 60, 120)
        self.set_text_color(255, 255, 255)
        self.cell(0, 9, "  " + text, fill=True, ln=True)
        self.set_text_color(0, 0, 0)
        self.ln(3)

    def kv_row(self, label, value, bold_val=False):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(80, 80, 80)
        self.cell(65, 7, label)
        if bold_val:
            self.set_font("Helvetica", "B", 10)
        self.set_text_color(0, 0, 0)
        self.cell(0, 7, str(value), ln=True)

    def badge_row(self, label, value, color):
        r, g, b = color
        self.set_font("Helvetica", "", 10)
        self.set_text_color(80, 80, 80)
        self.cell(65, 7, label)
        self.set_fill_color(r, g, b)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 9)
        self.cell(35, 6, " " + value + " ", fill=True, border=0)
        self.set_text_color(0, 0, 0)
        self.ln(8)

    def table_header(self, cols):
        self.set_font("Helvetica", "B", 9)
        self.set_fill_color(240, 240, 240)
        self.set_text_color(40, 40, 40)
        for label, width in cols:
            self.cell(width, 7, label, border=1, fill=True)
        self.ln()

    def table_row(self, values_widths, fill=False):
        self.set_font("Helvetica", "", 9)
        if fill:
            self.set_fill_color(248, 248, 248)
        else:
            self.set_fill_color(255, 255, 255)
        self.set_text_color(0, 0, 0)
        for val, width in values_widths:
            txt = str(val) if val is not None else "-"
            if len(txt) > 35:
                txt = txt[:33] + ".."
            self.cell(width, 6, txt, border=1, fill=True)
        self.ln()


def _pdf_safe(text):
    """Translit Slovak/Czech diacritics to ASCII for Helvetica (latin-1) font."""
    if not text:
        return ""
    text = str(text)
    tr = {
        'á':'a','ä':'a','č':'c','ď':'d','é':'e','ě':'e','í':'i',
        'ľ':'l','ĺ':'l','ň':'n','ó':'o','ô':'o','ö':'o','ř':'r',
        'š':'s','ť':'t','ú':'u','ů':'u','ü':'u','ý':'y','ž':'z',
        'Á':'A','Ä':'A','Č':'C','Ď':'D','É':'E','Ě':'E','Í':'I',
        'Ľ':'L','Ĺ':'L','Ň':'N','Ó':'O','Ô':'O','Ö':'O','Ř':'R',
        'Š':'S','Ť':'T','Ú':'U','Ů':'U','Ü':'U','Ý':'Y','Ž':'Z',
        '–':'-','—':'-','‘':"'",'’':"'",
        '“':'"','”':'"','…':'...',
    }
    result = []
    for ch in text:
        if ch in tr:
            result.append(tr[ch])
        else:
            try:
                ch.encode('latin-1')
                result.append(ch)
            except (UnicodeEncodeError, UnicodeDecodeError):
                result.append('?')
    return ''.join(result)


@app.route("/api/v1/report/generate")
def generate_report():
    check_auth()
    tenant_slug = request.args.get("tenant", "")
    days_param = request.args.get("days", "30")
    try:
        days = int(days_param)
        if days not in (30, 90):
            days = 30
    except Exception:
        days = 30

    if not tenant_slug:
        return jsonify({"error": "tenant required"}), 400

    try:
        import datetime as dt
        import os as _os
        import traceback as _tb
        from datetime import timezone

        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            "SELECT id, name, company, email, sla_tier, retention_days, language "
            "FROM tenants WHERE slug=%s AND active=true",
            (tenant_slug,)
        )
        t = cur.fetchone()
        if not t:
            conn.close()
            return jsonify({"error": "Tenant not found"}), 404
        tenant_id, tenant_name, company, email, sla_tier, retention_days, language = t

        interval = str(days) + " days"

        cur.execute(
            "SELECT COUNT(*) as total,"
            " COUNT(*) FILTER (WHERE severity='critical' OR rule_level>=12) as critical,"
            " COUNT(*) FILTER (WHERE severity='high' OR (rule_level>=8 AND rule_level<12)) as high,"
            " COUNT(*) FILTER (WHERE severity='medium' OR (rule_level>=5 AND rule_level<8)) as medium,"
            " COUNT(*) FILTER (WHERE severity='low' OR rule_level<5) as low,"
            " COUNT(*) FILTER (WHERE status='open') as open_cnt,"
            " COUNT(*) FILTER (WHERE status='resolved') as resolved,"
            " COUNT(*) FILTER (WHERE status='in_progress') as in_progress"
            " FROM alerts WHERE tenant_id=%s AND created_at > now() - interval %s",
            (tenant_id, interval)
        )
        sc = cur.fetchone()
        total, crit, high, medium, low, open_cnt, resolved, in_progress = sc

        cur.execute(
            "SELECT severity, summary, agent_name, created_at, status, rule_level"
            " FROM alerts"
            " WHERE tenant_id=%s AND created_at > now() - interval %s"
            " ORDER BY rule_level DESC NULLS LAST, created_at DESC LIMIT 10",
            (tenant_id, interval)
        )
        top_alerts = cur.fetchall()

        cur.execute(
            "SELECT COUNT(DISTINCT agent_name) FROM alerts"
            " WHERE tenant_id=%s AND created_at > now() - interval %s",
            (tenant_id, interval)
        )
        unique_agents = cur.fetchone()[0] or 0

        cur.execute(
            "SELECT probe_hostname, last_seen, version"
            " FROM probe_heartbeats WHERE tenant_id=%s ORDER BY last_seen DESC LIMIT 1",
            (tenant_id,)
        )
        hb = cur.fetchone()

        cur.execute(
            "SELECT date_trunc('week', created_at) as week, COUNT(*) as cnt"
            " FROM alerts WHERE tenant_id=%s AND created_at > now() - interval %s"
            " GROUP BY 1 ORDER BY 1",
            (tenant_id, interval)
        )
        weekly = cur.fetchall()

        conn.close()

        now = dt.datetime.now(timezone.utc)
        date_from = (now - dt.timedelta(days=days)).strftime("%d.%m.%Y")
        date_to = now.strftime("%d.%m.%Y")
        period_label = "Poslednych " + str(days) + " dni (" + date_from + " - " + date_to + ")"
        sla_map = {"business": "Business (99,5%)", "enterprise": "Enterprise (99,9%)", "basic": "Basic (99,0%)"}

        pdf = NIS2Report(tenant_name, company, period_label)
        pdf.add_page()

        pdf.ln(10)
        pdf.set_font("Helvetica", "B", 22)
        pdf.set_text_color(30, 60, 120)
        pdf.cell(0, 12, "SOC Security Report", align="C", ln=True)
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(60, 60, 60)
        pdf.cell(0, 9, "NIS2 Compliance Report", align="C", ln=True)
        pdf.ln(4)
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(80, 80, 80)
        pdf.cell(0, 7, _pdf_safe(company or tenant_name), align="C", ln=True)
        pdf.cell(0, 7, period_label, align="C", ln=True)
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(130, 130, 130)
        pdf.cell(0, 6, "Generovane: " + now.strftime("%d.%m.%Y %H:%M") + " UTC  |  InnovativeIT s.r.o.", align="C", ln=True)
        pdf.ln(8)

        pdf.section_title("1. Executive Summary")
        pdf.kv_row("Zakaznik:", _pdf_safe(company or tenant_name), bold_val=True)
        pdf.kv_row("Identifikator tenanta:", _pdf_safe(tenant_slug))
        pdf.kv_row("Sledovane obdobie:", period_label)
        pdf.kv_row("SLA uroven:", sla_map.get(sla_tier, sla_tier or "Business"))
        pdf.kv_row("Retencia logov:", str(retention_days) + " dni (NIS2 min. 365 dni)")
        if email:
            pdf.kv_row("Kontaktny email:", _pdf_safe(email))
        pdf.ln(4)

        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(0, 7, "Celkovy prehlad incidentov za obdobie:", ln=True)
        pdf.ln(1)
        items = [
            ("CELKOM", total or 0, (60, 60, 60)),
            ("KRITICKE", crit or 0, (180, 30, 30)),
            ("VYSOKE", high or 0, (200, 100, 30)),
            ("STREDNE", medium or 0, (180, 150, 30)),
            ("NIZKE", low or 0, (60, 130, 60)),
        ]
        for label, val, color in items:
            r2, g2, b2 = color
            pdf.set_fill_color(r2, g2, b2)
            pdf.set_text_color(255, 255, 255)
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(34, 8, label + ": " + str(val), fill=True, border=0)
        pdf.ln(10)

        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(0, 0, 0)
        pdf.kv_row("Otvorene incidenty:", str(open_cnt or 0))
        pdf.kv_row("V rieseni:", str(in_progress or 0))
        pdf.kv_row("Uzavrete/resolved:", str(resolved or 0))
        pdf.kv_row("Monitorovane zariadenia:", str(unique_agents))
        pdf.ln(4)

        if hb:
            age = (now - hb[1].replace(tzinfo=timezone.utc)).total_seconds() if hb[1] else 9999
            probe_status = "ONLINE" if age < 300 else "OFFLINE"
            probe_color = (60, 130, 60) if age < 300 else (180, 30, 30)
            pdf.badge_row("SW Probe stav:", probe_status, probe_color)
            pdf.kv_row("Probe hostname:", _pdf_safe(hb[0]))
            pdf.kv_row("Verzia agenta:", _pdf_safe(hb[2] or "-"))
        pdf.ln(4)

        pdf.section_title("2. Analyza incidentov")
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(60, 60, 60)
        pdf.multi_cell(0, 6,
            "V sledovanom obdobi " + str(days) + " dni bolo zaznamenanych celkom " + str(total or 0) +
            " bezpecnostnych incidentov. Z toho " + str(crit or 0) + " kriticke (rule level >= 12), " +
            str(high or 0) + " vysoke, " + str(medium or 0) + " stredne a " + str(low or 0) +
            " incidentov nizkej zavaznosti. Incidenty boli detegovane na " + str(unique_agents) + " jedinecnych zariadeniach."
        )
        pdf.ln(4)

        if weekly:
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(40, 40, 40)
            pdf.cell(0, 7, "Tyzdenny trend incidentov:", ln=True)
            pdf.ln(1)
            pdf.table_header([("Tyzden od", 50), ("Pocet incidentov", 50)])
            for row_idx, (week_dt, cnt) in enumerate(weekly):
                week_str = week_dt.strftime("%d.%m.%Y") if week_dt else "-"
                pdf.table_row([(week_str, 50), (str(cnt), 50)], fill=(row_idx % 2 == 0))
            pdf.ln(4)

        pdf.section_title("3. Top 10 Incidentov (podla zavaznosti)")
        if top_alerts:
            cols_inc = [("Severity", 22), ("Popis incidentu", 80), ("Zariadenie", 35), ("Datum", 25), ("Stav", 20)]
            pdf.table_header(cols_inc)
            sev_map2 = {"critical": "KRIT", "high": "VYS", "medium": "STRED", "low": "NIZKA"}
            for row_idx, (sev, summary, agent, created, status_a, rlevel) in enumerate(top_alerts):
                if sev:
                    sev_label = sev_map2.get(sev, sev)
                elif (rlevel or 0) >= 12:
                    sev_label = "KRIT"
                elif (rlevel or 0) >= 8:
                    sev_label = "VYS"
                else:
                    sev_label = "STRED"
                date_str = created.strftime("%d.%m %H:%M") if created else "-"
                status_labels = {"open": "Otv.", "resolved": "Uzav.", "in_progress": "Riesenie"}
                status_str = status_labels.get(status_a, status_a or "-")
                pdf.table_row([(_pdf_safe(sev_label), 22), (_pdf_safe(summary), 80), (_pdf_safe(agent or "-"), 35), (date_str, 25), (status_str, 20)], fill=(row_idx % 2 == 0))
            pdf.ln(4)
        else:
            pdf.set_font("Helvetica", "", 10)
            pdf.cell(0, 7, "Ziadne incidenty v sledovanom obdobi.", ln=True)
            pdf.ln(4)

        pdf.section_title("4. NIS2 Compliance Status")
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(60, 60, 60)
        pdf.multi_cell(0, 6,
            "Tento report bol vygenerovany v sulade s poziadavkami smernice NIS2 (EU 2022/2555) "
            "a zodpovedajucich implementacnych predpisov SR. SOC platforma zabezpecuje kontinualne "
            "monitorovanie, detegovanie a reporting bezpecnostnych incidentov."
        )
        pdf.ln(4)
        pdf.set_text_color(0, 0, 0)

        ret_ok = (retention_days or 0) >= 365
        nis2_items = [
            ("Logovanie a monitorovanie", "SPLNENE", (60, 130, 60)),
            ("Retencia logov (" + str(retention_days) + " dni, min. 365)", "SPLNENE" if ret_ok else "NESPLNENE", (60, 130, 60) if ret_ok else (180, 30, 30)),
            ("Detekovanie incidentov (Wazuh SIEM)", "SPLNENE", (60, 130, 60)),
            ("Reporting incidentov (tento dokument)", "SPLNENE", (60, 130, 60)),
            ("Notifikacia (email/Telegram)", "SPLNENE", (60, 130, 60)),
            ("SLA uroven (" + sla_map.get(sla_tier, sla_tier or "Business") + ")", "SPLNENE", (60, 130, 60)),
            ("Anonymizacia dat pred AI spracovanim", "SPLNENE", (60, 130, 60)),
            ("Sifrovana komunikacia (WireGuard VPN)", "SPLNENE", (60, 130, 60)),
        ]
        pdf.table_header([("Poziadavka NIS2", 120), ("Stav", 40)])
        for row_idx, (req, status_n, color) in enumerate(nis2_items):
            pdf.set_font("Helvetica", "", 9)
            if row_idx % 2 == 0:
                pdf.set_fill_color(248, 248, 248)
            else:
                pdf.set_fill_color(255, 255, 255)
            pdf.set_text_color(0, 0, 0)
            pdf.cell(120, 6, req, border=1, fill=True)
            r2, g2, b2 = color
            pdf.set_fill_color(r2, g2, b2)
            pdf.set_text_color(255, 255, 255)
            pdf.set_font("Helvetica", "B", 8)
            pdf.cell(40, 6, status_n, border=1, fill=True)
            pdf.ln()
        pdf.ln(4)

        pdf.section_title("5. Odporucania a nasledujuce kroky")
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(0, 0, 0)
        recs = []
        if (crit or 0) > 0:
            recs.append("Prioritne skontrolovat " + str(crit) + " kritickych incidentov a overit, ze su adresovane.")
        if (open_cnt or 0) > 5:
            recs.append("Uzavriet otvorene incidenty (" + str(open_cnt) + ")  -  vysoke mnozstvo moze indikovat nedostatocnu kapacitu.")
        if not hb:
            recs.append("SW Probe agent neposiela heartbeat  -  overit stav agenta na monitorovanom zariadeni.")
        if not ret_ok:
            recs.append("Zvysit retencnu dobu logov na minimum 365 dni podla poziadaviek NIS2.")
        recs.append("Pravidelne aktualizovat SW Probe agenta na najnovsiu verziu.")
        recs.append("Overit SCA hardening skore v Wazuh dashboarde (odporucane minimum 70%).")
        recs.append("Nasledujuci report odporucame generovat po " + str(days) + " dnoch alebo po bezpecnostnom incidente.")
        for i, rec in enumerate(recs, 1):
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(8, 7, str(i) + ".", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 10)
            pdf.set_x(28)
            pdf.multi_cell(162, 6, rec)
            pdf.ln(1)
        pdf.ln(4)

        pdf.section_title("6. Technicke informacie o SOC platforme")
        pdf.kv_row("SIEM platforma:", "Wazuh v4.14.5")
        pdf.kv_row("Monitoring:", "Zabbix v7.0.26")
        pdf.kv_row("Automatizacia:", "n8n 2.13.4")
        pdf.kv_row("AI analyza:", "Anthropic Claude (anonymizovane vstupy)")
        pdf.kv_row("VPN:", "WireGuard (end-to-end encrypted)")
        pdf.kv_row("DB retencia:", str(retention_days) + " dni")
        pdf.kv_row("Report vygenerovany:", now.strftime("%d.%m.%Y %H:%M") + " UTC")
        pdf.kv_row("Poskytovatel SOC:", "InnovativeIT s.r.o.")
        pdf.ln(8)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(130, 130, 130)
        pdf.multi_cell(0, 5,
            "Tento dokument je automaticky generovany report SOC platformy. Obsahuje informacie "
            "o bezpecnostnych incidentoch, compliance stave a odporucaniach pre dany monitoring "
            "period. Pre otazky kontaktujte soc@innovativeit.sk."
        )

        _os.makedirs(REPORTS_DIR, exist_ok=True)
        ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = "nis2-report-" + tenant_slug + "-" + str(days) + "d-" + ts + ".pdf"
        filepath = _os.path.join(REPORTS_DIR, filename)
        pdf.output(filepath)

        from flask import send_file as _sf
        return _sf(
            filepath,
            mimetype="application/pdf",
            as_attachment=True,
            download_name="SOC-NIS2-Report-" + tenant_slug + "-" + str(days) + "d.pdf"
        )

    except Exception as e:
        import traceback as _tb
        return jsonify({"error": str(e), "trace": _tb.format_exc()}), 500



# -- CHANGE PASSWORD --
@app.route("/api/v1/portal/change-password", methods=["POST"])
def portal_change_password():
    check_auth()
    data = request.get_json() or {}
    slug = data.get("tenant")
    old_pw = data.get("old_password", "")
    new_pw = data.get("new_password", "")
    if not slug or not old_pw or not new_pw:
        return jsonify({"error": "tenant, old_password, new_password required"}), 400
    if len(new_pw) < 8:
        return jsonify({"error": "Heslo musi mat aspon 8 znakov"}), 400
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT password_hash FROM tenants WHERE slug=%s AND active=true", (slug,))
                row = cur.fetchone()
                if not row:
                    return jsonify({"error": "Tenant not found"}), 404
                pw_hash = row[0]
                if not pw_hash:
                    return jsonify({"error": "Account has no password set"}), 400
                if not bcrypt.checkpw(old_pw.encode(), pw_hash.encode()):
                    return jsonify({"error": "Nespravne aktualne heslo"}), 401
                new_hash = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt(12)).decode()
                cur.execute("UPDATE tenants SET password_hash=%s WHERE slug=%s", (new_hash, slug))
                conn.commit()
        return jsonify({"success": True, "message": "Heslo zmenene"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -- RESET PASSWORD REQUEST --
import secrets as _secrets
import smtplib as _smtplib
from email.mime.text import MIMEText as _MIMEText
_reset_tokens = {}

@app.route("/api/v1/auth/reset-password-request", methods=["POST"])
@limiter.limit("5 per minute")
def reset_password_request():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    if not email:
        return jsonify({"error": "email required"}), 400
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT slug, name FROM tenants WHERE LOWER(email)=%s AND active=true AND password_hash IS NOT NULL",
                    (email,)
                )
                row = cur.fetchone()
        if not row:
            return jsonify({"success": True, "message": "Ak email existuje, dostanete odkaz."})
        slug, name = row
        token = _secrets.token_urlsafe(32)
        import time as _time
        _reset_tokens[token] = {"slug": slug, "expires": _time.time() + 3600}
        reset_url = "https://portal.innovativeit.sk/?reset_token=" + token
        body = "Dobry den " + name + ",\n\nReset hesla:\n" + reset_url + "\n\nPlatnost: 1 hodina.\n\nSOC Platform - InnovativeIT"
        msg = _MIMEText(body, "plain", "utf-8")
        msg["Subject"] = "SOC Portal - Reset hesla"
        msg["From"] = "portal@innovativeit.sk"
        msg["To"] = email
        send_email(email, msg["Subject"], body_text=body)
        return jsonify({"success": True, "message": "Ak email existuje, dostanete odkaz."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -- RESET PASSWORD CONFIRM --
@app.route("/api/v1/auth/reset-password", methods=["POST"])
def reset_password_confirm():
    data = request.get_json() or {}
    token = data.get("token", "")
    new_pw = data.get("new_password", "")
    if not token or not new_pw:
        return jsonify({"error": "token and new_password required"}), 400
    if len(new_pw) < 8:
        return jsonify({"error": "Heslo musi mat aspon 8 znakov"}), 400
    import time as _time
    entry = _reset_tokens.get(token)
    if not entry:
        return jsonify({"error": "Neplatny alebo expirovany token"}), 400
    if _time.time() > entry["expires"]:
        del _reset_tokens[token]
        return jsonify({"error": "Token expioval, poziadajte o novy reset"}), 400
    slug = entry["slug"]
    try:
        new_hash = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt(12)).decode()
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE tenants SET password_hash=%s WHERE slug=%s", (new_hash, slug))
                conn.commit()
        del _reset_tokens[token]
        return jsonify({"success": True, "message": "Heslo zmenene. Mozete sa prihlasit."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -- ALERT STATUS UPDATE --
@app.route("/api/v1/portal/alert/status", methods=["POST"])
def portal_alert_status():
    check_auth()
    data = request.get_json() or {}
    alert_id = data.get("alert_id")
    status = data.get("status", "")
    tenant = data.get("tenant", "")
    if not alert_id or not status or not tenant:
        return jsonify({"error": "alert_id, status, tenant required"}), 400
    if status not in ("open", "in_progress", "closed"):
        return jsonify({"error": "Invalid status"}), 400
    try:
        import uuid as _uuid
        try:
            alert_uuid = _uuid.UUID(str(alert_id))
        except ValueError:
            return jsonify({"error": "Invalid alert_id format"}), 400
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE alerts SET status=%s WHERE id=%s AND tenant_id=(SELECT id FROM tenants WHERE slug=%s)",
                    (status, str(alert_uuid), tenant)
                )
                conn.commit()
                if cur.rowcount == 0:
                    return jsonify({"error": "Alert not found"}), 404
        return jsonify({"success": True, "status": status})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── NOTIFICATION SETTINGS ────────────────────────────────────────

@app.route('/api/v1/portal/notifications', methods=['GET'])
def get_notifications():
    check_auth()
    tenant_slug = request.args.get('tenant', '')
    if not tenant_slug:
        return jsonify({'error': 'tenant required'}), 400
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT id FROM tenants WHERE slug=%s AND active=true', (tenant_slug,))
                t = cur.fetchone()
                if not t:
                    return jsonify({'error': 'Tenant not found'}), 404
                cur.execute(
                    'SELECT id, channel, address, label, active FROM tenant_notifications WHERE tenant_id=%s ORDER BY created_at',
                    (t[0],)
                )
                rows = cur.fetchall()
        return jsonify({'success': True, 'channels': [
            {'id': str(r[0]), 'channel': r[1], 'address': r[2], 'label': r[3], 'active': r[4]}
            for r in rows
        ]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/portal/notifications', methods=['POST'])
def save_notification():
    check_auth()
    data = request.get_json() or {}
    tenant_slug = data.get('tenant', '')
    channel = data.get('channel', '')
    address = (data.get('address') or '').strip()
    label = data.get('label') or channel
    active = data.get('active', True)
    rec_id = data.get('id')

    if not tenant_slug:
        return jsonify({'error': 'tenant required'}), 400

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT id FROM tenants WHERE slug=%s AND active=true', (tenant_slug,))
                t = cur.fetchone()
                if not t:
                    return jsonify({'error': 'Tenant not found'}), 404
                tenant_id = t[0]

                if rec_id:
                    # Toggle active na existujúcom zázname
                    cur.execute(
                        'UPDATE tenant_notifications SET active=%s WHERE id=%s AND tenant_id=%s RETURNING id',
                        (active, rec_id, tenant_id)
                    )
                else:
                    # Upsert nový kanál
                    if not channel or not address:
                        return jsonify({'error': 'channel and address required'}), 400
                    if channel not in ('email', 'telegram', 'whatsapp', 'sms'):
                        return jsonify({'error': 'Invalid channel'}), 400
                    cur.execute('''
                        INSERT INTO tenant_notifications (tenant_id, channel, address, label, active)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (tenant_id, channel, address)
                        DO UPDATE SET active=%s, label=%s
                        RETURNING id
                    ''', (tenant_id, channel, address, label, active, active, label))

                row = cur.fetchone()
                conn.commit()
        return jsonify({'success': True, 'id': str(row[0]) if row else None})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/v1/probe/heartbeat', methods=['POST'])
def probe_heartbeat():
    data = request.get_json() or {}
    tenant_slug = data.get('tenant', '').strip()
    hostname    = data.get('hostname', '').strip()
    wg_ip       = data.get('wg_ip', '').strip()
    version     = data.get('version', '1.0').strip()

    if not tenant_slug or not hostname:
        return jsonify({'error': 'tenant and hostname required'}), 400

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT id FROM tenants WHERE slug=%s AND active=true', (tenant_slug,))
                t = cur.fetchone()
                if not t:
                    return jsonify({'error': 'Tenant not found'}), 404
                tenant_id = t[0]

                # Upsert probe
                cur.execute('''
                    INSERT INTO probes (tenant_id, hostname, ip_address, status, last_seen)
                    VALUES (%s, %s, %s, 'active', now())
                    ON CONFLICT (hostname) DO UPDATE
                      SET status='active', last_seen=now(), ip_address=EXCLUDED.ip_address
                ''', (tenant_id, hostname, wg_ip or None))

                # Upsert heartbeat
                cur.execute('''
                    INSERT INTO probe_heartbeats (probe_hostname, tenant_id, last_seen, ip_address, version)
                    VALUES (%s, %s, now(), %s, %s)
                    ON CONFLICT (probe_hostname) DO UPDATE
                      SET last_seen=now(), ip_address=EXCLUDED.ip_address, version=EXCLUDED.version,
                          tenant_id=EXCLUDED.tenant_id
                ''', (hostname, tenant_id, wg_ip or None, version))

                conn.commit()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


ZABBIX_URL  = "http://localhost:8081/api_jsonrpc.php"
ZABBIX_USER = "Admin"
ZABBIX_PASS = "zabbix"

def _zbx_auth():
    try:
        r = _requests_lib.post(ZABBIX_URL, json={
            "jsonrpc": "2.0", "method": "user.login",
            "params": {"username": ZABBIX_USER, "password": ZABBIX_PASS}, "id": 1
        }, timeout=3)
        return r.json().get("result")
    except Exception:
        return None

def _zbx_hosts(token, hostnames):
    """Return dict hostname→{available, status, os, ip} for given hostnames."""
    if not token or not hostnames:
        return {}
    try:
        r = _requests_lib.post(ZABBIX_URL, json={
            "jsonrpc": "2.0", "method": "host.get",
            "params": {
                "output": ["hostid", "host", "name", "status", "available"],
                "selectInterfaces": ["ip", "type"],
                "filter": {"host": hostnames}
            },
            "auth": token, "id": 2
        }, timeout=3)
        result = {}
        for h in r.json().get("result", []):
            ip = next((i["ip"] for i in h.get("interfaces", []) if i["type"] == "1"), "")
            # available: 0=unknown, 1=available, 2=unavailable
            avail = int(h.get("available", 0))
            result[h["host"]] = {"zabbix_avail": avail, "zabbix_ip": ip}
        return result
    except Exception:
        return {}


@app.route('/api/v1/portal/devices', methods=['GET'])
def get_devices():
    check_auth()
    tenant_slug = request.args.get('tenant', '')
    if not tenant_slug:
        return jsonify({'error': 'tenant required'}), 400
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT id FROM tenants WHERE slug=%s AND active=true', (tenant_slug,))
                t = cur.fetchone()
                if not t:
                    return jsonify({'error': 'Tenant not found'}), 404
                tenant_id = t[0]

                cur.execute('''
                    SELECT p.hostname, host(p.ip_address), p.status, p.last_seen,
                           ph.last_seen AS heartbeat_at, ph.version
                    FROM probes p
                    LEFT JOIN probe_heartbeats ph ON ph.probe_hostname = p.hostname
                    WHERE p.tenant_id = %s
                    ORDER BY p.created_at
                ''', (tenant_id,))
                rows = cur.fetchall()

        hostnames = [r[0] for r in rows]
        zbx_token = _zbx_auth()
        zbx_map   = _zbx_hosts(zbx_token, hostnames)

        devices = []
        for row in rows:
            hostname, ip, db_status, last_seen, heartbeat_at, version = row
            zbx = zbx_map.get(hostname, {})

            if zbx:
                avail = zbx.get("zabbix_avail", 0)
                online = avail == 1
                status = "online" if online else ("offline" if avail == 2 else db_status or "unknown")
                ip = zbx.get("zabbix_ip") or ip or ""
            else:
                online = db_status == "active"
                status = db_status or "unknown"

            last_ts = heartbeat_at or last_seen
            last_str = ""
            if last_ts:
                delta = int((datetime.now(last_ts.tzinfo) - last_ts).total_seconds())
                if delta < 120:   last_str = "práve teraz"
                elif delta < 3600: last_str = f"pred {delta // 60} min"
                else:              last_str = f"pred {delta // 3600}h"

            probe_type = "SOC Agent" if "probe" in hostname.lower() else "Host"

            devices.append({
                "hostname": hostname,
                "ip": ip or "",
                "status": status,
                "online": online,
                "probe_type": probe_type,
                "last_seen": last_str,
                "version": version or "",
                "in_zabbix": bool(zbx)
            })

        online_count = sum(1 for d in devices if d["online"])
        return jsonify({"success": True, "devices": devices, "online": online_count, "total": len(devices)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    os.makedirs(PACKAGES_DIR, exist_ok=True)
    app.run(host="0.0.0.0", port=5050, debug=False)
