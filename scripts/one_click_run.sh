#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SUDO=""
if [[ "${EUID}" -ne 0 ]] && command -v sudo >/dev/null 2>&1; then
  SUDO="sudo"
fi

log() {
  echo "[auto-ledger] $*"
}

random_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 16
    return
  fi
  tr -dc 'a-f0-9' </dev/urandom | head -c 32
}

set_env_value() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key}=${value}|" .env
  else
    echo "${key}=${value}" >>.env
  fi
}

get_env_value() {
  local key="$1"
  local line
  line="$(grep -E "^${key}=" .env | head -n1 || true)"
  echo "${line#*=}"
}

install_docker_if_needed() {
  if command -v docker >/dev/null 2>&1; then
    return
  fi

  log "Docker not found. Installing Docker..."
  curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
  ${SUDO} sh /tmp/get-docker.sh
  rm -f /tmp/get-docker.sh
  ${SUDO} systemctl enable --now docker || true
}

resolve_docker_cmd() {
  if docker info >/dev/null 2>&1; then
    echo "docker"
    return
  fi

  if command -v sudo >/dev/null 2>&1 && sudo docker info >/dev/null 2>&1; then
    echo "sudo docker"
    return
  fi

  log "Docker daemon is not reachable. Please start docker first."
  exit 1
}

install_docker_if_needed
DOCKER_CMD="$(resolve_docker_cmd)"

if ! ${DOCKER_CMD} compose version >/dev/null 2>&1; then
  log "docker compose plugin is missing."
  exit 1
fi

if [[ ! -f ".env" ]]; then
  cp .env.example .env
  log ".env created from .env.example"
fi

if [[ -z "$(get_env_value APP_API_KEY)" ]]; then
  set_env_value "APP_API_KEY" "$(random_secret)"
  log "APP_API_KEY generated"
fi

if [[ -z "$(get_env_value TELEGRAM_WEBHOOK_SECRET)" ]]; then
  set_env_value "TELEGRAM_WEBHOOK_SECRET" "$(random_secret)"
  log "TELEGRAM_WEBHOOK_SECRET generated"
fi

if [[ -z "$(get_env_value WECHAT_TOKEN)" ]]; then
  set_env_value "WECHAT_TOKEN" "$(random_secret)"
  log "WECHAT_TOKEN generated"
fi

domain="$(get_env_value DOMAIN)"
telegram_token="$(get_env_value TELEGRAM_BOT_TOKEN)"

if [[ -n "${domain}" && "${domain}" != "ledger.example.com" ]]; then
  log "Starting in HTTPS webhook mode (domain: ${domain})..."
  ${DOCKER_CMD} compose -f docker-compose.server.yml up -d --build
  log "Done. Health check: https://${domain}/health"
  log "Mobile page: https://${domain}/app/"
else
  if [[ -n "${telegram_token}" ]]; then
    log "Starting in quick mode with Telegram polling..."
    log "Note: polling and webhook cannot be enabled at the same time."
    ${DOCKER_CMD} compose --profile tg-polling up -d --build
  else
    log "Starting in quick mode..."
    ${DOCKER_CMD} compose up -d --build
  fi
  log "Done. Health check: http://<server-ip>:8000/health"
  log "Mobile page: http://<server-ip>:8000/app/"
fi

log "Use this command to see logs:"
log "  ${DOCKER_CMD} compose logs -f --tail=100"

