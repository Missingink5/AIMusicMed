#!/bin/sh
set -eu

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer as root." >&2
  exit 1
fi

. /etc/os-release
if [ "${ID:-}" != "ubuntu" ] || [ "${VERSION_CODENAME:-}" != "noble" ]; then
  echo "Expected Ubuntu 24.04 (noble), found ${PRETTY_NAME:-unknown}." >&2
  exit 1
fi

conflicts=""
for package in docker.io docker-compose docker-compose-v2 docker-doc podman-docker containerd runc; do
  if dpkg-query -W -f='${db:Status-Abbrev}' "$package" 2>/dev/null | grep -q '^ii'; then
    conflicts="$conflicts $package"
  fi
done
if [ -n "$conflicts" ]; then
  # Word splitting is intentional: this contains only names from the fixed list above.
  apt-get remove -y $conflicts
fi

apt-get update
apt-get install -y ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

architecture="$(dpkg --print-architecture)"
cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${VERSION_CODENAME}
Components: stable
Architectures: ${architecture}
Signed-By: /etc/apt/keyrings/docker.asc
EOF

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
usermod -aG docker ubuntu

docker version
docker compose version
docker run --rm hello-world
