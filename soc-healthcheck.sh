#!/bin/bash
# SOC Platform — Comprehensive Healthcheck
# Verzia 2.0 — 2026-06-10

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
OK=0; WARN=0; FAIL=0

ok()   { echo -e "  ${GREEN}[OK]${NC}   $1"; ((OK++)); }
fail() { echo -e "  ${RED}[FAIL]${NC} $1"; ((FAIL++)); }
warn() { echo -e "  ${YELLOW}[WARN]${NC} $1"; ((WARN++)); }
info() { echo -e "  ${CYAN}[INFO]${NC} $1"; }
section() { echo ""; echo -e "${CYAN}─── $1 ───${NC}"; }

check_container() {
  if docker ps --format "{{.Names}}" | grep -q "^${1}$"; then
    ok "$1 running"
  else
    fail "$1 NOT running"
  fi
}

echo "╔══════════════════════════════════════╗"
echo "║  SOC Healthcheck  —  $(date '+%Y-%m-%d %H:%M:%S')  ║"
echo "╚══════════════════════════════════════╝"

# ──────────────────────────────────────────
section "1. Docker kontajnery"
CONTAINERS="single-node-wazuh.manager-1 single-node-wazuh.indexer-1 single-node-wazuh.dashboard-1 soc-n8n-1 soc-postgres-1 zabbix-server zabbix-web zabbix-postgres grafana"
for c in $CONTAINERS; do check_container "$c"; done

# ──────────────────────────────────────────
section "2. Systémové služby"
systemctl is-active cloudflared -q && ok "cloudflared aktívny" || fail "cloudflared FAIL"
systemctl is-active nginx -q      && ok "nginx aktívny"       || fail "nginx FAIL"
systemctl is-active flask-soc -q  && ok "flask-soc aktívny"   || fail "flask-soc FAIL"

# ──────────────────────────────────────────
section "3. Databáza"
if docker exec soc-postgres-1 pg_isready -U soc_admin -d soc -q 2>/dev/null; then
  ok "PostgreSQL ready"
else
  fail "PostgreSQL FAIL"
fi

TENANTS=$(docker exec soc-postgres-1 psql -U soc_admin -d soc -At \
  -c "SELECT count(*) FROM tenants;" 2>/dev/null | tr -d ' \n')
[ -n "$TENANTS" ] && ok "Tenants: $TENANTS" || fail "Tenants query FAIL"

SESSIONS=$(docker exec soc-postgres-1 psql -U soc_admin -d soc -At \
  -c "SELECT count(*) FROM portal_sessions WHERE expires_at > now();" 2>/dev/null | tr -d ' \n')
[ -n "$SESSIONS" ] && ok "Aktívne portal sessions: $SESSIONS" || warn "portal_sessions tabuľka chýba!"

ORPHAN_PROBES=$(docker exec soc-postgres-1 psql -U soc_admin -d soc -At \
  -c "SELECT count(*) FROM probes WHERE tenant_id IS NULL;" 2>/dev/null | tr -d ' \n')
[ "$ORPHAN_PROBES" = "0" ] && ok "DB integrita: žiadne orphaned probes" || \
  warn "DB integrita: $ORPHAN_PROBES probes bez tenant_id"

# Backup freshness
LAST_BACKUP=$(ls -t /opt/soc/backups/soc-db-*.sql.gz 2>/dev/null | head -1)
if [ -n "$LAST_BACKUP" ]; then
  BACKUP_AGE=$(( ($(date +%s) - $(stat -c %Y "$LAST_BACKUP")) / 3600 ))
  BACKUP_NAME=$(basename "$LAST_BACKUP")
  [ "$BACKUP_AGE" -lt 26 ] && ok "Záloha: ${BACKUP_NAME} (pred ${BACKUP_AGE}h)" || \
    warn "Záloha: ${BACKUP_NAME} je ${BACKUP_AGE}h stará — cron OK?"
else
  fail "Záloha: žiadna .sql.gz v /opt/soc/backups/"
fi

# ──────────────────────────────────────────
section "4. Flask API — funkčné testy"

# Základný health
HC_RESP=$(curl -s http://localhost:5050/health 2>/dev/null)
HC_STATUS=$(echo "$HC_RESP" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status',''))" 2>/dev/null)
[ "$HC_STATUS" = "ok" ] && ok "Flask /health → ok" || fail "Flask /health FAIL ($HC_RESP)"

# Login test — c001
LOGIN_RESP=$(curl -s -X POST http://localhost:5050/api/v1/portal/auth \
  -H "Content-Type: application/json" \
  -d '{"email":"soc-c001@innovativeit.sk","password":"CustC001-2026!"}' 2>/dev/null)
PORTAL_TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import json,sys; print(json.load(sys.stdin).get('portal_token',''))" 2>/dev/null)
if [ -n "$PORTAL_TOKEN" ]; then
  ok "Portal login (c001) → token OK"
  # Dashboard test s portal tokenom
  DASH_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5050/api/v1/portal/dashboard \
    -H "X-Portal-Token: $PORTAL_TOKEN" 2>/dev/null)
  [ "$DASH_CODE" = "200" ] && ok "Portal dashboard (s tokenom) → 200" || fail "Portal dashboard → $DASH_CODE"
  # Overenie že bez tokenu → 401
  UNAUTH_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5050/api/v1/portal/dashboard 2>/dev/null)
  [ "$UNAUTH_CODE" = "401" ] && ok "Dashboard bez tokenu → 401 (správne)" || warn "Dashboard bez tokenu → $UNAUTH_CODE (očakávané 401)"
else
  fail "Portal login FAIL — žiadny portal_token v odpovedi"
  info "Login response: $LOGIN_RESP"
fi

# Operator login
OP_RESP=$(curl -s -X POST http://localhost:5050/api/v1/operator/login \
  -H "Content-Type: application/json" \
  -d '{"password":"OperatorSOC2026!"}' 2>/dev/null)
OP_SUCCESS=$(echo "$OP_RESP" | python3 -c "import json,sys; print(json.load(sys.stdin).get('success',False))" 2>/dev/null)
[ "$OP_SUCCESS" = "True" ] && ok "Operator login → ok" || fail "Operator login FAIL ($OP_RESP)"

# Flask chyby za posledných 24h
FLASK_ERRORS=$(journalctl -u flask-soc --since "24 hours ago" 2>/dev/null | grep -E "HTTP/[0-9.]+ 5[0-9][0-9]|\bERROR\b|Traceback" 2>/dev/null | wc -l)
[ "${FLASK_ERRORS:-0}" -eq 0 ] && ok "Flask logy: 0 chýb za 24h" || warn "Flask logy: ${FLASK_ERRORS} chýb/5xx za 24h"

# ──────────────────────────────────────────
section "5. SW Probe & WireGuard"

# WG základný status
if wg show wg0 &>/dev/null; then
  ok "WireGuard aktívny"
  # Aktívne peers (majú handshake)
  TOTAL_PEERS=$(wg show wg0 2>/dev/null | grep "^peer:" | wc -l)
  ACTIVE_PEERS=$(wg show wg0 2>/dev/null | grep "latest handshake" | wc -l)
  [ "$ACTIVE_PEERS" -gt 0 ] && ok "WG peers: $ACTIVE_PEERS/$TOTAL_PEERS aktívnych" || \
    warn "WG peers: 0/$TOTAL_PEERS — žiadny aktívny probe"
  # Zobraz aktívne peers
  ACTIVE_PEER_IPS=$(wg show wg0 2>/dev/null | awk '/allowed ips:/{ip=$3} /latest handshake:/{print ip}')
  while IFS= read -r ip; do [ -n "$ip" ] && info "Aktívny peer: $ip"; done <<< "$ACTIVE_PEER_IPS"
else
  fail "WireGuard FAIL"
fi

# Probe heartbeats
LAST_HB=$(docker exec soc-postgres-1 psql -U soc_admin -d soc -At \
  -c "SELECT extract(epoch from (now()-MAX(last_seen)))/60 FROM probe_heartbeats;" 2>/dev/null | \
  python3 -c "import sys; v=sys.stdin.read().strip(); print(int(float(v))) if v else print(-1)" 2>/dev/null)
if [ "$LAST_HB" = "-1" ]; then
  warn "Probe heartbeats: žiadny záznam v DB"
elif [ "$LAST_HB" -lt 30 ]; then
  ok "Probe heartbeat: pred ${LAST_HB} min"
elif [ "$LAST_HB" -lt 240 ]; then
  warn "Probe heartbeat: pred ${LAST_HB} min (posliednich 4h)"
else
  fail "Probe heartbeat: pred ${LAST_HB} min — probe offline?"
fi

# SW Probe API health (s aktuálnym kľúčom z .env)
API_KEY=$(grep SOC_API_KEY /opt/soc/.env 2>/dev/null | cut -d= -f2)
API_KEY=${API_KEY:-soc-key-prod-b153c299eea49ca8e7b3c791069fe6ad3af5efefcae58c1c}
CODE=$(curl -s -o /dev/null -w "%{http_code}" -H "X-SOC-Key: $API_KEY" http://localhost:5050/health 2>/dev/null)
[ "$CODE" = "200" ] && ok "SW Probe API /health (s prod kľúčom) → 200" || fail "SW Probe API FAIL ($CODE)"

# ──────────────────────────────────────────
section "6. Wazuh"

# Procesy
for proc in wazuh-db wazuh-remoted wazuh-analysisd wazuh-modulesd wazuh-authd wazuh-apid; do
  if docker exec single-node-wazuh.manager-1 \
    /var/ossec/bin/wazuh-control status 2>/dev/null | grep -q "$proc is running"; then
    ok "$proc running"
  else
    fail "$proc NOT running"
  fi
done

# Wazuh API
set +H
W_TOKEN=$(docker exec single-node-wazuh.dashboard-1 curl -sk -u "wazuh-wui:MyS3cr37P450r.*-" \
  -X POST https://wazuh.manager:55000/security/user/authenticate \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['data']['token'])" 2>/dev/null)
if [ -n "$W_TOKEN" ]; then
  ok "Wazuh API autentifikácia OK"
  AGENTS=$(curl -sk -H "Authorization: Bearer $W_TOKEN" \
    "https://localhost:55000/agents?pretty=true" | python3 -c "
import json,sys
d=json.load(sys.stdin)
items=d.get('data',{}).get('affected_items',[])
total=len(items)
active=sum(1 for a in items if a.get('status')=='active')
print(f'{active}/{total}')
" 2>/dev/null)
  ok "Wazuh agenti: $AGENTS (aktívni/celkom)"
else
  fail "Wazuh API FAIL"
fi

# Indexer
INDEXER_HEALTH=$(curl -sk -u admin:Xp7mQ2nL-Ks91Vb \
  https://localhost:9200/_cluster/health 2>/dev/null | \
  python3 -c "import json,sys; print(json.load(sys.stdin)['status'])" 2>/dev/null)
if [ "$INDEXER_HEALTH" = "green" ];  then ok "Wazuh Indexer: green"
elif [ "$INDEXER_HEALTH" = "yellow" ]; then warn "Wazuh Indexer: yellow"
else fail "Wazuh Indexer: DOWN ($INDEXER_HEALTH)"
fi

# ──────────────────────────────────────────
section "7. Zabbix & Grafana"

# Zabbix API auth test
ZBX_RESP=$(curl -s -X POST http://localhost:8081/api_jsonrpc.php \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"user.login","params":{"username":"Admin","password":"zabbix"},"id":1}' \
  2>/dev/null)
ZBX_TOKEN=$(echo "$ZBX_RESP" | python3 -c "import json,sys; print(json.load(sys.stdin).get('result',''))" 2>/dev/null)
if [ -n "$ZBX_TOKEN" ] && [ "$ZBX_TOKEN" != "None" ]; then
  ok "Zabbix API autentifikácia OK"
  # Počet hostiteľov
  ZBX_HOSTS=$(curl -s -X POST http://localhost:8081/api_jsonrpc.php \
    -H "Content-Type: application/json" \
    -d "{\"jsonrpc\":\"2.0\",\"method\":\"host.get\",\"params\":{\"output\":\"count\"},\"auth\":\"$ZBX_TOKEN\",\"id\":2}" \
    2>/dev/null | python3 -c "import json,sys; print(len(json.load(sys.stdin).get('result',[])))" 2>/dev/null)
  ok "Zabbix hostitelia: ${ZBX_HOSTS:-?}"
else
  fail "Zabbix API FAIL (admin/zabbix)"
  info "Zabbix response: $ZBX_RESP"
fi

# Grafana
GF_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3001 2>/dev/null)
[ "$GF_CODE" = "200" ] || [ "$GF_CODE" = "302" ] && ok "Grafana HTTP → $GF_CODE" || fail "Grafana FAIL ($GF_CODE)"

# ──────────────────────────────────────────
section "8. n8n"

N8N_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5680 2>/dev/null)
[ "$N8N_CODE" = "200" ] || [ "$N8N_CODE" = "302" ] && ok "n8n HTTP → $N8N_CODE" || fail "n8n FAIL ($N8N_CODE)"

# n8n workflow count cez API
N8N_WORKFLOWS=$(curl -s "http://localhost:5678/rest/workflows" 2>/dev/null | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('data',[])))" 2>/dev/null || echo "?")
[ "$N8N_WORKFLOWS" = "?" ] && info "n8n: počet workflows nedostupný (vyžaduje prihlásenie)" || \
  { [ "$N8N_WORKFLOWS" -gt 0 ] 2>/dev/null && ok "n8n workflows: $N8N_WORKFLOWS" || warn "n8n: 0 workflows — treba nakonfigurovať"; }

# ──────────────────────────────────────────
section "9. SMTP"
python3 /opt/soc/smtp_test.py 2>/dev/null | grep -q OK && ok "SMTP 587 OK" || fail "SMTP FAIL"

# ──────────────────────────────────────────
section "10. Portál & SSL"

# Subdomény HTTP
for sub in wazuh-ops n8n-ops zabbix-ops grafana-ops portal; do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 https://${sub}.innovativeit.sk 2>/dev/null)
  if [ "$CODE" = "200" ] || [ "$CODE" = "302" ]; then
    ok "${sub}.innovativeit.sk → $CODE"
  else
    fail "${sub}.innovativeit.sk → $CODE"
  fi
done

# swprobe + /dev/
CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 https://swprobe.innovativeit.sk/health 2>/dev/null)
[ "$CODE" = "200" ] && ok "swprobe.innovativeit.sk/health → $CODE" || fail "swprobe.innovativeit.sk/health → $CODE"

CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 https://portal.innovativeit.sk/dev/ 2>/dev/null)
[ "$CODE" = "200" ] && ok "portal.innovativeit.sk/dev/ → $CODE (dev env)" || warn "portal.innovativeit.sk/dev/ → $CODE"

# SSL cert expiry (bez externého volania — cez lokálne nginx/certbot)
for DOMAIN in portal.innovativeit.sk swprobe.innovativeit.sk; do
  CERT_FILE=$(ls /etc/letsencrypt/live/${DOMAIN}/cert.pem 2>/dev/null)
  if [ -n "$CERT_FILE" ]; then
    DAYS=$(openssl x509 -noout -enddate -in "$CERT_FILE" 2>/dev/null | \
      python3 -c "
from datetime import datetime, timezone; import sys
line=sys.stdin.read().strip()
if '=' in line:
    d=datetime.strptime(line.split('=')[1], '%b %d %H:%M:%S %Y %Z').replace(tzinfo=timezone.utc)
    print((d-datetime.now(timezone.utc)).days)
else: print(-1)
" 2>/dev/null)
    if [ "$DAYS" -gt 30 ]; then ok "SSL ${DOMAIN}: ${DAYS}d do expiry"
    elif [ "$DAYS" -gt 0 ]; then warn "SSL ${DOMAIN}: len ${DAYS}d — OBNOV!"
    else fail "SSL ${DOMAIN}: cert chýba alebo expirovaný"
    fi
  else
    info "SSL ${DOMAIN}: certbot cert nenájdený (CF proxy?)"
  fi
done

# ──────────────────────────────────────────
section "11. Disk & RAM"
DISK=$(df / | awk 'NR==2{print $5}' | tr -d '%')
[ "$DISK" -lt 70 ] && ok "Disk: ${DISK}%" || \
  { [ "$DISK" -lt 85 ] && warn "Disk: ${DISK}% — pozor!" || fail "Disk: ${DISK}% — KRITICKÝ!"; }

RAM=$(free | awk '/^Mem/{printf "%.0f", $3/$2*100}')
[ "$RAM" -lt 80 ] && ok "RAM: ${RAM}%" || \
  { [ "$RAM" -lt 90 ] && warn "RAM: ${RAM}% — pozor!" || fail "RAM: ${RAM}% — KRITICKÝ!"; }

# ──────────────────────────────────────────
section "12. Compliance & Security"

# Retention >= 365 pre produkčných tenantov
PROD_BAD=$(docker exec soc-postgres-1 psql -U soc_admin -d soc -At \
  -c "SELECT count(*) FROM tenants WHERE test_account=false AND retention_days < 365;" \
  2>/dev/null | tr -d ' \n')
[ "$PROD_BAD" = "0" ] && ok "Retention: všetci prod tenanty >= 365 dní" || \
  fail "Retention: $PROD_BAD prod tenantov má < 365 dní (NIS2!)"

# Webhook tokeny
MISSING_TOKEN=$(docker exec soc-postgres-1 psql -U soc_admin -d soc -At \
  -c "SELECT count(*) FROM tenants WHERE webhook_token IS NULL;" \
  2>/dev/null | tr -d ' \n')
[ "$MISSING_TOKEN" = "0" ] && ok "Webhook tokeny: všetci tenanty" || \
  warn "Webhook tokeny: $MISSING_TOKEN tenantov bez tokenu"

# Password hash pre prod tenantov
MISSING_PASS=$(docker exec soc-postgres-1 psql -U soc_admin -d soc -At \
  -c "SELECT count(*) FROM tenants WHERE test_account=false AND password_hash IS NULL;" \
  2>/dev/null | tr -d ' \n')
[ "$MISSING_PASS" = "0" ] && ok "Heslá: všetci prod tenanty" || \
  warn "Heslá: $MISSING_PASS prod tenantov bez password_hash"

# Wazuh Indexer default heslo
WAZUH_DEFAULT=$(curl -sk -u admin:admin https://localhost:9200/_cluster/health 2>/dev/null | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print('yes' if d.get('status') else 'no')" 2>/dev/null)
[ "$WAZUH_DEFAULT" = "yes" ] && \
  warn "Wazuh Indexer: STÁLE default heslo admin/admin — zmeniť!" || \
  ok "Wazuh Indexer: heslo zmenené z default"

# Zabbix default heslo (Admin/zabbix)
if [ -n "$ZBX_TOKEN" ] && [ "$ZBX_TOKEN" != "None" ]; then
  warn "Zabbix: STÁLE default heslo Admin/zabbix — zmeniť!"
else
  ok "Zabbix: heslo zmenené z default"
fi

# API key — overenie že nie je default poc kľúč
if grep -q "soc-swprobe-api-key-poc" /opt/soc/.env 2>/dev/null || \
   grep -q "soc-swprobe-api-key-poc" /opt/soc/swprobe/soc-swprobe-api.py 2>/dev/null; then
  warn "API Key: stále obsahuje poc kľúč v kóde"
else
  ok "API Key: zmenený (prod kľúč)"
fi

# Orphaned alerts
ORPHANED=$(docker exec soc-postgres-1 psql -U soc_admin -d soc -At \
  -c "SELECT count(*) FROM alerts WHERE tenant_id IS NULL;" \
  2>/dev/null | tr -d ' \n')
[ "$ORPHANED" = "0" ] && ok "Alerts: žiadne orphaned" || warn "Alerts: $ORPHANED bez tenant_id"

# Otvorené alerty > 7 dní
OLD_OPEN=$(docker exec soc-postgres-1 psql -U soc_admin -d soc -At \
  -c "SELECT count(*) FROM alerts WHERE status='open' AND created_at < now() - interval '7 days';" \
  2>/dev/null | tr -d ' \n')
[ "$OLD_OPEN" = "0" ] && ok "SLA: žiadne open alerty staršie ako 7 dní" || \
  warn "SLA: $OLD_OPEN otvorených alertov > 7 dní"

# Neschválení partneri
PENDING=$(docker exec soc-postgres-1 psql -U soc_admin -d soc -At \
  -c "SELECT count(*) FROM partners WHERE approved=false AND role='partner';" \
  2>/dev/null | tr -d ' \n')
[ "$PENDING" = "0" ] && ok "Partneri: žiadni neschválení" || \
  warn "Partneri: $PENDING čaká na schválenie"

# Expired portal sessions (cleanup check)
EXPIRED=$(docker exec soc-postgres-1 psql -U soc_admin -d soc -At \
  -c "SELECT count(*) FROM portal_sessions WHERE expires_at < now();" \
  2>/dev/null | tr -d ' \n')
[ "${EXPIRED:-0}" -lt 50 ] && ok "Portal sessions: ${EXPIRED:-?} expirovaných (cron cleanup OK)" || \
  warn "Portal sessions: $EXPIRED expirovaných — cron cleanup nefunguje?"

# ──────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════╗"
printf "║  VÝSLEDOK: "
printf "${GREEN}%3d OK${NC} | ${YELLOW}%3d WARN${NC} | ${RED}%3d FAIL${NC}  ║\n" $OK $WARN $FAIL
echo "╚══════════════════════════════════════╝"
