#!/usr/bin/env bash
set -euo pipefail
NAME=mosq-exp-1
CONF="$HOME/mqtt-exp-1/mosquitto.conf"
CPUS="${1:-}"                      # ./recreate-broker.sh 0.15  -> restrito ; sem arg -> livre

docker rm -f "$NAME" 2>/dev/null || true
CPU_FLAG=""; [ -n "$CPUS" ] && CPU_FLAG="--cpus=$CPUS"

docker run -d --rm --name "$NAME" $CPU_FLAG \
  -p 1883:1883 \
  -v "$CONF":/mosquitto/config/mosquitto.conf:ro \
  eclipse-mosquitto:2

sleep 2
echo "Broker recriado: $NAME  (CPU: ${CPUS:-sem limite})"
docker ps --filter name=$NAME --format '{{.Image}} {{.Status}}'
