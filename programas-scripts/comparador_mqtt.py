#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comparador das duas condicoes do experimento MQTT:
  - "livre"     : broker sem limite de CPU (recursos plenos)
  - "restrito"  : broker com cota de CPU (dispositivo sobrecarregado)

Le os CSVs 'pubN_runR.csv' de cada pasta, agrega por cenario e gera as
figuras que sobrepoem as duas condicoes (latencia e throughput), prontas
para o artigo (PNG + PDF). Tambem salva uma tabela comparativa.

Requisitos:  pip install numpy matplotlib
Uso:         ajuste os caminhos abaixo e rode:  python comparador_mqtt.py

Os percentis usam interpolacao linear (mesmo metodo do analise_mqtt.py e do
analisador HTML), entao todos os numeros sao consistentes entre as ferramentas.
"""
import os, re, glob, csv
import numpy as np
import matplotlib.pyplot as plt

# ===== EDITE AQUI =====
DIR_LIVRE       = os.path.expanduser("~/mqtt-exp-1/results-livre")
DIR_RESTRITO    = os.path.expanduser("~/mqtt-exp-1/results-restrito")
SAIDA_DIR       = os.path.expanduser("~/mqtt-exp-1")
RAMP_UP_S       = 3          # mesmos valores usados na coleta
RAMP_DOWN_S     = 3
OFFERED_PER_PUB = 10         # msg/s por publisher (intervalo 100 ms)
ROTULO_LIVRE    = "Recursos plenos"
ROTULO_RESTRITO = "Sobrecarregado (CPU 0,02)"
# ======================


def parse_csv(path):
    start_ts, s_count = None, 0
    rec_ts, rec_lat = [], []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            p = line.split(",")
            try:
                ts = int(p[0])
            except (ValueError, IndexError):
                continue
            if start_ts is None:
                start_ts = ts
            ev = p[2] if len(p) > 2 else ""
            if ev == "S":
                s_count += 1
            elif ev == "R" and len(p) > 3 and p[3] != "":
                rec_ts.append(ts)
                rec_lat.append(int(p[3]))
    return start_ts, s_count, rec_ts, rec_lat


def stats_for(path):
    start_ts, s_count, rec_ts, rec_lat = parse_csv(path)
    if not rec_lat:
        return None
    rec_ts = np.array(rec_ts, np.int64)
    rec_lat = np.array(rec_lat, np.float64)
    ws = start_ts + RAMP_UP_S * 1_000_000
    we = rec_ts.max() - RAMP_DOWN_S * 1_000_000
    win = (we - ws) / 1_000_000
    if win <= 0:
        return None
    lat = rec_lat[(rec_ts >= ws) & (rec_ts <= we)] / 1000.0
    if lat.size == 0:
        return None
    return {
        "mean_ms": float(lat.mean()),
        "p95": float(np.percentile(lat, 95)),
        "throughput": lat.size / win,
        "integrity": (len(rec_lat) / s_count) if s_count else float("nan"),
    }


def aggregate(folder):
    by_pub = {}
    for path in sorted(glob.glob(os.path.join(folder, "pub*_run*.csv"))):
        m = re.search(r"pub(\d+)[_-]?run(\d+)", os.path.basename(path), re.I)
        if not m:
            continue
        st = stats_for(path)
        if st is None:
            continue
        by_pub.setdefault(int(m.group(1)), []).append(st)
    rows = []
    for pub in sorted(by_pub):
        g = by_pub[pub]
        col = lambda k: np.array([r[k] for r in g])
        sd = lambda a: float(a.std(ddof=1)) if len(g) > 1 else 0.0
        rows.append({
            "pub": pub,
            "mean_ms": float(col("mean_ms").mean()), "mean_sd": sd(col("mean_ms")),
            "p95": float(col("p95").mean()),
            "throughput": float(col("throughput").mean()), "thr_sd": sd(col("throughput")),
            "integrity": float(col("integrity").mean()),
        })
    return rows


def main():
    L = aggregate(DIR_LIVRE)
    R = aggregate(DIR_RESTRITO)
    if not L:
        print(f"Sem dados em {DIR_LIVRE}")
    if not R:
        print(f"Sem dados em {DIR_RESTRITO}")
    if not L or not R:
        print("Preciso das duas condicoes para comparar.")
        return

    pubs = sorted(set([r["pub"] for r in L]) | set([r["pub"] for r in R]))
    dL = {r["pub"]: r for r in L}
    dR = {r["pub"]: r for r in R}

    # ----- tabela comparativa -----
    os.makedirs(SAIDA_DIR, exist_ok=True)
    out_csv = os.path.join(SAIDA_DIR, "comparativo_mqtt.csv")
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["publishers", "lat_livre_ms", "lat_restrito_ms",
                    "p95_livre_ms", "p95_restrito_ms",
                    "thr_livre_msg_s", "thr_restrito_msg_s",
                    "integridade_livre", "integridade_restrito"])
        for p in pubs:
            a, b = dL.get(p), dR.get(p)
            w.writerow([p,
                        f"{a['mean_ms']:.3f}" if a else "", f"{b['mean_ms']:.3f}" if b else "",
                        f"{a['p95']:.3f}" if a else "", f"{b['p95']:.3f}" if b else "",
                        f"{a['throughput']:.1f}" if a else "", f"{b['throughput']:.1f}" if b else "",
                        f"{a['integrity']:.3f}" if a else "", f"{b['integrity']:.3f}" if b else ""])
    print("Tabela comparativa:", out_csv)

    C_L, C_R = "#2E7D8F", "#D1495B"

    # ----- figura 1: latencia (escala log no eixo y) -----
    fig, ax = plt.subplots(figsize=(7.5, 4.8))
    ax.errorbar([r["pub"] for r in L], [r["mean_ms"] for r in L],
                yerr=[r["mean_sd"] for r in L], marker="o", capsize=4,
                color=C_L, label=ROTULO_LIVRE)
    ax.errorbar([r["pub"] for r in R], [r["mean_ms"] for r in R],
                yerr=[r["mean_sd"] for r in R], marker="s", capsize=4,
                color=C_R, label=ROTULO_RESTRITO)
    ax.set_yscale("log")  # faixa dinamica enorme (ms a milhares de ms)
    ax.set_xlabel("Publishers simultaneos")
    ax.set_ylabel("Latencia media de entrega (ms, escala log)")
    ax.set_title("Latencia: recursos plenos x dispositivo sobrecarregado")
    ax.set_xticks(pubs)
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(SAIDA_DIR, "fig_comparativo_latencia.png"), dpi=150)
    fig.savefig(os.path.join(SAIDA_DIR, "fig_comparativo_latencia.pdf"))

    # ----- figura 2: throughput -----
    fig2, ax2 = plt.subplots(figsize=(7.5, 4.8))
    ax2.errorbar([r["pub"] for r in L], [r["throughput"] for r in L],
                 yerr=[r["thr_sd"] for r in L], marker="o", capsize=4,
                 color=C_L, label=ROTULO_LIVRE)
    ax2.errorbar([r["pub"] for r in R], [r["throughput"] for r in R],
                 yerr=[r["thr_sd"] for r in R], marker="s", capsize=4,
                 color=C_R, label=ROTULO_RESTRITO)
    xx = np.array(pubs, float)
    ax2.plot(xx, xx * OFFERED_PER_PUB, "--", color="gray", label="Carga ofertada (teorica)")
    ax2.set_xlabel("Publishers simultaneos")
    ax2.set_ylabel("Throughput entregue (msg/s)")
    ax2.set_title("Throughput: recursos plenos x dispositivo sobrecarregado")
    ax2.set_xticks(pubs)
    ax2.grid(True, alpha=0.3)
    ax2.legend()
    fig2.tight_layout()
    fig2.savefig(os.path.join(SAIDA_DIR, "fig_comparativo_throughput.png"), dpi=150)
    fig2.savefig(os.path.join(SAIDA_DIR, "fig_comparativo_throughput.pdf"))

    print("Figuras salvas:")
    print("  fig_comparativo_latencia.png / .pdf")
    print("  fig_comparativo_throughput.png / .pdf")
    # plt.show()  # descomente para abrir em janela


if __name__ == "__main__":
    main()
