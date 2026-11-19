#!/usr/bin/env bash
set -Eeuo pipefail

# Install the ShopVPN SSH Agent on a Debian/Ubuntu Linux node.
# Run from the project root as root: bash deploy/install-shopvpn-ssh-agent.sh

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/install-shopvpn-ssh-agent.sh" >&2
  exit 1
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENT_SOURCE="${PROJECT_ROOT}/ssh_node_agent.py"
SERVICE_SOURCE="${PROJECT_ROOT}/deploy/shopvpn-ssh-agent.service"
SSHD_TEMPLATE_SOURCE="${PROJECT_ROOT}/deploy/shopvpn-sshd@.service"

if [[ ! -f "${AGENT_SOURCE}" || ! -f "${SERVICE_SOURCE}" || ! -f "${SSHD_TEMPLATE_SOURCE}" ]]; then
  echo "Run this script from the extracted ShopVPN project; agent/service files are missing." >&2
  exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This helper supports Debian/Ubuntu (apt-get) only. Install Python 3 and aiohttp manually." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-aiohttp openssh-server nftables openssl

install -d -o root -g root -m 0755 /opt/shopvpn /var/lib/shopvpn-ssh-agent /etc/shopvpn/sshd
install -o root -g root -m 0755 "${AGENT_SOURCE}" /opt/shopvpn/ssh_node_agent.py
ssh-keygen -A

if [[ ! -f /etc/shopvpn-ssh-agent.env ]]; then
  TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  umask 077
  cat > /etc/shopvpn-ssh-agent.env <<EOF
SHOPVPN_AGENT_TOKEN=${TOKEN}
SHOPVPN_AGENT_HOST=127.0.0.1
SHOPVPN_AGENT_PORT=8765
SHOPVPN_AGENT_DB=/var/lib/shopvpn-ssh-agent/agent.db
SHOPVPN_NFT_ACCOUNTING=0
EOF
  chmod 0600 /etc/shopvpn-ssh-agent.env
  echo
  echo "A new Agent token was created in /etc/shopvpn-ssh-agent.env."
  echo "Copy SHOPVPN_AGENT_TOKEN securely to the ShopVPN main server's environment as the matching secret."
else
  chmod 0600 /etc/shopvpn-ssh-agent.env
  echo "Existing /etc/shopvpn-ssh-agent.env preserved."
fi

# Dedicated sshd instances listen on per-account ports; the main sshd is restricted below.
install -o root -g root -m 0644 "${SSHD_TEMPLATE_SOURCE}" /etc/systemd/system/shopvpn-sshd@.service
groupadd --system shopvpnssh 2>/dev/null || true

  # UDP gateway for SSH clients (V2Box, NetMod, ...). A missing gateway can
  # make a client appear connected while DNS/UDP traffic does not pass.
  # It must listen on loopback only; clients configure UDPGW port 7300.
  echo "[ShopVPN] Installing badvpn-udpgw..."
  UDPGW_BIN="$(command -v badvpn-udpgw 2>/dev/null || true)"
  if [[ -z "${UDPGW_BIN}" ]]; then
    if apt-get install -y badvpn; then
      UDPGW_BIN="$(command -v badvpn-udpgw 2>/dev/null || true)"
    else
      echo "[ShopVPN] badvpn package unavailable; building badvpn-udpgw from source." >&2
    fi
  fi
  if [[ -z "${UDPGW_BIN}" ]]; then
    apt-get install -y cmake build-essential git
    rm -rf /tmp/shopvpn-badvpn-build
    git clone --depth 1 https://github.com/ambrop72/badvpn /tmp/shopvpn-badvpn-build
    cmake -S /tmp/shopvpn-badvpn-build -B /tmp/shopvpn-badvpn-build/build \
      -DBUILD_NOTHING_BY_DEFAULT=1 -DBUILD_UDPGW=1
    cmake --build /tmp/shopvpn-badvpn-build/build --parallel "$(nproc)"
    cmake --install /tmp/shopvpn-badvpn-build/build
    UDPGW_BIN="$(command -v badvpn-udpgw 2>/dev/null || true)"
    if [[ -z "${UDPGW_BIN}" && -x /usr/local/bin/badvpn-udpgw ]]; then
      UDPGW_BIN=/usr/local/bin/badvpn-udpgw
    fi
  fi
  if [[ -z "${UDPGW_BIN}" || ! -x "${UDPGW_BIN}" ]]; then
    echo "[ShopVPN] ERROR: badvpn-udpgw installation failed; executable not found." >&2
    exit 1
  fi
  echo "[ShopVPN] UDPGW executable: ${UDPGW_BIN}"
  cat > /etc/systemd/system/shopvpn-udpgw.service <<EOF
[Unit]
Description=ShopVPN UDP gateway for SSH accounts (127.0.0.1:7300)
After=network.target

[Service]
Type=simple
ExecStart=${UDPGW_BIN} --listen-addr 127.0.0.1:7300 --max-clients 1000 --max-connections-for-client 64
Restart=always
RestartSec=2
User=nobody
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now shopvpn-udpgw.service
  UDPGW_READY=0
  for attempt in $(seq 1 5); do
    if systemctl is-active --quiet shopvpn-udpgw.service && ss -ltn 2>/dev/null | grep -Eq '127\.0\.0\.1:7300([[:space:]]|$)'; then
      UDPGW_READY=1
      break
    fi
    sleep 1
  done
  if [[ "${UDPGW_READY}" -ne 1 ]]; then
    echo "[ShopVPN] ERROR: shopvpn-udpgw did not become active/listen on 127.0.0.1:7300." >&2
    systemctl --no-pager --full status shopvpn-udpgw.service >&2 || true
    journalctl -u shopvpn-udpgw.service -n 20 --no-pager >&2 || true
    exit 1
  fi
  echo "[ShopVPN] UDPGW is active and listening on 127.0.0.1:7300."

# Prevent ShopVPN users from bypassing per-account listener ports and nftables
# accounting via the machine's regular administrative sshd port. The isolated
# shopvpn-sshd@ instances use their own config files and are not affected.
SSHD_CONFIG=/etc/ssh/sshd_config
SSHD_BACKUP="${SSHD_CONFIG}.shopvpn-backup.$(date +%Y%m%d%H%M%S)"
if ! grep -Fq '# BEGIN SHOPVPN SSH ACCOUNT RESTRICTIONS' "${SSHD_CONFIG}"; then
  cp -a "${SSHD_CONFIG}" "${SSHD_BACKUP}"
  cat >> "${SSHD_CONFIG}" <<'EOF'

# BEGIN SHOPVPN SSH ACCOUNT RESTRICTIONS
Match Group shopvpnssh
    AllowTcpForwarding no
    AllowStreamLocalForwarding no
    AllowAgentForwarding no
    X11Forwarding no
    PermitTunnel no
    PermitTTY no
    MaxSessions 0
    ForceCommand /usr/sbin/nologin
# END SHOPVPN SSH ACCOUNT RESTRICTIONS
EOF
  if ! /usr/sbin/sshd -t -f "${SSHD_CONFIG}"; then
    cp -a "${SSHD_BACKUP}" "${SSHD_CONFIG}"
    echo "OpenSSH configuration validation failed; restored the previous config." >&2
    exit 1
  fi
fi

install -o root -g root -m 0644 "${SSHD_TEMPLATE_SOURCE}" /etc/systemd/system/shopvpn-sshd@.service
install -o root -g root -m 0644 "${SERVICE_SOURCE}" /etc/systemd/system/shopvpn-ssh-agent.service
systemctl daemon-reload
if systemctl is-active --quiet ssh; then
  systemctl reload ssh
elif systemctl is-active --quiet sshd; then
  systemctl reload sshd
fi
systemctl enable --now shopvpn-ssh-agent

systemctl --no-pager --full status shopvpn-ssh-agent || true
cat <<'EOF'

Agent installed and bound to 127.0.0.1:8765 by default.
Do not expose this port directly to the public Internet. Use a private network or
an IP-restricted TLS reverse proxy. SSH accounts listen on unique TCP ports in
20000-39999; open this range in your firewall/security group for client access.
Per-account nftables accounting remains OFF until you test it and set
SHOPVPN_NFT_ACCOUNTING=1 in /etc/shopvpn-ssh-agent.env, then restart the Agent.
EOF
