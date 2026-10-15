#!/usr/bin/env python3
"""Prueba de humo del skill: construye una escena mínima con los patrones verificados, la simula en
FlexSim real y comprueba COMPORTAMIENTO, no solo que el código compile.

Escena (generar_escena.py):
  Línea con operarios:  Source_Llegadas -> Queue_Entrada -> Puesto_1..2 (equipo de 2 operarios) -> Sink_Salida
  Stock con FEFO:       Source_Lotes -> Separator_Lote (lote -> n_unidades) -> Rack_Stock
                        Source_Pedidos -> Queue_Pedidos -> Combiner_Estacion (tira del rack, FEFO) -> Sink_Salida

Comprueba:
  1. Sin FlexSim: check_script.py da 0 FAIL sobre el script generado.
  2. Con FlexSim (variante «sana», 8 h): todos los bloques OK y todos los campos Code compilan;
     el Sink recibe lo que llega (salvo el WIP); utilización de operarios en el rango teórico;
     el Separator divide cada lote en n_unidades; el rack entrega en orden FEFO (0 infracciones);
     el vigilante no da alarmas; misma semilla = mismo resultado, otra semilla = distinto.
  3. Variante «rota» (un Processor de capacidad 2 con operarios, el fallo medido): el vigilante
     debe dar SIN PROGRESO. Si no la da, el vigilante o el patrón han cambiado.

Uso:
    py -3.12 prueba_humo.py [--fspy DIR] [--base modelo.fsm] [--solo-estatica] [--guardar-escena DIR]
Cada variante corre en su propio proceso (FlexSim arranca una vez por proceso).
Salida: 0 todo bien, 1 alguna comprobación falla, 2 falta FlexSimPy (solo se hizo la parte estática).
"""
import argparse
import io
import json
import os
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from generar_escena import Escena  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except AttributeError:
    pass

HORAS = 8
LLEGADA_MEDIA = 60.0        # s entre llegadas a la línea
SERVICIO_MEDIO = 90.0       # triangular(60, 120, 90): media 90 s
PUESTOS = 2


def escena(variante="sana"):
    e = Escena("Prueba de humo del skill (%s)" % variante, guardar_en="prueba_humo.fsm")
    HDR = ["Object current = ownerobject(c);", "Object item = param(1);"]
    # --- línea con operarios
    for c, n in [("Source", "Source_Llegadas"), ("Queue", "Queue_Entrada"), ("Sink", "Sink_Salida")]:
        e.crear(c, n, bloque="Linea")
    if variante == "sana":
        puestos = e.puestos("Puesto_", PUESTOS, "Equipo_Operarios", bloque="Linea", logica="Logica: linea")
    else:  # el fallo medido: un solo Processor de capacidad 2 con operarios de proceso
        puestos = ["Puesto_Doble"]
        e.crear("Processor", "Puesto_Doble", bloque="Linea")
        e.conectar("Puesto_Doble", "Equipo_Operarios", "S")
        for p, v in [("MaxContent", 2), ("UseProcessOperators", 1), ("NumProcessOperators", 1)]:
            e.propiedad("Puesto_Doble", p, v, bloque="Logica: linea")
        e.codigo("Puesto_Doble", "OperatorRef", ['return model().find("Equipo_Operarios");'], bloque="Logica: linea")
    ops = e.equipo("Equipo_Operarios", "Operator", "Operario_", PUESTOS, bloque="Recursos")
    e.colocar_centro("Source_Llegadas", 0, 0)
    e.colocar_centro("Queue_Entrada", 5, 0)
    for i, p in enumerate(puestos):
        e.colocar_centro(p, 12, 4 - 8 * i)
        e.conectar("Queue_Entrada", p)
        e.conectar(p, "Sink_Salida")
        e.codigo(p, "ProcessTime", ["return triangular(60, 120, 90, 2);"], bloque="Logica: linea")
    e.colocar_centro("Sink_Salida", 20, 0)
    e.colocar_centro("Equipo_Operarios", 8, 8)
    for i, o in enumerate(ops):
        e.colocar_centro(o, 9 + 2 * i, 2)
    e.conectar("Source_Llegadas", "Queue_Entrada")
    e.codigo("Source_Llegadas", "InterArrivalTime", ["return exponential(0, %g, 1);" % LLEGADA_MEDIA], bloque="Logica: linea")
    if variante != "sana":       # la variante rota solo lleva la línea: sin otra salida que enmascare el bloqueo
        return e
    # --- stock con FEFO
    for c, n in [("Source", "Source_Lotes"), ("Separator", "Separator_Lote"), ("Rack", "Rack_Stock"),
                 ("Source", "Source_Pedidos"), ("Queue", "Queue_Pedidos"), ("Combiner", "Combiner_Estacion")]:
        e.crear(c, n, bloque="Stock")
    for n, x, y in [("Source_Lotes", 0, -20), ("Separator_Lote", 6, -20), ("Rack_Stock", 22, -20),
                    ("Source_Pedidos", 0, -30), ("Queue_Pedidos", 6, -30), ("Combiner_Estacion", 14, -30)]:
        e.colocar_centro(n, x, y)
    for a, b in [("Source_Lotes", "Separator_Lote"), ("Separator_Lote", "Rack_Stock"),
                 ("Source_Pedidos", "Queue_Pedidos"), ("Queue_Pedidos", "Combiner_Estacion"),   # puerto 1: pedido
                 ("Rack_Stock", "Combiner_Estacion"),                                           # puerto 2: stock
                 ("Combiner_Estacion", "Sink_Salida")]:
        e.conectar(a, b)
    L = "Logica: stock"
    e.codigo("Source_Lotes", "InterArrivalTime", ["return exponential(0, 600, 3);"], bloque=L)
    e.codigo("Source_Lotes", "SendToPort", HDR + ['item.labels.assert("n_unidades", 0).value = duniform(3, 8, 4);',
                                                  'current.labels.assert("unidades", 0).value += item.labels["n_unidades"].value;',
                                                  "return 1;"], bloque=L)
    e.trigger("Source_Lotes", "OnReset", ["Object current = ownerobject(c);", 'current.labels.assert("unidades", 0).value = 0;'], bloque=L)
    e.separador_lote("Separator_Lote", "n_unidades", bloque=L)
    e.codigo("Separator_Lote", "ProcessTime", ["return 30;"], bloque=L)
    # Cada unidad recibe su caducidad al entrar en el rack; al salir se cuenta si había otra libre que caducaba antes.
    e.trigger("Rack_Stock", "OnEntry", HDR + ['item.labels.assert("caducidad", 0).value = Model.time + uniform(0, 86400, 5);'], bloque=L)
    e.trigger("Rack_Stock", "OnExit", HDR + [
        'double v = item.labels["caducidad"].value;',
        "for (int i = 1; i <= current.subnodes.length; i++) {",
        "Object o = current.subnodes[i];",
        'if (o != item && o.labels.assert("reservado_por", "").value == "" && o.labels["caducidad"].value < v) {',
        'current.labels.assert("fefo_mal", 0).value += 1; break; }',
        "}",
        'current.labels.assert("salidas", 0).value += 1;'], bloque=L)
    e.trigger("Rack_Stock", "OnReset", ["Object current = ownerobject(c);", 'current.labels.assert("fefo_mal", 0).value = 0;',
                                        'current.labels.assert("salidas", 0).value = 0;'], bloque=L)
    # empieza a la media hora (con algo de stock); exponential(1800, ...) sumaría 1800 s a CADA intervalo
    e.codigo("Source_Pedidos", "InterArrivalTime", ["if (Model.time < 1800) { return 1800; }", "return exponential(0, 400, 6);"], bloque=L)
    e.codigo("Source_Pedidos", "SendToPort", HDR + ['item.labels.assert("n_pedido", 0).value = duniform(1, 3, 7);', "return 1;"], bloque=L)
    e.estacion_fefo("Combiner_Estacion", ["n_pedido"], bloque=L)
    e.codigo("Combiner_Estacion", "ProcessTime", ["return 20;"], bloque=L)
    return e


Q_KPI = r'''
Object src = model().find("Source_Llegadas"); Object sk = model().find("Sink_Salida");
Object lot = model().find("Source_Lotes"); Object sep = model().find("Separator_Lote"); Object rk = model().find("Rack_Stock");
Object cb = model().find("Combiner_Estacion"); Object ped = model().find("Source_Pedidos");
double T = Model.time; double idle = 0; int n = 0;
for (int i = 1; i <= model().subnodes.length; i++) {
  treenode x = model().subnodes[i];
  if (x.is(Object)) { Object o = x.as(Object); if (o.getProperty("Class") == "Operator") { idle = idle + o.stats.state().getTotalTimeAt(STATE_IDLE); n++; } }
}
return [src.stats.output.value, sk.stats.input.value, 1 - idle / n / T, lot.labels["unidades"].value, sep.stats.output.value,
        rk.labels["fefo_mal"].value, rk.labels["salidas"].value, cb.stats.output.value, ped.stats.output.value,
        model().find("Queue_Entrada").subnodes.length];'''


def correr_variante(variante, fspy, base, programa, semillas):
    """Se ejecuta en un subproceso: construye, compila los Code, simula con cada semilla."""
    from flexsim_check import Sesion, bloques_de, codigos_de
    d = tempfile.mkdtemp(prefix="humo_")
    escena(variante).escribir(d, "humo")
    texto = io.open(os.path.join(d, "humo.flexscript"), encoding="utf-8").read()
    s = Sesion(fspy, programa, base)
    res = {"variante": variante, "bloques_mal": [], "no_compilan": [], "corridas": []}
    for num, titulo, cuerpo in bloques_de(texto):
        r = s.bloque(cuerpo)
        if r != "OK":
            res["bloques_mal"].append("B%d %s: %r" % (num, titulo, r))
    for desc, cod in codigos_de(texto):
        if s.x("if (0) {\n" + cod + '\n}\nreturn "COMPILA";') != "COMPILA":
            res["no_compilan"].append(desc)
    for sem in semillas:
        vig = s.correr(HORAS * 3600, semilla=sem, vigilar=1800, parada=3 * 3600 if variante == "rota" else None)
        k = s.x(Q_KPI) if variante == "sana" else None
        res["corridas"].append({"semilla": sem, "kpi": k, "alarmas": vig["alarmas"], "t_final": vig["t_final"]})
    return res


def comprobar_sana(r):
    ok = []
    ok.append(("bloques OK", not r["bloques_mal"], r["bloques_mal"]))
    ok.append(("campos Code compilan", not r["no_compilan"], r["no_compilan"]))
    c1, c1b, c2 = r["corridas"]
    k = c1["kpi"]
    llegadas, sink, util, unid, sep_out, fefo_mal, rk_sal, cb_out, n_ped, cola = k
    esperadas = HORAS * 3600 / LLEGADA_MEDIA
    ok.append(("llegadas ~ %.0f (±4σ)" % esperadas, abs(llegadas - esperadas) <= 4 * esperadas ** 0.5, llegadas))
    pedidos_servidos = cb_out - rk_sal      # la salida del Combiner cuenta también los componentes empaquetados
    ok.append(("Sink recibe línea + pedidos (salvo WIP)", llegadas + pedidos_servidos - cola - PUESTOS <= sink <= llegadas + pedidos_servidos,
               (sink, llegadas, pedidos_servidos, cola)))
    rho = esperadas * SERVICIO_MEDIO / (HORAS * 3600) / PUESTOS
    ok.append(("utilización operarios en [ρ, ρ+0,15] (ρ=%.2f)" % rho, rho - 0.05 <= util <= rho + 0.15, round(util, 3)))
    ok.append(("Separator: salidas = suma de n_unidades (±1 lote en proceso)", 0 <= unid - sep_out <= 8, (unid, sep_out)))
    ok.append(("FEFO: 0 infracciones en %d salidas del rack" % rk_sal, fefo_mal == 0 and rk_sal > 0, fefo_mal))
    ok.append(("estación sirve los pedidos (salvo los últimos)", pedidos_servidos >= 0.8 * n_ped - 2, (pedidos_servidos, n_ped)))
    ok.append(("vigilante sin alarmas", not c1["alarmas"], [a["detalle"] for a in c1["alarmas"]]))
    ok.append(("misma semilla = mismo resultado", c1["kpi"] == c1b["kpi"], (c1["kpi"], c1b["kpi"])))
    ok.append(("otra semilla = resultado distinto", c1["kpi"] != c2["kpi"], (c1["kpi"][:2], c2["kpi"][:2])))
    return ok


def comprobar_rota(r):
    c = r["corridas"][0]
    tipos = [a["tipo"] for a in c["alarmas"]]
    return [("variante rota: el vigilante detecta SIN PROGRESO", "SIN PROGRESO" in tipos,
             [a["detalle"] + " | " + "; ".join(a["sospechosos"][:4]) for a in c["alarmas"]] or c["kpi"])]


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fspy", default=os.environ.get("FLEXSIMPY_DIR", ""))
    ap.add_argument("--base", default=os.environ.get("FLEXSIM_BASE_MODEL", ""))
    ap.add_argument("--programa", default=os.environ.get("FLEXSIM_PROGRAM", r"C:\Program Files\Autodesk\FlexSim 2027\program"))
    ap.add_argument("--solo-estatica", action="store_true")
    ap.add_argument("--guardar-escena", help="carpeta donde dejar el script generado")
    ap.add_argument("--_variante", help=argparse.SUPPRESS)
    ap.add_argument("--_json", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    for campo in ("base", "_json", "guardar_escena"):
        if getattr(a, campo):
            setattr(a, campo, os.path.abspath(getattr(a, campo)))
    if a._variante:                                   # subproceso
        sem = [1, 1, 2] if a._variante == "sana" else [1]
        res = correr_variante(a._variante, a.fspy, a.base, a.programa, sem)
        io.open(a._json, "w", encoding="utf-8").write(json.dumps(res, default=str))
        return 0
    fallos = 0
    # 1. estática
    d = a.guardar_escena or tempfile.mkdtemp(prefix="humo_")
    os.makedirs(d, exist_ok=True)
    escena("sana").escribir(d, "humo")
    p = subprocess.run([sys.executable, os.path.join(AQUI, "check_script.py"), os.path.join(d, "humo.flexscript")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    nfail = sum(1 for ln in p.stdout.splitlines() if ln.lstrip().startswith("[FAIL]"))
    print("%-4s check_script.py: %d FAIL" % ("OK" if nfail == 0 else "MAL", nfail))
    if nfail:
        print(p.stdout[-2000:])
        fallos += 1
    if a.solo_estatica:
        return 1 if fallos else 0
    if not a.fspy or not os.path.exists(os.path.join(a.fspy, "FlexSimPy.pyd")):
        print("Sin FlexSimPy (--fspy o FLEXSIMPY_DIR): solo se hizo la parte estática")
        return 2
    if not a.base:
        print("Falta --base (modelo .fsm real: sin FlowItemBin los Source no crean items)")
        return 2
    # 2 y 3. FlexSim, una variante por proceso
    for variante, comprobar in [("sana", comprobar_sana), ("rota", comprobar_rota)]:
        fd, tmp = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        cmd = [sys.executable, os.path.abspath(__file__), "--_variante", variante, "--_json", tmp,
               "--fspy", a.fspy, "--base", a.base, "--programa", a.programa]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900)
        try:
            r = json.load(io.open(tmp, encoding="utf-8"))
        except (OSError, ValueError):
            print("MAL  variante %s: el subproceso no escribió resultados" % variante)
            fallos += 1
            continue
        for nombre, bien, dato in comprobar(r):
            print("%-4s %s  [%s]" % ("OK" if bien else "MAL", nombre, dato))
            fallos += 0 if bien else 1
    print("Prueba de humo: %s" % ("TODO OK" if not fallos else "%d comprobaciones fallan" % fallos))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
