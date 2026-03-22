#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  ElasticGuard — Kubernetes Secrets Helper
#
#  Creates all required Kubernetes Secrets before running
#  helm install with existingSecret references.
#
#  Usage:
#    chmod +x helm/secrets-helper.sh
#    ./helm/secrets-helper.sh --namespace monitoring
#
#  Then install chart using existing secrets:
#    helm install elasticguard ./helm/elasticguard \
#      -n monitoring \
#      -f helm/values-production.yaml \
#      --set ai.existingSecret=elasticguard-ai-keys \
#      --set notifications.existingSecret=elasticguard-notification-keys \
#      --set grafana.existingSecret=elasticguard-grafana-admin \
#      --set app.secretKey=$(openssl rand -hex 32)
# ═══════════════════════════════════════════════════════════════
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'; BOLD='\033[1m'
info()    { echo -e "${CYAN}▶${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warn()    { echo -e "${YELLOW}⚠${NC}  $1"; }
error()   { echo -e "${RED}✗${NC} $1"; exit 1; }
ask()     { echo -en "${BOLD}$1${NC} "; read -r REPLY; echo "$REPLY"; }
ask_pass(){ echo -en "${BOLD}$1${NC} "; read -rs REPLY; echo; echo "$REPLY"; }

# ── Parse args ────────────────────────────────────────────────
NAMESPACE="monitoring"
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case $1 in
    -n|--namespace) NAMESPACE="$2"; shift 2 ;;
    --dry-run)      DRY_RUN=true; shift ;;
    -h|--help)
      echo "Usage: $0 [-n NAMESPACE] [--dry-run]"
      exit 0
      ;;
    *) error "Unknown argument: $1" ;;
  esac
done

echo -e "\n${BOLD}ElasticGuard — Kubernetes Secrets Setup${NC}"
echo "Namespace: ${CYAN}${NAMESPACE}${NC}"
echo ""

# ── Ensure namespace ─────────────────────────────────────────
if ! kubectl get namespace "$NAMESPACE" &>/dev/null; then
  info "Creating namespace $NAMESPACE..."
  $DRY_RUN || kubectl create namespace "$NAMESPACE"
fi

# ── AI Keys Secret ────────────────────────────────────────────
echo -e "\n${BOLD}── AI Provider Keys ─────────────────────────────────${NC}"
echo "Leave blank to skip any provider."
echo ""

AI_PROVIDER=$(ask "Default AI provider [openai/gemini/anthropic/ollama]:")
OPENAI_KEY=$(ask_pass "OpenAI API key (sk-...):")
GEMINI_KEY=$(ask_pass "Google Gemini API key (AIza...):")
ANTHROPIC_KEY=$(ask_pass "Anthropic Claude API key (sk-ant-...):")

info "Creating secret: elasticguard-ai-keys"
if $DRY_RUN; then
  warn "DRY RUN — would create secret elasticguard-ai-keys in $NAMESPACE"
else
  kubectl create secret generic elasticguard-ai-keys \
    --namespace "$NAMESPACE" \
    --from-literal=DEFAULT_AI_PROVIDER="${AI_PROVIDER:-ollama}" \
    --from-literal=OPENAI_API_KEY="${OPENAI_KEY}" \
    --from-literal=GEMINI_API_KEY="${GEMINI_KEY}" \
    --from-literal=ANTHROPIC_API_KEY="${ANTHROPIC_KEY}" \
    --dry-run=client -o yaml | kubectl apply -f -
fi
success "elasticguard-ai-keys created"

# ── Notification Secret ───────────────────────────────────────
echo -e "\n${BOLD}── Notification Channels ────────────────────────────${NC}"
echo "Leave blank to skip any channel."
echo ""

DISCORD_URL=$(ask "Discord Webhook URL (https://discord.com/api/webhooks/...):")
SLACK_URL=$(ask "Slack Webhook URL (https://hooks.slack.com/services/...):")
SMTP_HOST=$(ask "SMTP host (e.g. smtp.gmail.com):")
SMTP_USER=$(ask "SMTP username (e.g. you@gmail.com):")
SMTP_PASS=$(ask_pass "SMTP password / app password:")
SMTP_FROM=$(ask "SMTP from address (e.g. ElasticGuard <you@gmail.com>):")
NOTIF_EMAILS=$(ask "Notification emails (comma-separated):")

info "Creating secret: elasticguard-notification-keys"
if $DRY_RUN; then
  warn "DRY RUN — would create secret elasticguard-notification-keys in $NAMESPACE"
else
  kubectl create secret generic elasticguard-notification-keys \
    --namespace "$NAMESPACE" \
    --from-literal=DISCORD_WEBHOOK_URL="${DISCORD_URL}" \
    --from-literal=SLACK_WEBHOOK_URL="${SLACK_URL}" \
    --from-literal=SMTP_HOST="${SMTP_HOST}" \
    --from-literal=SMTP_USER="${SMTP_USER}" \
    --from-literal=SMTP_PASS="${SMTP_PASS}" \
    --from-literal=SMTP_FROM="${SMTP_FROM}" \
    --from-literal=NOTIFICATION_EMAILS="${NOTIF_EMAILS}" \
    --dry-run=client -o yaml | kubectl apply -f -
fi
success "elasticguard-notification-keys created"

# ── Grafana Secret ────────────────────────────────────────────
echo -e "\n${BOLD}── Grafana Admin Credentials ────────────────────────${NC}"

GRAFANA_USER=$(ask "Grafana admin username [admin]:")
GRAFANA_USER="${GRAFANA_USER:-admin}"
GRAFANA_PASS=$(ask_pass "Grafana admin password:")

info "Creating secret: elasticguard-grafana-admin"
if $DRY_RUN; then
  warn "DRY RUN — would create secret elasticguard-grafana-admin in $NAMESPACE"
else
  kubectl create secret generic elasticguard-grafana-admin \
    --namespace "$NAMESPACE" \
    --from-literal=admin-user="${GRAFANA_USER}" \
    --from-literal=admin-password="${GRAFANA_PASS}" \
    --dry-run=client -o yaml | kubectl apply -f -
fi
success "elasticguard-grafana-admin created"

# ── Summary ───────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}All secrets created in namespace '${NAMESPACE}'${NC}"
echo ""
echo "Now install ElasticGuard:"
echo ""
echo -e "  ${CYAN}helm install elasticguard ./helm/elasticguard \\${NC}"
echo -e "  ${CYAN}  -n ${NAMESPACE} \\${NC}"
echo -e "  ${CYAN}  -f helm/values-production.yaml \\${NC}"
echo -e "  ${CYAN}  --set ai.existingSecret=elasticguard-ai-keys \\${NC}"
echo -e "  ${CYAN}  --set notifications.existingSecret=elasticguard-notification-keys \\${NC}"
echo -e "  ${CYAN}  --set grafana.existingSecret=elasticguard-grafana-admin \\${NC}"
echo -e "  ${CYAN}  --set app.secretKey=\$(openssl rand -hex 32) \\${NC}"
echo -e "  ${CYAN}  --set app.approvalWebhookSecret=\$(openssl rand -hex 16)${NC}"
echo ""
