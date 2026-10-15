#!/usr/bin/env python3
"""Réplicas con semillas distintas: media, desviación e intervalo de confianza de cada KPI, y
comparación pareada de dos escenarios. Sirve para cualquier ejecutor que acepte una semilla y
escriba un JSON de KPIs (números, o dicts anidados de números).

Uso:
    py replicas.py --n 10 --cmd "py -3.12 ejecutar.py --dias 5 --semilla {semilla} --json {json}"
    py replicas.py --n 10 --cmd "...escenario A..." --comparar "...escenario B..." --kpi OTIF_% --kpi ciclo_h
Opciones:
    --semilla0 1        primera semilla (réplica i usa semilla0 + i)
    --paralelo 1        procesos simultáneos (FlexSim arranca una vez por proceso; con varios a la
                        vez se han visto *segmentation fault*: por defecto, de uno en uno)
    --precision 0.05    semiancho relativo deseado del IC; avisa de cuántas réplicas harían falta
    --confianza 0.95    0.90, 0.95 o 0.99
    --salida res.json   todo: réplicas, resumen y comparación
    --csv res.csv       una fila por réplica y KPI

La plantilla de --cmd lleva {semilla} y {json} (fichero temporal que el ejecutor debe escribir).
Una réplica que no escribe JSON (p. ej. el proceso muere) se reintenta una vez y, si vuelve a
fallar, se excluye y se avisa.

Con --comparar, cada réplica del escenario B usa la MISMA semilla que la de A (números aleatorios
comunes): se analiza la diferencia B - A réplica a réplica, que tiene mucha menos varianza que
comparar dos medias sueltas. «Significativa» = el IC de la diferencia no contiene el 0.
"""
import argparse
import io
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except AttributeError:
    pass

# t de Student bilateral: T[confianza][gl] (gl 1-30); para gl > 30 se usa la normal.
_T = {
    0.90: [6.314, 2.920, 2.353, 2.132, 2.015, 1.943, 1.895, 1.860, 1.833, 1.812, 1.796, 1.782, 1.771, 1.761, 1.753,
           1.746, 1.740, 1.734, 1.729, 1.725, 1.721, 1.717, 1.714, 1.711, 1.708, 1.706, 1.703, 1.701, 1.699, 1.697],
    0.95: [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.160, 2.145, 2.131,
           2.120, 2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042],
    0.99: [63.657, 9.925, 5.841, 4.604, 4.032, 3.707, 3.499, 3.355, 3.250, 3.169, 3.106, 3.055, 3.012, 2.977, 2.947,
           2.921, 2.898, 2.878, 2.861, 2.845, 2.831, 2.819, 2.807, 2.797, 2.787, 2.779, 2.771, 2.763, 2.756, 2.750],
}
_Z = {0.90: 1.645, 0.95: 1.960, 0.99: 2.576}


def t_student(gl, conf):
    return _T[conf][gl - 1] if gl <= 30 else _Z[conf]


def aplanar(d, pref=""):
    """{"a": 1, "b": {"c": 2}} -> {"a": 1, "b.c": 2}; descarta lo que no es número."""
    out = {}
    for k, v in d.items():
        k2 = pref + str(k)
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)) and math.isfinite(v):
            out[k2] = float(v)
        elif isinstance(v, dict):
            out.update(aplanar(v, k2 + "."))
    return out


def resumen(valores, conf, precision):
    n = len(valores)
    m = sum(valores) / n
    if n < 2:
        return {"n": n, "media": m, "desv": None, "ic": None, "ic_rel": None, "n_necesarias": None}
    sd = math.sqrt(sum((x - m) ** 2 for x in valores) / (n - 1))
    h = t_student(n - 1, conf) * sd / math.sqrt(n)
    rel = h / abs(m) if m else (0.0 if h == 0 else None)
    nec = None
    if rel is not None and rel > precision:
        nec = math.ceil(n * (rel / precision) ** 2)
    return {"n": n, "media": m, "desv": sd, "ic": h, "ic_rel": rel, "n_necesarias": nec,
            "min": min(valores), "max": max(valores)}


def una(cmd, semilla, reintentos=1, timeout=None):
    for intento in range(reintentos + 1):
        fd, tmp = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(tmp)
        t = time.time()
        p = subprocess.run(cmd.format(semilla=semilla, json=tmp), shell=True, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout)
        try:
            datos = json.load(io.open(tmp, encoding="utf-8"))
            os.remove(tmp)
            return {"semilla": semilla, "kpi": aplanar(datos) if isinstance(datos, dict) else {},
                    "s": round(time.time() - t, 1), "intentos": intento + 1}
        except (OSError, ValueError):
            err = (p.stderr or p.stdout or "")[-600:]
    return {"semilla": semilla, "error": "sin JSON (código %s): %s" % (p.returncode, err.strip())}


def correr(cmd, semillas, paralelo, etiqueta, timeout):
    res = {}

    def tarea(sem):
        r = una(cmd, sem, timeout=timeout)
        estado = "error" if "error" in r else "%.0f s" % r["s"]
        print("  %s semilla %d: %s" % (etiqueta, sem, estado), flush=True)
        return sem, r
    with ThreadPoolExecutor(max_workers=max(1, paralelo)) as ex:
        for sem, r in ex.map(tarea, semillas):
            res[sem] = r
    return [res[s] for s in semillas]


def fmt(v, nd=3):
    if v is None:
        return "-"
    if abs(v) >= 1000:
        return "%.0f" % v
    return ("%." + str(nd) + "g") % v


def tabla(filas, cabecera):
    anchos = [max(len(str(x)) for x in col) for col in zip(cabecera, *filas)]
    lin = lambda f: "  ".join(str(x).ljust(a) if i == 0 else str(x).rjust(a) for i, (x, a) in enumerate(zip(f, anchos)))
    print(lin(cabecera))
    print("  ".join("-" * a for a in anchos))
    for f in filas:
        print(lin(f))


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cmd", required=True, help="plantilla con {semilla} y {json}")
    ap.add_argument("--comparar", help="plantilla del escenario B (mismas semillas)")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--semilla0", type=int, default=1)
    ap.add_argument("--paralelo", type=int, default=1)
    ap.add_argument("--kpi", action="append", default=[], help="KPI a mostrar (clave aplanada, p. ej. utilizacion_%%.picking); por defecto todos")
    ap.add_argument("--confianza", type=float, default=0.95, choices=[0.90, 0.95, 0.99])
    ap.add_argument("--precision", type=float, default=0.05)
    ap.add_argument("--timeout", type=float, help="segundos máximos por réplica")
    ap.add_argument("--salida")
    ap.add_argument("--csv")
    a = ap.parse_args(argv)
    for plantilla in [a.cmd] + ([a.comparar] if a.comparar else []):
        if "{semilla}" not in plantilla or "{json}" not in plantilla:
            ap.error("cada plantilla necesita {semilla} y {json}")
    semillas = [a.semilla0 + i for i in range(a.n)]
    print("Escenario A: %d réplicas (semillas %d-%d)" % (a.n, semillas[0], semillas[-1]))
    A = correr(a.cmd, semillas, a.paralelo, "A", a.timeout)
    B = None
    if a.comparar:
        print("Escenario B: mismas semillas")
        B = correr(a.comparar, semillas, a.paralelo, "B", a.timeout)
    errores = [r for r in A + (B or []) if "error" in r]
    for r in errores:
        print("AVISO réplica excluida (semilla %d): %s" % (r["semilla"], r["error"][:300]))
    okA = [r for r in A if "kpi" in r]
    if len(okA) < 2:
        print("Menos de 2 réplicas válidas: no hay intervalo de confianza")
        return 1
    claves = a.kpi or sorted({k for r in okA for k in r["kpi"]})
    pct = int(round(a.confianza * 100))
    out = {"semillas": semillas, "confianza": a.confianza, "replicas_A": A, "resumen_A": {}}
    filas, faltan = [], []
    for k in claves:
        vals = [r["kpi"][k] for r in okA if k in r["kpi"]]
        if len(vals) < 2:
            continue
        s = resumen(vals, a.confianza, a.precision)
        out["resumen_A"][k] = s
        filas.append([k, fmt(s["media"]), fmt(s["desv"]), "±" + fmt(s["ic"]),
                      "-" if s["ic_rel"] is None else "%.1f%%" % (100 * s["ic_rel"]),
                      "%s-%s" % (fmt(s["min"]), fmt(s["max"])), s["n"]])
        if s["n_necesarias"]:
            faltan.append((k, s["n_necesarias"]))
    print("\nEscenario A (IC %d%%)" % pct)
    tabla(filas, ["KPI", "media", "desv", "IC", "IC rel", "rango", "n"])
    if faltan:
        print("\nPara un IC de ±%.0f%% harían falta más réplicas en: %s"
              % (100 * a.precision, ", ".join("%s (%d)" % f for f in faltan[:12])))
    if B:
        out["replicas_B"] = B
        out["diferencia_B_menos_A"] = {}
        parejas = [(ra, rb) for ra, rb in zip(A, B) if "kpi" in ra and "kpi" in rb]
        filas = []
        for k in claves:
            d = [rb["kpi"][k] - ra["kpi"][k] for ra, rb in parejas if k in ra["kpi"] and k in rb["kpi"]]
            if len(d) < 2:
                continue
            s = resumen(d, a.confianza, a.precision)
            mA = sum(ra["kpi"][k] for ra, rb in parejas if k in ra["kpi"]) / len(d)
            sig = s["ic"] is not None and (s["media"] - s["ic"] > 0 or s["media"] + s["ic"] < 0)
            s["significativa"] = sig
            out["diferencia_B_menos_A"][k] = s
            filas.append([k, fmt(mA), fmt(mA + s["media"]), fmt(s["media"]), "±" + fmt(s["ic"]),
                          "SÍ" if sig else "no", s["n"]])
        print("\nB - A, pareada con las mismas semillas (IC %d%%)" % pct)
        tabla(filas, ["KPI", "media A", "media B", "B-A", "IC", "significativa", "n"])
        # KPIs que solo existen en B (p. ej. los de una función nueva): resumen de B
        okB = [r for r in B if "kpi" in r]
        solo_b = [k for k in (a.kpi or sorted({k for r in okB for k in r["kpi"]}))
                  if k not in out["diferencia_B_menos_A"] and sum(1 for r in okB if k in r["kpi"]) >= 2]
        if solo_b:
            out["resumen_B"] = {}
            filas = []
            for k in solo_b:
                s = resumen([r["kpi"][k] for r in okB if k in r["kpi"]], a.confianza, a.precision)
                out["resumen_B"][k] = s
                filas.append([k, fmt(s["media"]), fmt(s["desv"]), "±" + fmt(s["ic"]), s["n"]])
            print("\nSolo en B (IC %d%%)" % pct)
            tabla(filas, ["KPI", "media", "desv", "IC", "n"])
    if a.salida:
        io.open(a.salida, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
    if a.csv:
        with io.open(a.csv, "w", encoding="utf-8-sig", newline="") as f:
            f.write("escenario;semilla;kpi;valor\n")
            for esc, rr in [("A", A), ("B", B or [])]:
                for r in rr:
                    for k, v in r.get("kpi", {}).items():
                        if k in claves:
                            f.write("%s;%d;%s;%s\n" % (esc, r["semilla"], k, repr(v).replace(".", ",")))
    return 0 if not errores else 3


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
