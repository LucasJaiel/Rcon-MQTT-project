#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analise dos CSVs brutos do MQTTLoader.
Le todos os arquivos 'pubN_runR.csv' de uma pasta, calcula latencia
(media, desvio-padrao, p50/p95/p99) e throughput por cenario, salva as
tabelas e gera os graficos prontos para o artigo (PNG + PDF).

Requisitos:  pip install numpy matplotlib
Uso:         ajuste RESULTS_DIR abaixo e rode:  python analise_mqtt.py

Os percentis usam interpolacao linear (mesmo metodo do analisador HTML),
entao os numeros das duas ferramentas coincidem.
"""
import os, re, glob, csv
import numpy as np
import matplotlib.pyplot as plt

# ===== EDITE AQUI =====
RESULTS_DIR     = r"C:\Users\SEU_USUARIO\mqtt-exp-1\results"  # pasta com os pubN_runR.csv
RAMP_UP_S       = 3    # descarte inicial (use o MESMO valor da coleta)
RAMP_DOWN_S     = 3    # descarte final
OFFERED_PER_PUB = 10    # carga ofertada por publisher (msg/s); 100 ms -> 10
SAIDA_DIR       = RESULTS_DIR   # onde salvar tabelas e figuras
# ======================


def parse_csv(path):
    """Le um CSV do MQTTLoader. Retorna inicio, nº de envios (S),
    timestamps e latencias (us) das mensagens recebidas (R)."""
    start_ts, s_count = None, 0
    rec_ts, rec_lat = [], []
    with open(path, "r", newline="") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            try:
                ts = int(parts[0])
            except (ValueError, IndexError):
                continue
            if start_ts is None:
                start_ts = ts          # 1a linha = inicio da medicao
            ev = parts[2] if len(parts) > 2 else ""
            if ev == "S":
                s_count += 1
            elif ev == "R" and len(parts) > 3 and parts[3] != "":
                rec_ts.append(ts)
                rec_lat.append(int(parts[3]))
    return start_ts, s_count, rec_ts, rec_lat


def stats_for(path):
    """Estatisticas de um arquivo, sobre a janela de regime permanente."""
    start_ts, s_count, rec_ts, rec_lat = parse_csv(path)
    r_count = len(rec_lat)
    if r_count == 0:
        return None
    rec_ts = np.array(rec_ts, dtype=np.int64)
    rec_lat = np.array(rec_lat, dtype=np.float64)
    win_start = start_ts + RAMP_UP_S * 1_000_000
    win_end   = rec_ts.max() - RAMP_DOWN_S * 1_000_000
    win_sec   = (win_end - win_start) / 1_000_000
    if win_sec <= 0:
        return None
    mask = (rec_ts >= win_start) & (rec_ts <= win_end)
    lat_ms = rec_lat[mask] / 1000.0     # us -> ms
    if lat_ms.size == 0:
        return None
    return {
        "n": int(lat_ms.size), "win_sec": float(win_sec),
        "mean_ms": float(np.mean(lat_ms)),
        "sd_ms": float(np.std(lat_ms, ddof=1)) if lat_ms.size > 1 else 0.0,
        "p50": float(np.percentile(lat_ms, 50)),
        "p95": float(np.percentile(lat_ms, 95)),
        "p99": float(np.percentile(lat_ms, 99)),
        "min_ms": float(lat_ms.min()), "max_ms": float(lat_ms.max()),
        "throughput": lat_ms.size / win_sec,
        "integrity": (r_count / s_count) if s_count > 0 else float("nan"),
    }


def main():
    files = sorted(glob.glob(os.path.join(RESULTS_DIR, "pub*_run*.csv")))
    if not files:
        print(f"Nenhum CSV 'pubN_runR.csv' encontrado em {RESULTS_DIR}")
        return

    runs = []
    for path in files:
        name = os.path.basename(path)
        m = re.search(r"pub(\d+)[_-]?run(\d+)", name, re.IGNORECASE)
        if not m:
            print(f"  ignorado (nome fora do padrao): {name}")
            continue
        st = stats_for(path)
        if st is None:
            print(f"  sem dados validos: {name}")
            continue
        st.update({"pub": int(m.group(1)), "run": int(m.group(2)), "arquivo": name})
        runs.append(st)
        print(f"  OK  pub={st['pub']:>3} run={st['run']}  media={st['mean_ms']:6.2f} ms  "
              f"p95={st['p95']:6.2f}  p99={st['p99']:6.2f}  "
              f"thr={st['throughput']:6.1f} msg/s  R/S={st['integrity']:.3f}")

    if not runs:
        print("Nenhum dado valido para agregar.")
        return

    # ----- agregacao por cenario (media +- dp entre execucoes) -----
    pubs = sorted(set(r["pub"] for r in runs))
    agg = []
    for pub in pubs:
        g = [r for r in runs if r["pub"] == pub]
        col = lambda k: np.array([r[k] for r in g], dtype=float)
        sd  = lambda a: float(a.std(ddof=1)) if len(g) > 1 else 0.0
        agg.append({
            "pub": pub, "n": len(g),
            "mean_ms": float(col("mean_ms").mean()), "mean_sd": sd(col("mean_ms")),
            "p50": float(col("p50").mean()),
            "p95": float(col("p95").mean()), "p95_sd": sd(col("p95")),
            "p99": float(col("p99").mean()), "sd_ms": float(col("sd_ms").mean()),
            "throughput": float(col("throughput").mean()), "thr_sd": sd(col("throughput")),
            "integrity": float(col("integrity").mean()),
        })

    # ----- salva tabelas -----
    os.makedirs(SAIDA_DIR, exist_ok=True)
    run_csv = os.path.join(SAIDA_DIR, "por_execucao_mqtt.csv")
    with open(run_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["publishers", "execucao", "arquivo", "latencia_media_ms", "dp_ms",
                    "p50_ms", "p95_ms", "p99_ms", "min_ms", "max_ms",
                    "throughput_msg_s", "n_mensagens", "integridade_R_S"])
        for r in sorted(runs, key=lambda x: (x["pub"], x["run"])):
            w.writerow([r["pub"], r["run"], r["arquivo"],
                        f"{r['mean_ms']:.4f}", f"{r['sd_ms']:.4f}", f"{r['p50']:.4f}",
                        f"{r['p95']:.4f}", f"{r['p99']:.4f}", f"{r['min_ms']:.4f}",
                        f"{r['max_ms']:.4f}", f"{r['throughput']:.4f}", r["n"],
                        f"{r['integrity']:.4f}"])

    agg_csv = os.path.join(SAIDA_DIR, "agregado_mqtt.csv")
    with open(agg_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["publishers", "n_execucoes", "latencia_media_ms", "latencia_media_dp_ms",
                    "p50_ms", "p95_ms", "p95_dp_ms", "p99_ms", "dp_latencia_ms",
                    "throughput_msg_s", "throughput_dp", "integridade_R_S"])
        for r in agg:
            w.writerow([r["pub"], r["n"], f"{r['mean_ms']:.4f}", f"{r['mean_sd']:.4f}",
                        f"{r['p50']:.4f}", f"{r['p95']:.4f}", f"{r['p95_sd']:.4f}",
                        f"{r['p99']:.4f}", f"{r['sd_ms']:.4f}", f"{r['throughput']:.4f}",
                        f"{r['thr_sd']:.4f}", f"{r['integrity']:.4f}"])

    print(f"\nTabelas salvas:\n  {agg_csv}\n  {run_csv}")

    # ----- graficos -----
    x = np.array([r["pub"] for r in agg], dtype=float)

    fig1, ax1 = plt.subplots(figsize=(7, 4.5))
    ax1.errorbar(x, [r["mean_ms"] for r in agg], yerr=[r["mean_sd"] for r in agg],
                 marker="o", capsize=4, label="Latencia media (+-dp entre execucoes)")
    ax1.plot(x, [r["p95"] for r in agg], marker="s", linestyle="--", label="p95")
    ax1.set_xlabel("Publishers simultaneos")
    ax1.set_ylabel("Latencia de entrega (ms)")
    ax1.set_title("Latencia x numero de publishers")
    ax1.set_xticks(x); ax1.grid(True, alpha=0.3); ax1.legend()
    fig1.tight_layout()
    fig1.savefig(os.path.join(SAIDA_DIR, "fig_latencia.png"), dpi=150)
    fig1.savefig(os.path.join(SAIDA_DIR, "fig_latencia.pdf"))

    fig2, ax2 = plt.subplots(figsize=(7, 4.5))
    ax2.errorbar(x, [r["throughput"] for r in agg], yerr=[r["thr_sd"] for r in agg],
                 marker="o", capsize=4, label="Throughput entregue (medido)")
    ax2.plot(x, x * OFFERED_PER_PUB, linestyle="--", color="gray",
             label="Carga ofertada (teorica)")
    ax2.set_xlabel("Publishers simultaneos")
    ax2.set_ylabel("Throughput (msg/s)")
    ax2.set_title("Throughput x numero de publishers")
    ax2.set_xticks(x); ax2.grid(True, alpha=0.3); ax2.legend()
    fig2.tight_layout()
    fig2.savefig(os.path.join(SAIDA_DIR, "fig_throughput.png"), dpi=150)
    fig2.savefig(os.path.join(SAIDA_DIR, "fig_throughput.pdf"))

    print("Graficos salvos:\n  fig_latencia.png / .pdf\n  fig_throughput.png / .pdf")
    # plt.show()   # descomente para abrir as figuras em janela


if __name__ == "__main__":
    main()
