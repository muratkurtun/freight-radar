#!/usr/bin/env bash
# Hetzner Ubuntu bootstrap — one-shot, idempotent, safe to re-run.
#
# Sets up a single VPS to host the Opportunity Radar stack via
# docker-compose.prod.yml. Installs Docker (+ Compose plugin), locks
# down SSH, enables UFW, schedules unattended-upgrades, makes the
# 'deploy' user + /opt/opportunity-radar directory.
#
# NGINX IS NOT INSTALLED ON THE HOST. The stack ships its own nginx
# container (see docker-compose.prod.yml). Installing a second nginx
# here would race for ports 80/443 and the stack would fail to start.
# This script only *opens* those ports at the firewall level.
#
# Usage (as root, fresh Hetzner box):
#   scp ops/server-setup.sh root@<ip>:/root/
#   ssh root@<ip>
#   bash /root/server-setup.sh
#
# Optional env overrides:
#   DEPLOY_USER=deploy  APP_DIR=/opt/opportunity-radar  SSH_PORT=22

set -euo pipefail

DEPLOY_USER="${DEPLOY_USER:-deploy}"
APP_DIR="${APP_DIR:-/opt/opportunity-radar}"
BACKUP_DIR="${BACKUP_DIR:-/opt/or-backups}"
BACKUP_LOG="${BACKUP_LOG:-/var/log/or-backup.log}"
SSH_PORT="${SSH_PORT:-22}"

log()  { printf '\n\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\n\033[1;33m!!\033[0m  %s\n' "$*" >&2; }
die()  { printf '\n\033[1;31mXX\033[0m  %s\n' "$*" >&2; exit 1; }

# ----------------------------------------------------------------------
# 0. Safety checks
# ----------------------------------------------------------------------
[[ $EUID -eq 0 ]] || die "Run this script as root."

# shellcheck disable=SC1091
. /etc/os-release
case "${ID:-}:${VERSION_ID:-}" in
    ubuntu:22.04|ubuntu:24.04) ;;
    *) die "Unsupported OS: ${PRETTY_NAME:-unknown} (need Ubuntu 22.04 or 24.04)" ;;
esac

# ----------------------------------------------------------------------
# 1. Base packages
# ----------------------------------------------------------------------
log "Updating apt + installing base packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
    ca-certificates curl gnupg git rsync cron \
    ufw fail2ban unattended-upgrades tzdata

# ----------------------------------------------------------------------
# 2. Timezone UTC (everything logs in UTC, scheduler assumes UTC)
# ----------------------------------------------------------------------
log "Setting timezone to UTC"
timedatectl set-timezone UTC

# ----------------------------------------------------------------------
# 3. Docker + Compose plugin (official Docker apt repo)
# ----------------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
    log "Installing Docker Engine + Compose plugin"
    install -m 0755 -d /etc/apt/keyrings
    if [[ ! -f /etc/apt/keyrings/docker.gpg ]]; then
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
            | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        chmod a+r /etc/apt/keyrings/docker.gpg
    fi

    ARCH="$(dpkg --print-architecture)"
    CODENAME="$(. /etc/os-release && echo "$VERSION_CODENAME")"
    echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu ${CODENAME} stable" \
        > /etc/apt/sources.list.d/docker.list

    apt-get update -qq
    apt-get install -y -qq \
        docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin

    systemctl enable --now docker
else
    log "Docker already installed — skipping install"
fi

# ----------------------------------------------------------------------
# 4. Docker log rotation (prevents /var/lib/docker/containers from
#    filling the 40GB disk over time)
# ----------------------------------------------------------------------
mkdir -p /etc/docker
if [[ ! -f /etc/docker/daemon.json ]] || ! grep -q '"max-size"' /etc/docker/daemon.json; then
    log "Configuring Docker log rotation (10m × 3 files per container)"
    cat > /etc/docker/daemon.json <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
JSON
    systemctl restart docker
else
    log "Docker log rotation already configured"
fi

# ----------------------------------------------------------------------
# 5. Deploy user + docker group
# ----------------------------------------------------------------------
if ! id -u "$DEPLOY_USER" >/dev/null 2>&1; then
    log "Creating user: $DEPLOY_USER"
    adduser --disabled-password --gecos "" "$DEPLOY_USER"
fi
usermod -aG docker,sudo "$DEPLOY_USER"

# Passwordless sudo for the deploy user — they'll run compose / alembic
# / backup scripts as part of day-to-day ops. Remove this block if you
# want password-gated sudo.
SUDOERS_FILE="/etc/sudoers.d/${DEPLOY_USER}-nopasswd"
if [[ ! -f "$SUDOERS_FILE" ]]; then
    echo "${DEPLOY_USER} ALL=(ALL) NOPASSWD:ALL" > "$SUDOERS_FILE"
    chmod 440 "$SUDOERS_FILE"
fi

# ----------------------------------------------------------------------
# 6. SSH keys — copy from root so we don't lock ourselves out
# ----------------------------------------------------------------------
if [[ -s /root/.ssh/authorized_keys ]]; then
    log "Copying root's authorized_keys to $DEPLOY_USER (dedup via sort -u)"
    install -d -m 700 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh"
    touch "/home/$DEPLOY_USER/.ssh/authorized_keys"
    sort -u /root/.ssh/authorized_keys "/home/$DEPLOY_USER/.ssh/authorized_keys" \
        -o "/home/$DEPLOY_USER/.ssh/authorized_keys"
    chown "$DEPLOY_USER:$DEPLOY_USER" "/home/$DEPLOY_USER/.ssh/authorized_keys"
    chmod 600 "/home/$DEPLOY_USER/.ssh/authorized_keys"
else
    warn "/root/.ssh/authorized_keys is empty or missing."
    warn "Add your public key to /home/$DEPLOY_USER/.ssh/authorized_keys BEFORE the next run,"
    warn "otherwise SSH hardening in step 7 will lock you out."
fi

# ----------------------------------------------------------------------
# 7. SSH hardening — only when the deploy user has a usable key
# ----------------------------------------------------------------------
if [[ -s "/home/$DEPLOY_USER/.ssh/authorized_keys" ]]; then
    log "Hardening SSH (disable root login + password auth)"

    # Drop-in file — Ubuntu 22.04+ includes /etc/ssh/sshd_config.d/*.conf.
    # A drop-in is cleaner than sed on the main file: re-runs just
    # overwrite this single file.
    mkdir -p /etc/ssh/sshd_config.d
    cat > /etc/ssh/sshd_config.d/99-hardening.conf <<'EOF'
# Managed by server-setup.sh
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
PermitEmptyPasswords no
ChallengeResponseAuthentication no
KbdInteractiveAuthentication no
EOF

    # Validate first. If the config is broken, do NOT restart sshd —
    # that would drop the current session.
    if sshd -t; then
        systemctl restart ssh
    else
        die "sshd -t failed; refusing to restart sshd to avoid lockout"
    fi
else
    warn "SKIPPING SSH hardening (deploy user has no authorized_keys)"
fi

# ----------------------------------------------------------------------
# 8. UFW firewall
#    Only 22 / 80 / 443 open. 80/443 terminate inside the nginx
#    container (see docker-compose.prod.yml) — we do NOT install nginx
#    on the host. DB and backend ports are not exposed to the host at
#    all by compose, so no ufw rule needed for them.
# ----------------------------------------------------------------------
log "Configuring UFW firewall"
ufw default deny incoming  >/dev/null
ufw default allow outgoing >/dev/null
ufw allow "${SSH_PORT}/tcp" comment 'SSH'  >/dev/null
ufw allow 80/tcp            comment 'HTTP (ACME + HTTPS redirect)' >/dev/null
ufw allow 443/tcp           comment 'HTTPS' >/dev/null
ufw --force enable  >/dev/null
ufw status verbose | sed 's/^/    /'

# ----------------------------------------------------------------------
# 9. fail2ban — SSH brute-force protection, default jail is enough.
# ----------------------------------------------------------------------
log "Enabling fail2ban"
systemctl enable --now fail2ban

# ----------------------------------------------------------------------
# 10. unattended-upgrades — security patches install automatically.
# ----------------------------------------------------------------------
log "Enabling unattended-upgrades"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
systemctl enable --now unattended-upgrades >/dev/null

# ----------------------------------------------------------------------
# 11. Swap (2GB) — CX22 ships without swap. Prevents OOM kills during
#     LLM response bursts or Postgres memory spikes.
# ----------------------------------------------------------------------
if [[ ! -f /swapfile ]]; then
    log "Creating 2GB swap file"
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap  /swapfile >/dev/null
    swapon  /swapfile
    if ! grep -q '^/swapfile' /etc/fstab; then
        echo "/swapfile none swap sw 0 0" >> /etc/fstab
    fi
else
    log "Swap file already present — skipping"
fi

# ----------------------------------------------------------------------
# 12. Application directories
# ----------------------------------------------------------------------
log "Creating application directories"
install -d -m 755 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$APP_DIR"
install -d -m 755 -o "$DEPLOY_USER" -g "$DEPLOY_USER" "$BACKUP_DIR"

# Backup log file — pg_backup.sh will append to it via cron
if [[ ! -f "$BACKUP_LOG" ]]; then
    install -m 640 -o "$DEPLOY_USER" -g "$DEPLOY_USER" /dev/null "$BACKUP_LOG"
fi

# ----------------------------------------------------------------------
# Done
# ----------------------------------------------------------------------
cat <<DONE

================================================================
  Bootstrap complete.
================================================================

  OS          : $PRETTY_NAME
  Docker      : $(docker --version | awk '{print $3}' | tr -d ',')
  Compose     : $(docker compose version --short 2>/dev/null || echo '?')
  Deploy user : ${DEPLOY_USER}
  App dir     : ${APP_DIR}
  Backup dir  : ${BACKUP_DIR}
  Firewall    : $(ufw status | head -1 | awk '{print $2}')

Next steps — run as the '${DEPLOY_USER}' user, not root:

  ssh ${DEPLOY_USER}@<server-ip>

  cd ${APP_DIR}
  git clone <repo-url> .
  cp .env.example .env && nano .env        # fill DOMAIN, JWT_SECRET, OPENAI_API_KEY, ...
  chmod 600 .env

  # Substitute the real domain into the nginx site config (one-off):
  sed -i "s/\\\${DOMAIN}/\$(grep ^DOMAIN= .env | cut -d= -f2)/g" \\
      ops/nginx/conf.d/opportunity-radar.conf

  docker compose -f docker-compose.prod.yml build
  docker compose -f docker-compose.prod.yml up -d postgres
  docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head
  ./ops/init-letsencrypt.sh <domain> <email>
  docker compose -f docker-compose.prod.yml up -d

  # Daily backup cron:
  (crontab -l 2>/dev/null; \\
   echo "0 3 * * * ${APP_DIR}/ops/backup/pg_backup.sh >> ${BACKUP_LOG} 2>&1") \\
  | crontab -

================================================================

DONE
