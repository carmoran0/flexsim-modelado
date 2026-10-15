#!/usr/bin/env python3
"""Ejecuta un script de construcción en FlexSim REAL (sin interfaz) mediante FlexSimPy y comprueba
el resultado: bloques, clases, propiedades, conexiones, A* y una simulación corta.

Requisitos (ver references/flexsimpy.md):
- FlexSimPy compilado (FlexSimPy.pyd) para la versión de Python con la que se ejecuta este
  script (3.9-3.12). Ruta con --fspy o con la variable FLEXSIMPY_DIR.
- FlexSim instalado (por defecto C:/Program Files/Autodesk/FlexSim 2027/program).

Uso:
    py -3.12 flexsim_check.py escena.flexscript [--saltar "layout B"] [--correr 3600]
                              [--semilla 1] [--vigilar 3600 [--parada 14400]]
                              [--fspy DIR] [--programa DIR] [--json salida.json] [--guardar modelo.fsx]

--semilla: siembra los streams 0-99 tras el reset (randinit): réplicas reproducibles.
--vigilar: simula a trozos y avisa de interbloqueos (SIN PROGRESO), atascos y colas que crecen.
--recorridos H [--desde T]: muestrea cada 1 s la posición de cada recurso móvil durante H horas y
           cuenta cruces de muros A* y pasos por encima de estanterías y puestos.
Como módulo: Sesion(...).correr(T, semilla=n, vigilar=3600) y vigilar_simulacion().

Cómo funciona: FlexSimPy solo sabe evaluar un NODO del árbol por su ruta (Controller.evaluate),
no texto. El script abre un modelo mínimo en XML (.fsx) que lleva en Tools dos nodos FlexScript:
Tools/Exec (executestring(param(1))) y Tools/RunFS (executefsfile(param(1), 1)). Cada bloque se
ejecuta con un marcador final 'return "OK";':
    "OK"  -> el bloque terminó;  None -> excepción en ejecución;  0.0 -> no compila.
FlexScript no tiene try/catch: si un bloque falla, se busca la primera sentencia que falla
ejecutando prefijos del bloque (--localizar).
"""
import argparse
import io
import json
import os
import random
import re
import sys
import tempfile
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except AttributeError:
    pass

BOOT = """<?xml version="1.0" encoding="UTF-8"?>
<flexsim-tree version="4" treetype="model">
<node f="10000043" dt="4"><name>model</name><data>
 <node f="40"><name></name></node>
</data>
 <node f="40"><name></name></node>
 <node f="43"><name>Tools</name>
  <node f="40"><name></name></node>
  <node f="442" dt="2"><name>RunFS</name><data>return executefsfile(param(1), 1);</data></node>
  <node f="442" dt="2"><name>Exec</name><data>return executestring(param(1));</data></node>
 </node>
</node>
</flexsim-tree>
"""

ESTADO = {"OK": "OK", None: "EXCEPCION", 0.0: "NO COMPILA"}

# Deja el modelo base vacío: destruye todos los objetos salvo el suelo; conserva Tools.
VACIAR_MODELO = r'''
for (int i = model().subnodes.length; i >= 1; i--) {
  treenode n = model().subnodes[i];
  if (n.is(Object) && n.name != "FlexsimModelFloor") n.destroy();
}
return 1;'''

Q_UNIDADES = r'''
treenode u = model().find("Tools/ModelUnits");
string s = "";
Array a;
if (objectexists(u)) for (int i = 1; i <= u.subnodes.length; i++) a.push(u.subnodes[i].name + "=" + string.fromNum(u.subnodes[i].value));
return a;'''


class Sesion:
    def __init__(self, fspy_dir, programa, base=None):
        sys.path.insert(0, fspy_dir)
        import FlexSimPy  # noqa: E402
        self.fs = FlexSimPy
        t = time.time()
        self.c = FlexSimPy.launch(showGUI=False, programDir=programa)
        self.t_launch = time.time() - t
        fd, self.boot = tempfile.mkstemp(suffix=".fsx")
        os.close(fd)
        io.open(self.boot, "w", encoding="utf-8").write(BOOT)
        self.c.open(self.boot.replace("\\", "/"))
        self.ruta_exec = "Tools/Exec"
        if self.x("return 1;") != 1.0:
            raise RuntimeError("No se pudo ejecutar FlexScript a traves del modelo base")
        # El nodo Exec se copia FUERA del modelo (MAIN:/project) para que sobreviva a abrir otro
        # modelo: Controller.evaluate admite rutas relativas al modelo como "../ClaudeExec".
        self.x('treenode e = createcopy(model().find("Tools/Exec"), model().up, 1); e.name = "ClaudeExec"; return 1;')
        self.ruta_exec = "../ClaudeExec"
        if base:
            # Un modelo real trae Tools completos (FlowItemBin...): sin eso los Source no crean items.
            self.c.open(base.replace("\\", "/"))
            self.x(VACIAR_MODELO)
        if self.x("return 1;") != 1.0:
            raise RuntimeError("No se pudo ejecutar FlexScript tras abrir el modelo base")

    def x(self, codigo):
        return self.c.evaluate(self.ruta_exec, codigo)

    def bloque(self, texto):
        return self.x(texto + '\nreturn "OK";')

    def sembrar(self, semilla):
        """Siembra los streams 0-99 con valores derivados de `semilla` (randinit). Llamar DESPUÉS de
        reset (con «Repeat Random Streams» el reset los devuelve a sus valores por defecto) y antes
        de correr. Misma semilla = misma ejecución; semillas distintas = réplicas independientes.
        Lo que se muestrea DURANTE el reset (p. ej. la primera llegada de un Source) usa aún la
        semilla por defecto."""
        rnd = random.Random(int(semilla))
        semillas = [rnd.randint(1, 2 ** 31 - 2) for _ in range(100)]
        r = self.x("Array s = [%s]; for (int i = 0; i <= 99; i++) randinit(i, s[i + 1]); return 1;"
                   % ", ".join(map(str, semillas)))
        if r != 1.0:
            raise RuntimeError("randinit falló (%r)" % (r,))

    def correr(self, hasta, semilla=None, vigilar=0, **kw):
        """reset (+ sembrar) + simular hasta `hasta` s. Con vigilar > 0 simula a trozos de `vigilar`
        segundos y busca interbloqueos y colas que crecen (ver vigilar()). Devuelve el informe del
        vigilante o None."""
        self.c.reset()
        if semilla is not None:
            self.sembrar(semilla)
        if vigilar and vigilar > 0:
            return vigilar_simulacion(self, hasta, vigilar, **kw)
        self.c.runToTime(hasta)
        return None

    def localizar(self, texto):
        """Devuelve la primera línea cuyo prefijo deja de terminar en OK (aprox.)."""
        lineas = texto.split("\n")
        ok_hasta = 0
        for i in range(1, len(lineas) + 1):
            pref = "\n".join(lineas[:i])
            if pref.count("{") != pref.count("}") or pref.count("(") != pref.count(")"):
                continue
            r = self.x(pref + '\nreturn "OK";')
            if r != "OK":
                return i, lineas[i - 1].strip(), ESTADO.get(r, repr(r))
            ok_hasta = i
        return None


def bloques_de(texto):
    out = []
    for p in re.split(r"(?=/\* BLOQUE \d+)", texto):
        m = re.match(r"/\* BLOQUE (\d+) - (.*?)\s*\*/", p, re.S)
        if m:
            out.append((int(m.group(1)), m.group(2).strip().split("\n")[0], p))
    return out


def codigos_de(texto):
    """Cadenas FlexScript que el script guarda como código: setProperty("X", "...") con código y
    nodos de trigger/variable (<var>.value = "..."). Devuelve [(descripción, código)]."""
    out = []
    lit = r'"((?:[^"\\]|\\.)*)"'
    for m in re.finditer(r'(\w+)\.as\(Object\)\.setProperty\("(\w+)",\s*' + lit + r'\)', texto):
        cod = m.group(3).replace('\\"', '"').replace("\\\\", "\\")
        if "return" in cod or "ownerobject" in cod or "param(" in cod:
            out.append(("%s.%s" % (m.group(1), m.group(2)), cod))
    for m in re.finditer(r'(\w+)\s*=\s*(\w+)\.as\(Object\)\.find\(">variables"\)\.subnodes\.assert\("(\w+)"\);\s*\n\s*\1\.value = '
                         + lit + ';', texto):
        cod = m.group(4).replace('\\"', '"').replace("\\\\", "\\")
        out.append(("%s.variables/%s" % (m.group(2), m.group(3)), cod))
    return out


def propiedades_fijadas(texto):
    """(objeto, propiedad) de cada setProperty("P", ...) sobre una variable ligada a find("Obj")."""
    var_obj = dict(re.findall(r"treenode\s+(\w+)\s*=\s*model\(\)\.find\(\"([^\"]+)\"\)", texto))
    pares = []
    for v, p in re.findall(r"(\w+)\.as\(Object\)\.setProperty\(\"(\w+)\"", texto):
        if v in var_obj and (var_obj[v], p) not in pares:
            pares.append((var_obj[v], p))
    return pares


Q_INVENTARIO = r'''
Map m;
treenode r = model();
for (int i = 1; i <= r.subnodes.length; i++) {
  treenode n = r.subnodes[i];
  if (n.is(Object)) { string k = n.as(Object).getProperty("Class"); m[k] = (m[k] ? m[k] : 0) + 1; }
}
return m;'''

Q_A_ESTRELLA = r'''
treenode nav = model().find("AStarNavigator");
if (!objectexists(nav)) return "sin navegador";
int divs = 0; int otros = 0;
for (int i = 1; i <= nav.subnodes.length; i++) {
  treenode n = nav.subnodes[i];
  if (n.is(Object)) { if (n.as(Object).getProperty("Class") == "AStar::Divider") divs++; else otros++; }
}
treenode tm = nav.find(">variables/travelmembers");
return "dividers=" + string.fromNum(divs) + " otros_hijos=" + string.fromNum(otros) +
       " viajeros=" + string.fromNum(objectexists(tm) ? tm.subnodes.length : -1);'''

Q_ESTADISTICAS = r'''
Array out;
Array clases = ["Source", "Queue", "Processor", "Sink", "Rack", "Combiner", "Separator", "MultiProcessor",
                "Conveyor::StraightConveyor", "Conveyor::CurvedConveyor"];
treenode r = model();
for (int i = 1; i <= r.subnodes.length; i++) {
  treenode n = r.subnodes[i];
  if (!n.is(Object)) continue;
  Object o = n.as(Object);
  string k = o.getProperty("Class");
  int vale = 0;
  for (int j = 1; j <= clases.length; j++) if (clases[j] == k) vale = 1;
  if (!vale) continue;
  if (k == "Rack" && o.stats.input.value == 0) continue;
  out.push(o.name + " | in=" + string.fromNum(o.stats.input.value) + " out=" + string.fromNum(o.stats.output.value)
           + " contenido=" + string.fromNum(n.subnodes.length));
}
return out;'''


# ----------------------------------------------------------------- vigilante de interbloqueos
# Foto de cada objeto: nombre;clase;entradas;salidas;contenido;estado (getstatestr).
Q_FOTO = r'''
string r = "";
for (int i = 1; i <= model().subnodes.length; i++) {
  treenode n = model().subnodes[i];
  if (!n.is(Object)) continue;
  Object o = n.as(Object);
  string cl = o.getProperty("Class");
  if (cl == "VisualTool" || cl == "Dispatcher" || cl == "AStar::AStarNavigator" || cl == "Conveyor::ConveyorSystem"
      || o.name == "FlexsimModelFloor") continue;
  r = r + o.name + ";" + cl + ";" + string.fromNum(o.stats.input.value) + ";" + string.fromNum(o.stats.output.value)
        + ";" + string.fromNum(n.subnodes.length) + ";" + getstatestr(o) + "|";
}
return r;'''

MOVILES = ("Operator", "Transporter", "TaskExecuter", "Robot", "ASRSvehicle", "Crane", "Elevator", "BasicTE")


def _foto(s):
    out = {}
    for fila in (s.x(Q_FOTO) or "").split("|"):
        v = fila.split(";")
        if len(v) == 6:
            out[v[0]] = {"clase": v[1], "in": float(v[2]), "out": float(v[3]), "cont": float(v[4]), "estado": v[5]}
    return out


def vigilar_simulacion(s, hasta, paso=3600, parada=None, ciclo=86400, seguir=False, excluir=("Rack",)):
    """Simula hasta `hasta` a trozos de `paso` s y vigila tres fallos que la simulación no avisa:

    - SIN PROGRESO (interbloqueo global): durante `parada` s (por defecto 4 trozos) ningún objeto
      saca nada y hay items dentro. Sospechosos: objetos con contenido sin salidas y recursos
      móviles en el mismo estado no ocioso todo el tiempo (p. ej. operarios en «utilize» sin
      soltar). Para la simulación salvo `seguir`.
    - ATASCO (local): un objeto sigue recibiendo pero no saca nada en `parada` s. El resto del
      modelo puede seguir moviéndose. Un Combiner esperando stock o una cartera que espera a
      propósito también salen aquí: revisar, no siempre es un error.
    - CRECE: un objeto acaba cada `ciclo` (día) con más contenido que el anterior, 3 ciclos
      seguidos: la carga supera la capacidad. Con menos de 3 ciclos, tendencia de las 6 últimas fotos.
    No se vigilan Source, Sink, recursos móviles ni las clases de `excluir` (stock a propósito).
    Devuelve {"alarmas": [...], "t_final": t, "fotos": n, "paso": paso}."""
    parada = parada or 4 * paso
    fotos = []                      # (t, foto)
    alarmas = []
    t = 0.0
    avisados = set()
    no_vig = ("Source", "Sink") + MOVILES + tuple(excluir)
    while t < hasta - 1e-6:
        t = min(hasta, t + paso)
        s.c.runToTime(t)
        f = _foto(s)
        fotos.append((s.c.time(), f))
        atras = [(tt, ff) for tt, ff in fotos if tt <= fotos[-1][0] - parada + 1e-6]
        if atras:
            t0, f0 = atras[-1]
            ventana = [ff for tt, ff in fotos if tt >= t0 - 1e-6]
            d_out = {n: o["out"] - f0.get(n, {"out": 0})["out"] for n, o in f.items()}
            d_in = {n: o["in"] - f0.get(n, {"in": 0})["in"] for n, o in f.items()}
            avance = sum(d_out[n] for n, o in f.items() if o["clase"] != "Source") +                 sum(d_in[n] for n, o in f.items() if o["clase"] == "Sink")
            wip = sum(o["cont"] for o in f.values() if o["clase"] not in no_vig)
            # --- sin progreso
            if avance == 0 and wip > 0:
                sosp = []
                for n, o in f.items():
                    if o["clase"] in MOVILES:
                        estados = {ff.get(n, {}).get("estado") for ff in ventana}
                        if len(estados) == 1 and o["estado"] not in ("idle", ""):
                            sosp.append("%s (%s): «%s» todo el tiempo, carga %d" % (n, o["clase"], o["estado"], o["cont"]))
                    elif o["clase"] not in no_vig and o["cont"] > 0:
                        sosp.append("%s (%s): %d dentro, estado «%s»" % (n, o["clase"], o["cont"], o["estado"]))
                alarmas.append({"tipo": "SIN PROGRESO", "t": fotos[-1][0],
                                "detalle": "%.1f h sin ninguna salida con %d items dentro" % (parada / 3600.0, wip),
                                "sospechosos": sosp})
                if not seguir:
                    break
            # --- atascos locales
            for n, o in f.items():
                if ("A", n) in avisados or o["clase"] in no_vig:
                    continue
                if d_in[n] > 0 and d_out[n] == 0 and o["cont"] > 0:
                    avisados.add(("A", n))
                    alarmas.append({"tipo": "ATASCO", "t": fotos[-1][0],
                                    "detalle": "%s (%s): %d entradas y 0 salidas en %.1f h, %d dentro, estado «%s»"
                                               % (n, o["clase"], d_in[n], parada / 3600.0, o["cont"], o["estado"]),
                                    "sospechosos": []})
        # --- colas que crecen
        cierres = [ff for tt, ff in fotos if ciclo and abs(tt / ciclo - round(tt / ciclo)) < 1e-6 and tt > 0]
        for n, o in f.items():
            if ("C", n) in avisados or o["clase"] in no_vig:
                continue
            if len(cierres) >= 4 and cierres[-1] is f:
                serie = [c.get(n, {"cont": 0})["cont"] for c in cierres[-4:]]
                crece = all(b > a for a, b in zip(serie, serie[1:])) and serie[-1] - serie[0] >= max(10, 0.2 * serie[0])
                base = "fin de cada ciclo"
            elif len(cierres) < 4 and len(fotos) >= 6:
                serie = [ff.get(n, {"cont": 0})["cont"] for _, ff in fotos[-6:]]
                pasos = [b - a for a, b in zip(serie, serie[1:])]
                crece = (all(d >= 0 for d in pasos) and sum(d > 0 for d in pasos) >= 4
                         and serie[-1] >= max(serie[0] + 20, 2 * serie[0]))
                base = "últimas 6 fotos"
            else:
                continue
            if crece:
                avisados.add(("C", n))
                alarmas.append({"tipo": "CRECE", "t": fotos[-1][0],
                                "detalle": "%s (%s): contenido %s (%s): la carga supera la capacidad"
                                           % (n, o["clase"], " -> ".join("%d" % v for v in serie), base),
                                "sospechosos": []})
    return {"alarmas": alarmas, "t_final": fotos[-1][0] if fotos else 0, "fotos": len(fotos), "paso": paso}


# ----------------------------------------------------------------- recorridos: ¿atraviesan algo?
# Muros = puntos de cada Divider del navegador; obstáculos = eje largo de cada Rack y eje de la
# huella de Processor/Combiner/Separator/Queue. Posición de cada recurso móvil con
# updatelocations: sin él, getLocation devuelve la posición del ÚLTIMO evento y un recurso que
# viaja parece saltar en línea recta (medido: 54 m en 3 s), lo que daría cruces falsos.
Q_MUROS = r'''
string r = "";
Object nav = model().find("AStarNavigator");
if (objectexists(nav)) for (int i = 1; i <= nav.subnodes.length; i++) {
  treenode n = nav.subnodes[i];
  if (!n.is(Object)) continue;
  Object d = n.as(Object);
  if (d.getProperty("Class") != "AStar::Divider") continue;
  Array p = d.getProperty("PathPoints");
  for (int k = 1; k < p.length; k++) r = r + "M;" + d.name + ";" + string.fromNum(p[k][1] + nav.location.x) + ";" + string.fromNum(p[k][2] + nav.location.y)
       + ";" + string.fromNum(p[k + 1][1] + nav.location.x) + ";" + string.fromNum(p[k + 1][2] + nav.location.y) + "|";
}
for (int i = 1; i <= model().subnodes.length; i++) {
  treenode n = model().subnodes[i];
  if (!n.is(Object)) continue;
  Object o = n.as(Object);
  string cl = o.getProperty("Class");
  if (cl == "Rack" || cl == "Processor" || cl == "Combiner" || cl == "Separator" || cl == "Queue") {
    Vec3 a = o.getLocation(0, 0, 0); Vec3 b = o.getLocation(1, 1, 0);
    r = r + "O;" + o.name + ";" + string.fromNum(Math.min(a.x, b.x)) + ";" + string.fromNum(Math.min(a.y, b.y)) + ";"
          + string.fromNum(Math.max(a.x, b.x)) + ";" + string.fromNum(Math.max(a.y, b.y)) + "|";
  }
}
return r;'''

Q_POSICIONES = r'''
string r = "";
for (int i = 1; i <= model().subnodes.length; i++) {
  treenode n = model().subnodes[i];
  if (!n.is(TaskExecuter)) continue;
  Object o = n.as(Object);
  if (o.getProperty("Class") == "Robot") continue;
  updatelocations(o);
  Vec3 c = o.getLocation(0.5, 0.5, 0);
  r = r + o.name + ";" + string.fromNum(c.x) + ";" + string.fromNum(c.y) + "|";
}
return r;'''


def _cruza(p, q, seg, margen=0.05):
    x1, y1, x2, y2 = seg
    if abs(y2 - y1) < 1e-9:                       # tramo horizontal
        if (p[1] - y1) * (q[1] - y1) >= 0:
            return False
        x = p[0] + (y1 - p[1]) / (q[1] - p[1]) * (q[0] - p[0])
        return min(x1, x2) + margen < x < max(x1, x2) - margen
    if abs(x2 - x1) < 1e-9:                       # tramo vertical
        if (p[0] - x1) * (q[0] - x1) >= 0:
            return False
        y = p[1] + (x1 - p[0]) / (q[0] - p[0]) * (q[1] - p[1])
        return min(y1, y2) + margen < y < max(y1, y2) - margen
    d = lambda a, b, c: (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])   # tramo oblicuo
    a, b = (x1, y1), (x2, y2)
    return d(a, b, p) * d(a, b, q) < 0 and d(p, q, a) * d(p, q, b) < 0


def revisar_recorridos(s, hasta, paso=1.0):
    """Simula hasta `hasta` s muestreando cada `paso` s la posición de cada recurso móvil, y
    cuenta cuántas veces cruza un muro A* (Divider) o pasa por encima de un objeto fijo
    (estantería, puesto, cola). Hazlo tras un reset y con la simulación en sus horas activas.
    Devuelve {"muros": {...}, "objetos": {...}, "ejemplos": [...]} con cruces por (recurso, obstáculo)."""
    segs = []
    for f in (s.x(Q_MUROS) or "").split("|"):
        v = f.split(";")
        if len(v) != 6:
            continue
        x1, y1, x2, y2 = map(float, v[2:])
        if v[0] == "M":
            segs.append(("muros", v[1], (x1, y1, x2, y2)))
        elif x2 - x1 >= y2 - y1:                  # eje largo de la huella
            segs.append(("objetos", v[1], (x1 + 0.2, (y1 + y2) / 2, x2 - 0.2, (y1 + y2) / 2)))
        else:
            segs.append(("objetos", v[1], ((x1 + x2) / 2, y1 + 0.2, (x1 + x2) / 2, y2 - 0.2)))

    def pos():
        out = {}
        for f in (s.x(Q_POSICIONES) or "").split("|"):
            v = f.split(";")
            if len(v) == 3:
                out[v[0]] = (float(v[1]), float(v[2]))
        return out
    inf = {"muros": {}, "objetos": {}, "ejemplos": [], "tramos": len(segs)}
    t = s.c.time()
    prev = pos()
    while t < hasta - 1e-6:
        t = min(hasta, t + paso)
        s.c.runToTime(t)
        cur = pos()
        for n, q in cur.items():
            p = prev.get(n)
            if not p or p == q:
                continue
            for tipo, obst, seg in segs:
                if _cruza(p, q, seg):
                    k = "%s -> %s" % (n.rstrip("0123456789_"), obst)
                    inf[tipo][k] = inf[tipo].get(k, 0) + 1
                    if len(inf["ejemplos"]) < 10:
                        inf["ejemplos"].append("t=%.0f %s (%.1f, %.1f) -> (%.1f, %.1f) cruza %s" % (t, n, p[0], p[1], q[0], q[1], obst))
        prev = cur
    return inf


def imprimir_vigilancia(inf):
    if not inf:
        return
    if not inf["alarmas"]:
        print("Vigilante: sin interbloqueos ni colas crecientes (%d fotos cada %.0f s, hasta %.0f s)"
              % (inf["fotos"], inf["paso"], inf["t_final"]))
        return
    for a in inf["alarmas"]:
        print("Vigilante %s en t=%.0f s (%.1f h): %s" % (a["tipo"], a["t"], a["t"] / 3600.0, a["detalle"]))
        for x in a["sospechosos"][:15]:
            print("    sospechoso:", x)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script")
    ap.add_argument("--saltar", action="append", default=[], help="regex sobre el título de bloques a saltar")
    ap.add_argument("--correr", type=float, default=0, help="segundos de simulación tras construir (0 = no)")
    ap.add_argument("--fspy", default=os.environ.get("FLEXSIMPY_DIR", ""))
    ap.add_argument("--programa", default=r"C:\Program Files\Autodesk\FlexSim 2027\program")
    ap.add_argument("--base", default=os.environ.get("FLEXSIM_BASE_MODEL", ""),
                    help="modelo .fsm real que se vacía y se usa de base (necesario para simular)")
    ap.add_argument("--json")
    ap.add_argument("--localizar", action="store_true", help="si un bloque falla, buscar la línea")
    ap.add_argument("--consulta", action="append", default=[], help="FlexScript extra a evaluar al final")
    ap.add_argument("--guardar", help="ruta .fsm donde guardar el modelo construido (savebyname, sin dialogo)")
    ap.add_argument("--posiciones", help="JSON <prefijo>_posiciones.json de generar_escena.py para comparar")
    ap.add_argument("--tolerancia", type=float, default=0.3, help="metros de desviación admitida")
    ap.add_argument("--semilla", type=int, help="siembra los streams 0-99 tras el reset (réplicas reproducibles)")
    ap.add_argument("--vigilar", type=float, default=0,
                    help="con --correr: simula a trozos de N s y avisa de interbloqueos y colas que crecen")
    ap.add_argument("--parada", type=float, help="segundos sin salidas que cuentan como interbloqueo (4 trozos)")
    ap.add_argument("--recorridos", type=float, default=0,
                    help="horas de simulación muestreando posiciones cada 1 s: ¿cruzan muros A* u objetos fijos?")
    ap.add_argument("--desde", type=float, default=0, help="con --recorridos: segundos a saltar antes (horas activas)")
    a = ap.parse_args(argv)
    # FlexSim cambia el directorio de trabajo al arrancar: todas las rutas, absolutas desde ya
    for campo in ("script", "json", "posiciones", "base", "guardar"):
        if getattr(a, campo):
            setattr(a, campo, os.path.abspath(getattr(a, campo)))
    if not a.fspy:
        print("Falta --fspy (carpeta con FlexSimPy.pyd) o FLEXSIMPY_DIR")
        return 2
    texto = io.open(a.script, encoding="utf-8").read()
    s = Sesion(a.fspy, a.programa, a.base or None)
    if not a.base and a.correr > 0:
        print("AVISO: sin --base el modelo no tiene FlowItemBin y los Source no crearán items")
    rep = {"script": a.script, "launch_s": round(s.t_launch, 1), "bloques": [], "fallos": 0}
    print("FlexSim arrancado en %.1f s" % s.t_launch)
    rep["unidades"] = s.x(Q_UNIDADES)
    print("Unidades del modelo base:", rep["unidades"])
    for num, titulo, cuerpo in bloques_de(texto):
        if any(re.search(p, titulo, re.I) for p in a.saltar):
            print("B%-3d SALTADO     %s" % (num, titulo[:80]))
            rep["bloques"].append({"n": num, "titulo": titulo, "estado": "SALTADO"})
            continue
        t = time.time()
        r = s.bloque(cuerpo)
        est = ESTADO.get(r, repr(r))
        info = {"n": num, "titulo": titulo, "estado": est, "s": round(time.time() - t, 2)}
        print("B%-3d %-11s %s" % (num, est, titulo[:80]))
        if est != "OK":
            rep["fallos"] += 1
            if a.localizar:
                info["linea"] = s.localizar(cuerpo)
                print("     primera linea que falla:", info["linea"])
        rep["bloques"].append(info)
    # Cada campo Code / trigger por separado: un código que no compila NO da error al fijarlo ni al
    # simular (el campo simplemente no hace nada). Se compila sin ejecutarlo: if (0) { ... }
    nombres_obj = dict(re.findall(r'treenode\s+(\w+)\s*=\s*model\(\)\.find\("([^"]+)"\)', texto))
    no_compilan = []
    vistos = set()
    for desc, cod in codigos_de(texto):
        if cod in vistos:
            continue
        vistos.add(cod)
        r = s.x("if (0) {\n" + cod + '\n}\nreturn "COMPILA";')
        if r != "COMPILA":
            var = desc.split(".")[0]
            no_compilan.append("%s [%s]: %s" % (desc, nombres_obj.get(var, "?"), cod[:90]))
    rep["codigos_que_no_compilan"] = no_compilan
    print("Campos Code y triggers que NO compilan: %s" % (len(no_compilan) if no_compilan else "ninguno"))
    for n in no_compilan:
        print("   ", n)
    rep["inventario"] = s.x(Q_INVENTARIO)
    print("Inventario por clase:", rep["inventario"])
    # propiedades fijadas que no existen (getProperty devuelve nullvar -> None)
    malas = []
    for obj, p in propiedades_fijadas(texto):
        v = s.x('treenode n = model().find("%s"); if (!objectexists(n)) return "NO_OBJ"; '
                'return n.as(Object).getProperty("%s");' % (obj, p))
        if v is None:
            malas.append("%s.%s" % (obj, p))
    rep["propiedades_sin_valor"] = malas
    print("Propiedades fijadas que getProperty no devuelve (nombre inválido o no aplica): %s"
          % (", ".join(malas) if malas else "ninguna"))
    if a.posiciones:
        esp = json.load(io.open(a.posiciones, encoding="utf-8"))
        desv = []
        for n, (cx, cy, sx, sy) in esp["objetos"].items():
            r = s.x('treenode n = model().find("%s"); if (!objectexists(n)) return "NO"; Object o = n.as(Object); '
                    'Vec3 c = o.getLocation(0.5, 0.5, 0); return [c.x, c.y, o.size.x, o.size.y];' % n)
            if r == "NO" or r is None:
                continue
            d = max(abs(r[0] - cx), abs(r[1] - cy))
            if d > a.tolerancia:
                desv.append("%s: previsto (%.2f, %.2f) real (%.2f, %.2f) tam real %.2fx%.2f" % (n, cx, cy, r[0], r[1], r[2], r[3]))
        for n, (p1, p2) in esp["cintas"].items():
            r = s.x('Object o = model().find("%s"); return [o.getProperty("StartLocation"), o.getProperty("EndLocation")];' % n)
            if not r:
                continue
            d = max(abs(r[0][0] - p1[0]), abs(r[0][1] - p1[1]), abs(r[1][0] - p2[0]), abs(r[1][1] - p2[1]))
            if d > a.tolerancia:
                desv.append("%s: prevista %s -> %s real %s -> %s" % (n, p1, p2, r[0][:2], r[1][:2]))
        rep["desviaciones_plano"] = desv
        print("Plano vs FlexSim (tolerancia %.2f m): %s" % (a.tolerancia, "coinciden" if not desv else "%d desviaciones" % len(desv)))
        for d in desv:
            print("   ", d)
    rep["astar"] = s.x(Q_A_ESTRELLA)
    print("A*:", rep["astar"])
    if a.guardar:
        s.c.reset()
        r = s.x('return savebyname(model(), "%s");' % a.guardar.replace("\\", "/"))
        rep["guardado"] = {"ruta": a.guardar, "ok": r == 1.0 and os.path.exists(a.guardar)}
        print("Guardado:", a.guardar, "OK" if rep["guardado"]["ok"] else "FALLO")
    if a.correr > 0:
        t = time.time()
        vig = s.correr(a.correr, semilla=a.semilla, vigilar=a.vigilar, parada=a.parada)
        if vig:
            rep["vigilancia"] = vig
            imprimir_vigilancia(vig)
            if vig["alarmas"]:
                rep["fallos"] += 1
        rep["tiempo_alcanzado"] = s.c.time()
        rep["run_s"] = round(time.time() - t, 1)
        print("Simulacion: pedido %.0f s, alcanzado %.0f s (%.1f s reales)" % (a.correr, rep["tiempo_alcanzado"], rep["run_s"]))
        rep["estadisticas"] = s.x(Q_ESTADISTICAS)
        for linea in rep["estadisticas"] or []:
            print("   ", linea)
    if a.recorridos > 0:
        s.c.reset()
        if a.semilla is not None:
            s.sembrar(a.semilla)
        if a.desde > 0:
            s.c.runToTime(a.desde)
        rc = revisar_recorridos(s, a.desde + a.recorridos * 3600, paso=1.0)
        rep["recorridos"] = rc
        nm, no = sum(rc["muros"].values()), sum(rc["objetos"].values())
        print("Recorridos (%.1f h desde t=%.0f s, %d tramos): %d cruces de muros A*, %d pasos por encima de objetos fijos"
              % (a.recorridos, a.desde, rc["tramos"], nm, no))
        for k, v in sorted(list(rc["muros"].items()) + list(rc["objetos"].items()), key=lambda kv: -kv[1])[:12]:
            print("   %5d  %s" % (v, k))
        for x in rc["ejemplos"][:5]:
            print("   ", x)
        if nm or no:
            rep["fallos"] += 1
    for q in a.consulta:
        r = s.x(q)
        rep.setdefault("consultas", []).append({"q": q, "r": r})
        print("Consulta:", q[:70], "->", r)
    if a.json:
        io.open(a.json, "w", encoding="utf-8").write(json.dumps(rep, ensure_ascii=False, indent=1, default=str))
    return 1 if rep["fallos"] or no_compilan else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
