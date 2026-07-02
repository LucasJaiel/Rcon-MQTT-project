#!/usr/bin/env bash
# Orquestrador do experimento MQTT — gerador de carga em Debian (separado do broker).
# Roda MQTTLoader (publishers + subscriber) num unico processo (relogio unico, sem NTP).

set -uo pipefail

# ===== EDITE AQUI =====
SCENARIOS=(50)     # nº de publishers (independente)
REPETITIONS=3
EXEC_TIME=60                   # exec_time (s)
INTERVAL_US=100000              # 100 ms em MICROSSEGUNDOS (nao mude para 100)
PAYLOAD=64                      # bytes (>= 8)
QOS=1
TOPIC="exp/throughput"
MQTT_VERSION=5                  # 5 = v5.0 ; 3 = v3.1.1 (reporte qual usou)
RAMP_UP=3                       # use os MESMOS valores no analisador/Python
RAMP_DOWN=3

CONDICAO="livre"             # "livre" (broker sem limite) ou "restrito" (CPU limitada)
CPUS_RESTRITO="0.02"            # cota de CPU do broker na condicao restrita

BROKER_IP="10.0.42.71"        # IP do notebook do broker
BROKER_PORT=1883

MQTTLOADER_DIR="$HOME/rcon-mqtt-exp-1/mqttloader-0.8.6/mqttloader"   # pasta com bin/mqttloader
WORK_DIR="$HOME/rcon-mqtt-exp-1"

USE_SSH=false                   # true = recria o broker automaticamente via SSH
SSH_USER="aluno"                # usuario do notebook do broker
# ======================

if [ "$CONDICAO" = "restrito" ]; then CPUS="$CPUS_RESTRITO"; else CPUS=""; fi
RAW_DIR="$WORK_DIR/raw"
RESULTS_DIR="$WORK_DIR/results-$CONDICAO"
LAUNCHER="$MQTTLOADER_DIR/bin/mqttloader"
CONF_RUN="$WORK_DIR/run.conf"
mkdir -p "$RAW_DIR" "$RESULTS_DIR"

if [ ! -x "$LAUNCHER" ]; then
  echo "ERRO: nao achei o executavel $LAUNCHER (rode: chmod +x $LAUNCHER)"; exit 1
fi

recreate_broker () {
  if [ "$USE_SSH" = true ]; then
    echo "  Recriando broker via SSH (CPU: ${CPUS:-sem limite})..."
    ssh "$SSH_USER@$BROKER_IP" "bash ~/mqtt-exp-1/recreate-broker.sh $CPUS"
    sleep 3
  else
    read -rp "  >> No notebook do broker rode:  ./recreate-broker.sh $CPUS   e tecle ENTER "
  fi
}

echo "### Condicao: $CONDICAO  (CPU broker: ${CPUS:-sem limite}) ###"
for pub in "${SCENARIOS[@]}"; do
  for run in $(seq 1 "$REPETITIONS"); do
    echo "=== Publishers=$pub  Execucao=$run/$REPETITIONS  [$CONDICAO] ==="
    recreate_broker
    rm -f "$RAW_DIR"/*.csv 2>/dev/null

    cat > "$CONF_RUN" << EOF
broker = $BROKER_IP
broker_port = $BROKER_PORT
mqtt_version = $MQTT_VERSION
num_publishers = $pub
num_subscribers = 1
qos_publisher = $QOS
qos_subscriber = $QOS
topic = $TOPIC
payload = $PAYLOAD
interval = $INTERVAL_US
num_messages = 1000000
exec_time = $EXEC_TIME
ramp_up = $RAMP_UP
ramp_down = $RAMP_DOWN
subscriber_timeout = 10
log_level = INFO
output = $RAW_DIR
EOF

    log="$RESULTS_DIR/pub${pub}_run${run}.console.txt"
    "$LAUNCHER" -c "$CONF_RUN" 2>&1 | tee "$log"

    csv=$(find "$RAW_DIR" -maxdepth 1 -name '*.csv' -printf '%T@ %p\n' 2>/dev/null \
          | sort -rn | head -1 | cut -d' ' -f2-)
    if [ -n "$csv" ]; then
      mv "$csv" "$RESULTS_DIR/pub${pub}_run${run}.csv"
      echo "  CSV salvo: results-$CONDICAO/pub${pub}_run${run}.csv"
    else
      echo "  AVISO: nenhum CSV gerado em pub=$pub run=$run"
    fi
    sleep 3
  done
done
echo "Concluido [$CONDICAO]. CSVs em $RESULTS_DIR"
