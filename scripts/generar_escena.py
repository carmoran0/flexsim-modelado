#!/usr/bin/env python3
"""Generador de scripts FlexScript de construcción de escena (FlexSim 2027).

Describe la escena en Python y el generador escribe los bloques en el orden que evita los
errores conocidos (ver references/patrones.md):

    CREAR -> PROPIEDADES PREVIAS (p. ej. dimensiones de racks) -> COLOCAR -> GEOMETRÍA DEL
    PLANO (suelos, paredes) -> CONECTAR -> A* (navegador, muros lógicos, miembros) -> PROPIEDADES

Todos los bloques son repetibles: crear solo crea lo que falta, colocar y fijar propiedades es
idempotente y conectar usa marcas cx<tecla>_<otro> en las etiquetas de los dos extremos.

La misma descripción sirve para dibujar el plano 2D (SVG con rótulos, PNG de fondo para el
Model Background de FlexSim) con tamaños nominales: `previsualizar`, `svg_plano`, `png_fondo`.

Ejemplo mínimo:

    import sys; sys.path.insert(0, r"<ruta del skill>/scripts")
    from generar_escena import Escena

    e = Escena("Linea de ejemplo")
    e.crear("Source", "Entrada", bloque="Linea")
    e.crear("Processor", "Torno", bloque="Linea")
    e.crear("Conveyor::StraightConveyor", "Cinta1", bloque="Linea")
    e.crear("Sink", "Salida", bloque="Linea")
    e.crear("Operator", "Operario1", bloque="Recursos")

    e.colocar_centro("Torno", 10, 5)               # ancla
    e.encadenar("Entrada", "Torno", 0.5, "-x")     # pegado a la izquierda (sin transporte)
    e.encadenar("Salida", "Torno", 6, "+x")        # 6 m a la derecha: los cubre la cinta
    e.colocar_rel("Operario1", "Torno", 0, 2.5, desde="arriba")
    e.cinta_auto("Cinta1", "Torno", "Salida")      # del borde del origen al del destino

    e.zona("Zona_Taller", [(0, 0, 20, 10)], (0.85, 0.95, 0.85))
    e.muro("Muro_Sur", 0, 0, 20, 0, tipo="exterior")

    e.conectar("Entrada", "Torno"); e.conectar("Torno", "Cinta1"); e.conectar("Cinta1", "Salida")
    e.conectar("Torno", "Operario1", "S")
    e.miembros_astar(["Operario1"])
    e.codigo("Torno", "OperatorRef", ['return model().find("Operario1");'])

    e.escribir(r"C:/ruta/salida", "escena")
    e.svg_plano(r"C:/ruta/salida/plano.svg", "Plano de ejemplo")

Clases de los objetos visuales y de A* (ver references/api.md):
- Suelos y paredes: "VisualTool" con la propiedad VisualDisplay = "Plane" / "Cube"
  (clase verificada por ejecución con FlexSimPy).
- Muros lógicos: "AStar::Divider" dentro de "AStar::AStarNavigator" (nombres leídos del
  código fuente del módulo A*, github.com/flexsim/AStar). PathPoints en coordenadas del
  navegador, que se deja en (0,0,0).
"""
import io
import math
import os
import re
import zlib
import struct

CONV_PREFIX = "Conveyor::"
TE_CLASSES = ("Operator", "Transporter", "TaskExecuter", "Robot", "Crane", "ASRSvehicle", "Elevator")


def _id(name):
    return re.sub(r"\W", "", name)


def code_string(lines):
    """Convierte líneas de FlexScript en el literal de texto para setProperty (escapa \\ y ")."""
    s = " ".join(lines)
    return '"%s"' % s.replace("\\", "\\\\").replace('"', '\\"')


def _num(v):
    return ("%.3f" % v).rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


class Escena:
    def __init__(self, titulo, guardar_en="<ruta del modelo>.fsm"):
        self.titulo = titulo
        self.guardar_en = guardar_en
        self.objs = []          # (bloque, clase, nombre)
        self.ops = []           # operaciones de colocación (dato), ver _op_*
        self.conns = []         # (a, b, tecla)
        self.props = {}         # bloque -> [(obj, prop, valor)]
        self.prop_order = []
        self.pre_props = {}     # propiedades que van ANTES de colocar (cambian el tamaño)
        self.pre_order = []
        self.visual = []        # (bloque, tipo, nombre, datos)   tipo: plane / cube
        self.dividers = []      # (bloque, nombre, puntos)
        self.astar_members = []
        self.astar_barreras = []
        self.dibujo = []        # solo plano: ("puerta"|"muelle"|"texto"|"cota", datos)
        self.nominal = {}       # nombre -> (sx, sy) para previsualizar
        self.zcinta = 0
        self._k = 0

    # ------------------------------------------------------------- crear
    def crear(self, clase, nombre, bloque="Objetos"):
        if any(n == nombre for (_, _, n) in self.objs) or any(v[2] == nombre for v in self.visual):
            raise ValueError("nombre duplicado: %s" % nombre)
        self.objs.append((bloque, clase, nombre))

    def clase_de(self, nombre):
        for (_, c, n) in self.objs:
            if n == nombre:
                return c
        return None

    def tamano_nominal(self, nombre, sx, sy):
        """Tamaño supuesto para dibujar el plano (FlexSim usa el tamaño real al ejecutar)."""
        self.nominal[nombre] = (sx, sy)

    # ------------------------------------------------------------- colocar (operaciones)
    def colocar_centro(self, nombre, x, y):
        self.ops.append(("centro", nombre, x, y))

    def colocar_borde(self, nombre, x, y, lado="izq"):
        """Pone el borde izquierdo (o derecho) del objeto en x y su centro en y."""
        self.ops.append(("borde", nombre, x, y, lado))

    def encadenar(self, nombre, ref, hueco=0.5, dir="+x", fijar=None):
        """Coloca `nombre` junto a `ref` en la dirección dir (+x, -x, +y, -y), dejando `hueco`
        metros entre bordes, con el mismo eje transversal que ref (o `fijar` si se da)."""
        assert dir in ("+x", "-x", "+y", "-y")
        self.ops.append(("encadenar", nombre, ref, hueco, dir, fijar))

    def colocar_rel(self, nombre, ref, dx, dy, desde="centro"):
        """Centro de `nombre` = punto de `ref` + (dx, dy). desde: centro, derecha, izquierda,
        arriba (+y) o abajo (-y): el borde correspondiente de ref (en su centro transversal)."""
        self.ops.append(("rel", nombre, ref, dx, dy, desde))

    def cinta_auto(self, nombre, origen, destino, hueco_inicio=0, hueco_fin=0, desplaz=0,
                   desplaz_fin=None, eje=None):
        """Cinta del borde de `origen` que mira al destino al borde de `destino` que mira al
        origen. eje: 'x' o 'y' (por defecto, el dominante en la previsualización).
        desplaz: metros en el eje transversal sobre el centro del origen (abanicos)."""
        self.ops.append(("cinta", nombre, origen, destino, hueco_inicio, hueco_fin, desplaz,
                         desplaz if desplaz_fin is None else desplaz_fin, eje))

    def cinta_abs(self, nombre, inicio, fin):
        """Cinta entre dos puntos fijos (x, y) del plano, p. ej. un colector al que cargan de lado
        varias estaciones (la transferencia de entrada se crea al conectar, en el punto más cercano)."""
        self.ops.append(("cinta_abs", nombre, tuple(inicio), tuple(fin)))

    def flexscript_colocacion(self, lineas):
        self.ops.append(("raw", list(lineas)))

    # compatibilidad con la API anterior
    def colocar_abs(self, nombre, x, y, fx=0.5):
        if fx == 0.5:
            self.colocar_centro(nombre, x, y)
        else:
            self.colocar_borde(nombre, x, y, "izq" if fx == 0 else "der")

    def colocar_junto(self, nombre, ref, hueco=0.5, y=None, lado="derecha"):
        self.encadenar(nombre, ref, hueco, "+x" if lado == "derecha" else "-x", y)

    def cinta(self, nombre, origen, destino, hueco_inicio=0, desplaz_y=None):
        self.cinta_auto(nombre, origen, destino, hueco_inicio, eje="x",
                        desplaz=0 if desplaz_y is None else ("frac", desplaz_y))

    # ------------------------------------------------------------- plano: suelos, paredes, A*
    def zona(self, nombre, rects, color, bloque="Plano: suelos", etiqueta=None, mostrar_nombre=True,
             etiqueta_en=None):
        """Suelo coloreado (VisualTool Plane) por cada rectángulo (x1, y1, x2, y2).
        etiqueta_en=(x, y): dónde rotular la zona en el plano (por defecto, arriba del mayor)."""
        for i, r in enumerate(rects, 1):
            n = nombre if len(rects) == 1 else "%s_%d" % (nombre, i)
            self.visual.append((bloque, "plane", n, {"rect": r, "color": color, "show": mostrar_nombre,
                                                       "etiqueta": etiqueta or nombre, "grupo": nombre,
                                                       "etiqueta_en": etiqueta_en}))

    def muro(self, nombre, x1, y1, x2, y2, tipo="interior", grosor=0.3, altura=3.0, color=(0.6, 0.6, 0.6),
             bloque="Plano: paredes", astar=True):
        """Pared recta alineada con los ejes: VisualTool Cube y, si astar, un AStar::Divider."""
        if x1 != x2 and y1 != y2:
            raise ValueError("muro %s: solo paredes alineadas con x o con y" % nombre)
        self.visual.append((bloque, "cube", nombre, {"seg": (x1, y1, x2, y2), "tipo": tipo, "grosor": grosor,
                                                      "altura": altura, "color": color}))
        if astar:
            self.dividers.append((bloque + " (A*)", "AS_" + nombre, [(x1, y1), (x2, y2)]))

    def divider(self, nombre, puntos, bloque="A*: muros"):
        self.dividers.append((bloque, nombre, list(puntos)))

    def miembros_astar(self, nombres):
        """Task Executers que respetan los muros (conexión "A" navegador -> TE)."""
        for n in nombres:
            if n not in self.astar_members:
                self.astar_members.append(n)

    def barreras_astar(self, nombres):
        """Objetos fijos que A* debe esquivar (estanterías, estaciones, mesas...): conexión "A"
        del navegador al objeto. Sin esto, A* solo esquiva los muros (Divider) y los recursos pasan
        por encima de racks y puestos aunque su ruta respete las paredes (medido)."""
        for n in nombres:
            if n not in self.astar_barreras:
                self.astar_barreras.append(n)

    def puerta(self, x, y, ancho, orient, etiqueta=""):
        """Solo dibujo. orient 'h' (en un muro horizontal) o 'v'."""
        self.dibujo.append(("puerta", (x, y, ancho, orient, etiqueta)))

    def muelle(self, x, y, ancho, lado, etiqueta=""):
        """Solo dibujo. lado: 'oeste', 'este', 'norte', 'sur' (el muelle sobresale hacia fuera)."""
        self.dibujo.append(("muelle", (x, y, ancho, lado, etiqueta)))

    def texto_plano(self, x, y, texto, tam=1.2, color="#333"):
        self.dibujo.append(("texto", (x, y, texto, tam, color)))

    # ------------------------------------------------------------- conectar
    def conectar(self, a, b, tecla="A"):
        if tecla not in ("A", "S"):
            raise ValueError("tecla de conexion: 'A' (flujo) o 'S' (puerto central)")
        if (a, b, tecla) not in self.conns:
            self.conns.append((a, b, tecla))

    # ------------------------------------------------------------- propiedades
    def _addprop(self, store, order, bloque, item):
        if bloque not in store:
            store[bloque] = []
            order.append(bloque)
        store[bloque].append(item)

    def propiedad(self, obj, prop, valor, bloque="Logica", antes_de_colocar=False):
        """valor: número, o texto ya en FlexScript (p. ej. '"texto"' o '[1, 2, 0]').
        antes_de_colocar: para propiedades que cambian el tamaño (dimensiones de racks)."""
        if antes_de_colocar:
            self._addprop(self.pre_props, self.pre_order, bloque, (obj, prop, str(valor)))
        else:
            self._addprop(self.props, self.prop_order, bloque, (obj, prop, str(valor)))

    def codigo(self, obj, prop, lineas, bloque="Logica"):
        """Propiedad de tipo Code (SendToPort, TransportRef, OperatorRef, ProcessTime...)."""
        self.propiedad(obj, prop, code_string(lineas), bloque)

    # Nodos de variables de los triggers. Verificados en FlexSim 2027 (FlexSimPy, 13-14/10/2026):
    # OnEntry (Processor, Queue, Combiner, Sink, Rack), OnExit (Processor, Rack), OnProcessFinish
    # (Processor) y OnReset (Queue, Rack, Sink, Source, Combiner). OnSetupFinish, OnCreation y
    # OnMessage siguen el mismo patrón del código de la librería (bindEventByName), sin ejecutar.
    EVENTOS = {"OnEntry": "entrytrigger", "OnExit": "exittrigger", "OnProcessFinish": "processfinishtrigger",
               "OnSetupFinish": "setupfinishtrigger", "OnCreation": "creationtrigger",
               "OnMessage": "messagetrigger", "OnReset": "resettrigger"}

    def trigger(self, obj, evento, lineas, bloque="Logica"):
        """Trigger por script: crea el nodo variables/<evento> como FlexScript y re-enlaza el
        objeto. Sustituye a cualquier trigger que hubiera (lista de opciones de la GUI incluida)."""
        var = self.EVENTOS.get(evento, evento)
        self.propiedad(obj, ("var_codigo", var), code_string(lineas), bloque)

    def variable(self, obj, var, valor, bloque="Logica"):
        """Variable interna sin propiedad (p. ej. Separator 'unpack', Combiner 'pack'): número."""
        self.propiedad(obj, ("var_num", var), valor, bloque)

    def variable_codigo(self, obj, var, lineas, bloque="Logica"):
        """Variable interna de tipo código (p. ej. Separator 'splitquantity')."""
        self.propiedad(obj, ("var_codigo", var), code_string(lineas), bloque)

    # ------------------------------------------------------------- patrones verificados
    # Extraídos de modelos que funcionan en FlexSim 2027 (medidos con FlexSimPy). Cada uno resuelve
    # un fallo silencioso: ver references/patrones.md §11.
    def equipo(self, dispatcher, clase, prefijo, n, usuarios=(), bloque="Recursos"):
        """Crea un Dispatcher y n recursos móviles (Operator, Transporter, TaskExecuter) prefijo1..n.
        Conecta Dispatcher -> miembros ("A") y cada usuario -> Dispatcher ("S"). La colocación de
        los miembros queda para quien llama. Devuelve los nombres de los miembros."""
        self.crear("Dispatcher", dispatcher, bloque=bloque)
        miembros = [prefijo + str(i) for i in range(1, n + 1)]
        for m in miembros:
            self.crear(clase, m, bloque=bloque)
            self.conectar(dispatcher, m)
        for u in usuarios:
            self.conectar(u, dispatcher, "S")
        return miembros

    def puestos(self, prefijo, n, equipo, operarios=1, clase="Processor", bloque="Objetos", logica="Logica"):
        """n puestos prefijo1..n de CAPACIDAD 1 atendidos por `equipo` (un Dispatcher).
        Un Processor con MaxContent > 1 y operarios de proceso deja a los operarios enganchados en
        «utilize» (medido): varios puestos = varios objetos. `operarios` = operarios por item.
        Devuelve los nombres; las conexiones de flujo quedan para quien llama."""
        nombres = [prefijo + str(i) for i in range(1, n + 1)]
        for p in nombres:
            self.crear(clase, p, bloque=bloque)
            self.conectar(p, equipo, "S")
            self.propiedad(p, "MaxContent", 1, bloque=logica)
            self.propiedad(p, "UseProcessOperators", 1, bloque=logica)
            self.propiedad(p, "NumProcessOperators", operarios, bloque=logica)
            self.codigo(p, "OperatorRef", ['return model().find("%s");' % equipo], bloque=logica)
        return nombres

    def estacion_fefo(self, nombre, etiquetas, caducidad="caducidad", equipo=None, al_reservar=(),
                      bloque="Logica"):
        """Configura un Combiner ya creado como estación que TIRA del stock con FEFO.
        Puerto de entrada 1: el contenedor (pedido). Puertos 2..k+1: una fuente (Rack) por cada
        etiqueta de `etiquetas`, que dice cuántas unidades pide el pedido a esa fuente. Conecta las
        fuentes en ese orden. Al entrar el pedido se fijan componentlist Y targetcomponentsum (sin
        este último el Combiner sigue esperando la cantidad anterior y se bloquea). De cada fuente
        solo acepta el item libre de `caducidad` mínima; el item queda reservado para la estación.
        al_reservar: líneas FlexScript extra al reservar (variables `item`, `rk` = fuente)."""
        hdr = ["Object current = ownerobject(c);", "Object item = param(1);"]
        entrada = hdr + [
            "int port = param(2);",
            "if (port == 1) {",
            'treenode cl = getvarnode(current, "componentlist");',
            "double total = 0;"]
        for i, et in enumerate(etiquetas, 1):
            entrada += ['double q%d = item.labels.assert("%s", 0).value; cl.subnodes[%d].subnodes[1].value = q%d; total = total + q%d;'
                        % (i, et, i, i, i)]
        entrada += ['setvarnum(current, "targetcomponentsum", total);', "}", "return 0;"]
        # Caché por fuente (instante, contenido, nº de reservas): evita recorrer el rack entero por
        # cada item evaluado (O(n²) con miles de palés).
        fefo = hdr + [
            "int port = param(2);",
            "if (port == 1) { return 1; }",
            'string rp = item.labels.assert("reservado_por", "").value;',
            "if (rp == current.name) { return 1; }",
            'if (rp != \"\") { return 0; }',
            "Object rk = current.inObjects[port];",
            'treenode ct = rk.labels.assert("fefo_t", -1); treenode cn = rk.labels.assert("fefo_n", -1);',
            'treenode cv = rk.labels.assert("fefo_v", 0); treenode cm = rk.labels.assert("fefo_min", 0);',
            'treenode cr = rk.labels.assert("fefo_vc", -1);',
            "if (ct.value != Model.time || cn.value != rk.subnodes.length || cr.value != cv.value) {",
            "double m = 1e12;",
            "for (int i = 1; i <= rk.subnodes.length; i++) {",
            "Object o = rk.subnodes[i];",
            'if (o.labels.assert("reservado_por", "").value == "") { double v = o.labels.assert("%s", 0).value; if (v < m) { m = v; } }' % caducidad,
            "}",
            "cm.value = m; ct.value = Model.time; cn.value = rk.subnodes.length; cr.value = cv.value;",
            "}",
            'if (item.labels.assert("%s", 0).value <= cm.value) {' % caducidad,
            'item.labels["reservado_por"].value = current.name; cv.value = cv.value + 1;'] + list(al_reservar) + [
            "return 1;",
            "}",
            "return 0;"]
        reset = ["Object current = ownerobject(c);",
                 "for (int i = 2; i <= current.inObjects.length; i++) {",
                 "Object rk = current.inObjects[i];",
                 'rk.labels.assert("fefo_t", -1).value = -1; rk.labels.assert("fefo_v", 0).value = 0; rk.labels.assert("fefo_vc", -1).value = -1;',
                 "}"]
        self.trigger(nombre, "OnEntry", entrada, bloque=bloque)
        self.trigger(nombre, "OnReset", reset, bloque=bloque)
        self.propiedad(nombre, "Pull", 1, bloque=bloque)
        self.codigo(nombre, "PullRequirement", fefo, bloque=bloque)
        if equipo:
            self.propiedad(nombre, "UseProcessOperators", 1, bloque=bloque)
            self.propiedad(nombre, "NumProcessOperators", 1, bloque=bloque)
            self.codigo(nombre, "OperatorRef", ['return model().find("%s");' % equipo], bloque=bloque)

    def separador_lote(self, nombre, etiqueta="n_unidades", bloque="Logica"):
        """Configura un Separator ya creado para dividir cada lote en item.labels[etiqueta] items
        (modo Split: unpack = 0; splitquantity = código). Las copias heredan las etiquetas."""
        self.variable(nombre, "unpack", 0, bloque=bloque)
        self.variable_codigo(nombre, "splitquantity",
                             ["Object item = param(1);", 'return item.labels.assert("%s", 1).value;' % etiqueta],
                             bloque=bloque)

    # ------------------------------------------------------------- previsualización nominal
    def _size(self, n, tam):
        if n in self.nominal:
            return self.nominal[n]
        c = self.clase_de(n) or ""
        for k, v in tam.items():
            if c == k or c.endswith("::" + k):
                return v
        return tam.get("*", (2.0, 2.0))

    def previsualizar(self, tamanos=None):
        """Evalúa las operaciones con tamaños supuestos. Devuelve (pos, cintas):
        pos[nombre] = (cx, cy, sx, sy); cintas[nombre] = ((x1, y1), (x2, y2))."""
        # Tamaños por defecto MEDIDOS en FlexSim 2027 (Object.create + size), 13/10/2026
        tam = {"Source": (1.06, 1.06), "Sink": (1.06, 1.06), "Queue": (2.0, 2.0), "Processor": (4.0, 3.0),
               "Combiner": (4.0, 3.0), "Separator": (4.0, 3.0), "Rack": (20.0, 1.5), "Robot": (0.68, 1.0),
               "Operator": (0.4, 0.58), "Transporter": (2.38, 1.37), "TaskExecuter": (2.0, 1.0),
               "Dispatcher": (0.95, 1.5), "VisualTool": (10.0, 6.0), "*": (2.0, 2.0)}
        tam.update(tamanos or {})
        pos, cintas = {}, {}

        def get(n):
            if n not in pos:
                raise KeyError("previsualizar: %s se usa antes de colocarse" % n)
            return pos[n]

        for op in self.ops:
            k = op[0]
            if k == "centro":
                _, n, x, y = op
                sx, sy = self._size(n, tam)
                pos[n] = (x, y, sx, sy)
            elif k == "borde":
                _, n, x, y, lado = op
                sx, sy = self._size(n, tam)
                pos[n] = (x + sx / 2 if lado == "izq" else x - sx / 2, y, sx, sy)
            elif k == "encadenar":
                _, n, ref, h, d, fijar = op
                cx, cy, rx, ry = get(ref)
                sx, sy = self._size(n, tam)
                if d == "+x":
                    p = (cx + rx / 2 + h + sx / 2, cy if fijar is None else fijar)
                elif d == "-x":
                    p = (cx - rx / 2 - h - sx / 2, cy if fijar is None else fijar)
                elif d == "+y":
                    p = (cx if fijar is None else fijar, cy + ry / 2 + h + sy / 2)
                else:
                    p = (cx if fijar is None else fijar, cy - ry / 2 - h - sy / 2)
                pos[n] = (p[0], p[1], sx, sy)
            elif k == "rel":
                _, n, ref, dx, dy, desde = op
                cx, cy, rx, ry = get(ref)
                bx, by = {"centro": (cx, cy), "derecha": (cx + rx / 2, cy), "izquierda": (cx - rx / 2, cy),
                          "arriba": (cx, cy + ry / 2), "abajo": (cx, cy - ry / 2)}[desde]
                sx, sy = self._size(n, tam)
                pos[n] = (bx + dx, by + dy, sx, sy)
            elif k == "cinta":
                _, n, o, d, hi, hf, dz, dzf, eje = op
                a, b = get(o), get(d)
                start, end = self._cinta_puntos(a, b, hi, hf, dz, dzf, eje)
                cintas[n] = (start, end)
                pos[n] = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2,
                          abs(end[0] - start[0]) or 1.0, abs(end[1] - start[1]) or 1.0)
            elif k == "cinta_abs":
                _, n, start, end = op
                cintas[n] = (start, end)
                pos[n] = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2,
                          abs(end[0] - start[0]) or 1.0, abs(end[1] - start[1]) or 1.0)
        return pos, cintas

    @staticmethod
    def _eje(a, b, eje):
        if eje:
            return eje
        return "x" if abs(b[0] - a[0]) >= abs(b[1] - a[1]) else "y"

    def _cinta_puntos(self, a, b, hi, hf, dz, dzf, eje):
        e = self._eje(a, b, eje)
        if isinstance(dz, tuple):            # compatibilidad: fracción de medio tamaño y
            dz = dz[1] * a[3] / 2
            dzf = 0
        if e == "x":
            sg = 1 if b[0] >= a[0] else -1
            return ((a[0] + sg * (a[2] / 2 + hi), a[1] + dz), (b[0] - sg * (b[2] / 2 + hf), b[1] + dzf))
        sg = 1 if b[1] >= a[1] else -1
        return ((a[0] + dz, a[1] + sg * (a[3] / 2 + hi)), (b[0] + dzf, b[1] - sg * (b[3] / 2 + hf)))

    # ------------------------------------------------------------- FlexScript: colocación
    def _v(self, p):
        self._k += 1
        return "%s%d" % (p, self._k)

    def _lay_lines(self, prev):
        pos, _ = prev
        L = []
        for op in self.ops:
            k = op[0]
            if k == "raw":
                L += op[1]
                continue
            if k == "cinta_abs":
                _, n, (x1, y1), (x2, y2) = op
                cv = self._v("k")
                L += ['treenode %s = model().find("%s");' % (cv, n),
                      "if (objectexists(%s)) {" % cv,
                      "    %s.as(Object).location = Vec3(0, 0, 0);" % cv,
                      '    %s.as(Object).setProperty("StartLocation", [%s, %s, zCinta]);' % (cv, _num(x1), _num(y1)),
                      '    %s.as(Object).setProperty("EndLocation", [%s, %s, zCinta]);' % (cv, _num(x2), _num(y2)),
                      "}"]
                continue
            if k == "centro":
                _, n, x, y = op
                v = self._v("o")
                L += ['treenode %s = model().find("%s");' % (v, n),
                      "if (objectexists(%s)) { %s.as(Object).setLocation(%s, %s, 0, 0.5, 0.5, 0); }"
                      % (v, v, _num(x), _num(y))]
            elif k == "borde":
                _, n, x, y, lado = op
                v = self._v("o")
                L += ['treenode %s = model().find("%s");' % (v, n),
                      "if (objectexists(%s)) { %s.as(Object).setLocation(%s, %s, 0, %s, 0.5, 0); }"
                      % (v, v, _num(x), _num(y), 0 if lado == "izq" else 1)]
            elif k == "encadenar":
                _, n, ref, h, d, fijar = op
                v, r, c, s = self._v("o"), self._v("r"), self._v("c"), self._v("s")
                if d in ("+x", "-x"):
                    sg = "+" if d == "+x" else "-"
                    xx = "%s.x %s (%s.x / 2 + %s + %s.as(Object).size.x / 2)" % (c, sg, s, _num(h), v)
                    yy = "%s.y" % c if fijar is None else _num(fijar)
                else:
                    sg = "+" if d == "+y" else "-"
                    yy = "%s.y %s (%s.y / 2 + %s + %s.as(Object).size.y / 2)" % (c, sg, s, _num(h), v)
                    xx = "%s.x" % c if fijar is None else _num(fijar)
                L += ['treenode %s = model().find("%s");' % (v, n),
                      'treenode %s = model().find("%s");' % (r, ref),
                      "if (objectexists(%s) && objectexists(%s)) {" % (v, r),
                      "    Vec3 %s = %s.as(Object).getLocation(0.5, 0.5, 0); Vec3 %s = %s.as(Object).size;" % (c, r, s, r),
                      "    %s.as(Object).setLocation(%s, %s, 0, 0.5, 0.5, 0);" % (v, xx, yy),
                      "}"]
            elif k == "rel":
                _, n, ref, dx, dy, desde = op
                v, r, c, s = self._v("o"), self._v("r"), self._v("c"), self._v("s")
                bx, by = {"centro": ("%s.x" % c, "%s.y" % c),
                          "derecha": ("%s.x + %s.x / 2" % (c, s), "%s.y" % c),
                          "izquierda": ("%s.x - %s.x / 2" % (c, s), "%s.y" % c),
                          "arriba": ("%s.x" % c, "%s.y + %s.y / 2" % (c, s)),
                          "abajo": ("%s.x" % c, "%s.y - %s.y / 2" % (c, s))}[desde]
                L += ['treenode %s = model().find("%s");' % (v, n),
                      'treenode %s = model().find("%s");' % (r, ref),
                      "if (objectexists(%s) && objectexists(%s)) {" % (v, r),
                      "    Vec3 %s = %s.as(Object).getLocation(0.5, 0.5, 0); Vec3 %s = %s.as(Object).size;" % (c, r, s, r),
                      "    %s.as(Object).setLocation(%s + %s, %s + %s, 0, 0.5, 0.5, 0);" % (v, bx, _num(dx), by, _num(dy)),
                      "}"]
            elif k == "cinta":
                _, n, o, d, hi, hf, dz, dzf, eje = op
                e = self._eje(pos[o], pos[d], eje)
                sgn = 1 if (pos[d][0] >= pos[o][0] if e == "x" else pos[d][1] >= pos[o][1]) else -1
                sg = "+" if sgn > 0 else "-"
                ns = "-" if sgn > 0 else "+"
                cv, a, b, ca, sa, cb, sb = (self._v("k"), self._v("a"), self._v("b"), self._v("p"),
                                             self._v("q"), self._v("u"), self._v("w"))
                if isinstance(dz, tuple):
                    dzs, dzfs = "%s * %s.y / 2" % (_num(dz[1]), sa), "0"
                else:
                    dzs, dzfs = _num(dz), _num(dzf)
                if e == "x":
                    st = "[%s.x %s (%s.x / 2 + %s), %s.y + %s, zCinta]" % (ca, sg, sa, _num(hi), ca, dzs)
                    en = "[%s.x %s (%s.x / 2 + %s), %s.y + %s, zCinta]" % (cb, ns, sb, _num(hf), cb, dzfs)
                else:
                    st = "[%s.x + %s, %s.y %s (%s.y / 2 + %s), zCinta]" % (ca, dzs, ca, sg, sa, _num(hi))
                    en = "[%s.x + %s, %s.y %s (%s.y / 2 + %s), zCinta]" % (cb, dzfs, cb, ns, sb, _num(hf))
                L += ['treenode %s = model().find("%s");' % (cv, n),
                      'treenode %s = model().find("%s");' % (a, o),
                      'treenode %s = model().find("%s");' % (b, d),
                      "if (objectexists(%s) && objectexists(%s) && objectexists(%s)) {" % (cv, a, b),
                      "    Vec3 %s = %s.as(Object).getLocation(0.5, 0.5, 0); Vec3 %s = %s.as(Object).size;" % (ca, a, sa, a),
                      "    Vec3 %s = %s.as(Object).getLocation(0.5, 0.5, 0); Vec3 %s = %s.as(Object).size;" % (cb, b, sb, b),
                      "    %s.as(Object).location = Vec3(0, 0, 0);" % cv,
                      '    %s.as(Object).setProperty("StartLocation", %s);' % (cv, st),
                      '    %s.as(Object).setProperty("EndLocation", %s);' % (cv, en),
                      "}"]
        return L

    # ------------------------------------------------------------- FlexScript: bloques
    def _crear_lines(self, items):
        L = []
        for (cls, n) in items:
            v = "t" + _id(n)
            L += ['treenode %s = model().find("%s");' % (v, n),
                  "if (!objectexists(%s)) {" % v,
                  '    %s = Object.create("%s");' % (v, cls),
                  '    %s.name = "%s";' % (v, n), "}"]
        return L

    def _visual_geom_lines(self, items, tag):
        L = []
        for (_, tipo, n, d) in items:
            v = "g%s%s" % (tag, _id(n))
            L.append('treenode %s = model().find("%s");' % (v, n))
            L.append("if (objectexists(%s)) {" % v)
            if tipo == "plane":
                x1, y1, x2, y2 = d["rect"]
                cx, cy, w, h = (x1 + x2) / 2, (y1 + y2) / 2, abs(x2 - x1), abs(y2 - y1)
                L += ['    %s.as(Object).setProperty("VisualDisplay", "Plane");' % v,
                      "    %s.as(Object).setSize(%s, %s, 0.05);" % (v, _num(w), _num(h)),
                      "    %s.as(Object).setLocation(%s, %s, 0, 0.5, 0.5, 0);" % (v, _num(cx), _num(cy)),
                      "    %s.as(Object).color = Color(%s, %s, %s);" % ((v,) + tuple(_num(c) for c in d["color"])),
                      '    %s.as(Object).setProperty("ShowName", %d);' % (v, 1 if d["show"] else 0)]
            else:
                x1, y1, x2, y2 = d["seg"]
                g, alt = d["grosor"], d["altura"]
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                if y1 == y2:
                    sx, sy = abs(x2 - x1), g
                else:
                    sx, sy = g, abs(y2 - y1)
                L += ['    %s.as(Object).setProperty("VisualDisplay", "Cube");' % v,
                      "    %s.as(Object).setSize(%s, %s, %s);" % (v, _num(sx), _num(sy), _num(alt)),
                      "    %s.as(Object).setLocation(%s, %s, 0, 0.5, 0.5, 0);" % (v, _num(cx), _num(cy)),
                      "    %s.as(Object).color = Color(%s, %s, %s);" % ((v,) + tuple(_num(c) for c in d["color"]))]
            L.append("}")
        return L

    def _conn_lines(self, conns, tag):
        L = []
        for i, (a, b, k) in enumerate(conns, 1):
            va, vb = "%s%da%s" % (tag, i, _id(a)), "%s%db%s" % (tag, i, _id(b))
            ma, mb = "cx%s_%s" % (k, b), "cx%s_%s" % (k, a)
            L += ['treenode %s = model().find("%s");' % (va, a),
                  'treenode %s = model().find("%s");' % (vb, b),
                  "if (objectexists(%s) && objectexists(%s)) {" % (va, vb),
                  '    if (%s.labels.assert("%s", 0).value == 0 || %s.labels.assert("%s", 0).value == 0) {' % (va, ma, vb, mb),
                  '        contextdragconnection(%s, %s, "%s");' % (va, vb, k),
                  '        %s.labels.assert("%s", 0).value = 1;' % (va, ma),
                  '        %s.labels.assert("%s", 0).value = 1;' % (vb, mb),
                  "    }", "}"]
        return L

    def _divider_lines(self, items, crear_nav, tag):
        L = []
        nv = "nav%s" % tag
        L.append('treenode %s = model().find("AStarNavigator");' % nv)
        if crear_nav:
            # Object.create("AStar::AStarNavigator") NO crea el navegador (devuelve otro nodo,
            # comprobado en FlexSim 2027): se crea como lo hace el propio módulo A*.
            L += ["if (!objectexists(%s)) {" % nv,
                  '    %s = createinstance(library().find("?AStarNavigator"), model());' % nv,
                  "}"]
        L.append('if (objectexists(%s) && %s.as(Object).getProperty("Class") == "AStar::AStarNavigator") {' % (nv, nv))
        for (_, n, pts) in items:
            v = "d%s%s" % (tag, _id(n))
            arr = "[%s]" % ", ".join("[%s, %s, 0]" % (_num(x), _num(y)) for (x, y) in pts)
            L += ['    treenode %s = model().find("AStarNavigator/%s");' % (v, n),
                  "    if (!objectexists(%s)) { %s = model().find(\"%s\"); }" % (v, v, n),
                  "    if (!objectexists(%s)) {" % v,
                  '        %s = Object.create("AStar::Divider");' % v,
                  '        %s.name = "%s";' % (v, n),
                  "    }",
                  "    if (%s.up != %s) { %s.up = %s; }" % (v, nv, v, nv),
                  '    function_s(%s, "assertNavigator");' % v,
                  '    %s.as(Object).setProperty("PathPoints", %s);' % (v, arr)]
        L += ['    function_s(%s, "rebuildMeshes");' % nv, "}"]
        return L

    def _prop_lines(self, items, tag):
        L, seen = [], {}
        for (o, p, val) in items:
            if o not in seen:
                seen[o] = "p%s%s" % (tag, _id(o))
                L.append('treenode %s = model().find("%s");' % (seen[o], o))
            v = seen[o]
            if isinstance(p, tuple) and p[0] == "var_num":
                L.append('if (objectexists(%s)) { setvarnum(%s, "%s", %s); }' % (v, v, p[1], val))
            elif isinstance(p, tuple):
                n = self._v("vn")
                L += ["if (objectexists(%s)) {" % v,
                      '    treenode %s = %s.as(Object).find(">variables").subnodes.assert("%s");' % (n, v, p[1]),
                      "    %s.value = %s;" % (n, val),
                      "    enablecode(%s, 1); buildnodeflexscript(%s); rebindobjectattributes(%s);" % (n, n, v),
                      "}"]
            else:
                L.append('if (objectexists(%s)) { %s.as(Object).setProperty("%s", %s); }' % (v, v, p, val))
        return L

    @staticmethod
    def _orden(seq):
        out = []
        for b in seq:
            if b not in out:
                out.append(b)
        return out

    def bloques(self, tamanos=None):
        prev = self.previsualizar(tamanos)
        self._k = 0
        bl = []
        visual_cls = {"plane": "VisualTool", "cube": "VisualTool"}
        # 1. crear
        for b in self._orden([o[0] for o in self.objs]):
            bl.append(("Crear: %s" % b, self._crear_lines([(c, n) for (bb, c, n) in self.objs if bb == b])))
        for b in self._orden([v[0] for v in self.visual]):
            bl.append(("Crear: %s (objetos visuales)" % b,
                       self._crear_lines([(visual_cls[t], n) for (bb, t, n, _) in self.visual if bb == b])))
        # 2. propiedades que cambian el tamaño
        for i, b in enumerate(self.pre_order):
            bl.append(("Antes de colocar: %s (repetible)" % b, self._prop_lines(self.pre_props[b], "a%d" % i)))
        # 3. colocar
        if self.ops:
            bl.append(("Colocar (despues de crear y ANTES de conectar; repetible)",
                       ["double zCinta = %s;  /* altura de las cintas */" % _num(self.zcinta)] + self._lay_lines(prev) + [
                           "/* Posicion de reset = la colocada. Sin esto, cada Reset deja a operarios y carretillas",
                           "   donde acabaron y dos corridas con la misma semilla dan resultados distintos (medido). */",
                           "for (int iRst = 1; iRst <= model().subnodes.length; iRst++) {",
                           "    treenode nRst = model().subnodes[iRst];",
                           "    if (nRst.is(TaskExecuter)) setresetposition(nRst);",
                           "}"]))
        # 4. geometría del plano
        for i, b in enumerate(self._orden([v[0] for v in self.visual])):
            bl.append(("Geometria: %s (repetible)" % b,
                       self._visual_geom_lines([v for v in self.visual if v[0] == b], "v%d" % i)))
        # 5. conectar
        if self.conns:
            bl.append(("Conectar (despues de colocar: las transferencias de cinta se crean aqui; repetible)",
                       self._conn_lines(self.conns, "k")))
        # 6. A*
        dgroups = self._orden([d[0] for d in self.dividers])
        for i, b in enumerate(dgroups):
            bl.append(("A*: %s (repetible)" % b,
                       self._divider_lines([d for d in self.dividers if d[0] == b], i == 0, "%d" % i)))
        if self.astar_members:
            L = ['treenode navM = model().find("AStarNavigator");', "if (objectexists(navM)) {"]
            for j, n in enumerate(self.astar_members, 1):
                v = "m%d%s" % (j, _id(n))
                L += ['    treenode %s = model().find("%s");' % (v, n),
                      '    if (objectexists(%s)) { if (%s.labels.assert("cxA_AStarNavigator", 0).value == 0) {' % (v, v),
                      '        contextdragconnection(navM, %s, "A");' % v,
                      '        %s.labels.assert("cxA_AStarNavigator", 0).value = 1; } }' % v]
            L.append("}")
            bl.append(("A*: miembros (los Task Executers rodean los muros; repetible)", L))
        if self.astar_barreras:
            L = ['treenode navB = model().find("AStarNavigator");', "if (objectexists(navB)) {"]
            for j, n in enumerate(self.astar_barreras, 1):
                v = "b%d%s" % (j, _id(n))
                L += ['    treenode %s = model().find("%s");' % (v, n),
                      '    if (objectexists(%s)) { if (%s.labels.assert("cxA_AStarNavigator", 0).value == 0) {' % (v, v),
                      '        contextdragconnection(navB, %s, "A");' % v,
                      '        %s.labels.assert("cxA_AStarNavigator", 0).value = 1; } }' % v]
            L.append("}")
            bl.append(("A*: barreras (estanterias y puestos que los recursos rodean; repetible)", L))
        # 7. propiedades
        for i, b in enumerate(self.prop_order):
            bl.append(("Propiedades: %s (repetible)" % b, self._prop_lines(self.props[b], "g%d" % i)))
        return bl

    def escribir(self, carpeta, prefijo, tamanos=None, cabecera_extra=""):
        os.makedirs(carpeta, exist_ok=True)
        bl = self.bloques(tamanos)
        cab = ("/* ESCENA: %s\n"
               "   Orden: crear -> (dimensiones) -> colocar -> geometria del plano -> conectar -> A* -> propiedades.\n"
               "   Todos los bloques son repetibles. Uso: pegar los bloques en orden en la Script Console, o\n"
               "   pegar las lineas de EJECUTAR_%s.txt (executefsfile, 'For developer use': si falla, a mano).\n"
               "   Campos de tipo Code fijados por script aparecen VACIOS en la GUI: es normal.\n%s\n"
               "   GUARDADO\n"
               "   Guarda con Ctrl+S en %s, o sin dialogo desde la consola:\n"
               "   savebyname(model(), \"C:/ruta/modelo.fsm\");   (verificado en FlexSim 2027) */\n") % (
                   self.titulo, prefijo, cabecera_extra, self.guardar_en)
        partes, run = [cab], []
        bdir = os.path.join(carpeta, prefijo + "_bloques")
        os.makedirs(bdir, exist_ok=True)
        for f in os.listdir(bdir):
            if f.endswith(".fs"):
                os.remove(os.path.join(bdir, f))
        ruta = os.path.abspath(bdir).replace("\\", "/")
        for i, (titulo, L) in enumerate(bl, 1):
            txt = "/* BLOQUE %d - %s */\n%s" % (i, titulo, "\n".join(L))
            partes.append(txt)
            fn = "%02d.fs" % i
            io.open(os.path.join(bdir, fn), "w", encoding="utf-8", newline="\n").write(txt + "\n")
            run.append('executefsfile("%s/%s", 1);  /* %s */' % (ruta, fn, titulo[:60]))
        partes.append("/* FIN. Guarda con Ctrl+S. */\n")
        io.open(os.path.join(carpeta, prefijo + ".flexscript"), "w", encoding="utf-8", newline="\n").write("\n\n".join(partes))
        io.open(os.path.join(carpeta, "EJECUTAR_%s.txt" % prefijo), "w", encoding="utf-8", newline="\n").write(
            "/* Pega estas lineas en la Script Console (modelo vacio). Guarda con Ctrl+S al acabar. */\n"
            + "\n".join(run) + "\n")
        C = ["/* LIMPIEZA de %s: destruye los objetos de cada bloque de creacion. Despues repite ese\n"
             "   bloque y los de colocar, geometria, conectar, A* y propiedades. Guarda con Ctrl+S. */" % prefijo]
        grupos = [(b, [n for (bb, _, n) in self.objs if bb == b]) for b in self._orden([o[0] for o in self.objs])]
        grupos += [(b, [n for (bb, _, n, _) in self.visual if bb == b]) for b in self._orden([v[0] for v in self.visual])]
        for b, names in grupos:
            C.append("\n/* Limpieza: %s */" % b)
            for n in names:
                v = "lim" + _id(b) + _id(n)
                C += ['treenode %s = model().find("%s");' % (v, n), "if (objectexists(%s)) { %s.destroy(); }" % (v, v)]
        convs = [n for (_, c, n) in self.objs if c.startswith(CONV_PREFIX)]
        if convs:
            C.append("\n/* Limpieza: solo cintas (si una transferencia quedo mal) */")
            for n in convs:
                v = "limCintas" + _id(n)
                C += ['treenode %s = model().find("%s");' % (v, n), "if (objectexists(%s)) { %s.destroy(); }" % (v, v)]
        if self.dividers:
            C.append("\n/* Limpieza: navegador A* y todos sus muros logicos */")
            C += ['treenode limNav = model().find("AStarNavigator");', "if (objectexists(limNav)) { limNav.destroy(); }"]
        io.open(os.path.join(carpeta, "limpiar_%s.flexscript" % prefijo), "w", encoding="utf-8", newline="\n").write("\n".join(C) + "\n")
        # posiciones previstas (para comparar con FlexSim real: flexsim_check.py --posiciones)
        import json
        pos, cintas = self.previsualizar(tamanos)
        io.open(os.path.join(carpeta, "%s_posiciones.json" % prefijo), "w", encoding="utf-8").write(json.dumps(
            {"objetos": {n: [round(v, 3) for v in p] for n, p in pos.items() if n not in cintas},
             "cintas": {n: [list(a), list(b)] for n, (a, b) in cintas.items()}}, indent=1))
        return len(bl)

    # ------------------------------------------------------------- plano SVG
    ESTILO_MURO = {"exterior": ("#222", 0.45, None), "camara": ("#1565c0", 0.35, None),
                   "cortafuegos": ("#c62828", 0.35, "1.2,0.6"), "interior": ("#555", 0.25, None)}
    COLOR_CLASE = {"Processor": "#ffb74d", "Queue": "#fff176", "Source": "#81c784", "Sink": "#e57373",
                   "Rack": "#8d6e63", "Robot": "#7e57c2", "Operator": "#26a69a", "Transporter": "#ef6c00",
                   "Combiner": "#ff8a65", "Separator": "#ffcc80",
                   "TaskExecuter": "#00897b", "Dispatcher": "#90a4ae"}

    def svg_plano(self, ruta, titulo, subtitulo="", leyenda=None, tabla=None, notas=None,
                  tamanos=None, px_por_m=10, margen=8, mostrar_recursos=True, estilos_muro=None,
                  etiquetas=None, ancho_panel=460):
        """Plano 2D con suelos, paredes, puertas, muelles, racks, objetos, cintas, cotas y leyenda.
        etiquetas: dict nombre -> texto, o (texto, posición) con posición 'arriba' (defecto),
        'abajo', 'izquierda' o 'derecha' respecto al objeto."""
        pos, cintas = self.previsualizar(tamanos)
        est = dict(self.ESTILO_MURO)
        est.update(estilos_muro or {})
        xs, ys = [], []
        for (_, t, n, d) in self.visual:
            if t == "plane":
                x1, y1, x2, y2 = d["rect"]
            else:
                x1, y1, x2, y2 = d["seg"]
            xs += [x1, x2]; ys += [y1, y2]
        for (cx, cy, sx, sy) in pos.values():
            xs += [cx - sx / 2, cx + sx / 2]; ys += [cy - sy / 2, cy + sy / 2]
        xmin, xmax, ymin, ymax = min(xs) - margen, max(xs) + margen, min(ys) - margen, max(ys) + margen
        k = px_por_m
        panel = ancho_panel
        W, H = int((xmax - xmin) * k) + panel, int((ymax - ymin) * k) + 90

        def X(x):
            return (x - xmin) * k

        def Y(y):
            return (ymax - y) * k + 60

        def esc(s):
            return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
               'font-family="Segoe UI, Arial, sans-serif">' % (W, H, W, H),
               '<rect width="100%" height="100%" fill="#ffffff"/>',
               '<defs><marker id="flecha" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" '
               'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#546e7a"/></marker>'
               '<pattern id="rackp" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
               '<rect width="6" height="6" fill="#bcaaa4"/><line x1="0" y1="0" x2="0" y2="6" stroke="#6d4c41" stroke-width="2"/>'
               '</pattern></defs>',
               '<text x="16" y="30" font-size="22" font-weight="600" fill="#212121">%s</text>' % esc(titulo),
               '<text x="16" y="50" font-size="13" fill="#555">%s</text>' % esc(subtitulo)]
        # suelos
        for (_, t, n, d) in self.visual:
            if t != "plane":
                continue
            x1, y1, x2, y2 = d["rect"]
            col = "rgb(%d,%d,%d)" % tuple(int(255 * c) for c in d["color"])
            out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" stroke="none"/>'
                       % (X(min(x1, x2)), Y(max(y1, y2)), abs(x2 - x1) * k, abs(y2 - y1) * k, col))
        # rótulos de zona (uno por grupo, en el rectángulo mayor)
        grupos = {}
        for (_, t, n, d) in self.visual:
            if t == "plane":
                x1, y1, x2, y2 = d["rect"]
                area = abs(x2 - x1) * abs(y2 - y1)
                g = d["grupo"]
                if g not in grupos or area > grupos[g][0]:
                    grupos[g] = (area, d)
        # racks y objetos
        for n, (cx, cy, sx, sy) in pos.items():
            c = self.clase_de(n) or ""
            if c.startswith(CONV_PREFIX):
                continue
            base = c.split("::")[-1]
            if base in TE_CLASSES[:3] or base == "Dispatcher":
                if not mostrar_recursos:
                    continue
                col = self.COLOR_CLASE.get(base, "#999")
                if base == "Dispatcher":
                    out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" stroke="#455a64" '
                               'stroke-width="1" transform="rotate(45 %.1f %.1f)"/>'
                               % (X(cx) - 4, Y(cy) - 4, 8, 8, col, X(cx), Y(cy)))
                else:
                    out.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" stroke="#263238" stroke-width="1"/>'
                               % (X(cx), Y(cy), max(3.5, sx * k / 2.2), col))
                continue
            if base == "Robot":
                out.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" stroke="#311b92" stroke-width="1.5"/>'
                           % (X(cx), Y(cy), sx * k / 2, self.COLOR_CLASE["Robot"]))
                out.append('<text x="%.1f" y="%.1f" font-size="9" text-anchor="middle" fill="#fff">R</text>'
                           % (X(cx), Y(cy) + 3))
                continue
            conectado = any(n in (a, b) for (a, b, _) in self.conns)
            if base == "Rack":
                out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="url(#rackp)" stroke="%s" '
                           'stroke-width="%s"/>' % (X(cx - sx / 2), Y(cy + sy / 2), sx * k, sy * k,
                                                    "#d84315" if conectado else "#5d4037", "2" if conectado else "0.8"))
                continue
            col = self.COLOR_CLASE.get(base, "#cfd8dc")
            out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="%s" stroke="#37474f" stroke-width="1"/>'
                       % (X(cx - sx / 2), Y(cy + sy / 2), sx * k, sy * k, col))
        # cintas
        for n, ((x1, y1), (x2, y2)) in cintas.items():
            out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#90a4ae" stroke-width="%.1f" '
                       'stroke-linecap="butt"/>' % (X(x1), Y(y1), X(x2), Y(y2), 0.9 * k))
            out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#546e7a" stroke-width="1.2" '
                       'marker-end="url(#flecha)"/>' % (X(x1), Y(y1), X(x2), Y(y2)))
        # paredes
        for (_, t, n, d) in self.visual:
            if t != "cube":
                continue
            x1, y1, x2, y2 = d["seg"]
            col, wid, dash = est.get(d["tipo"], est["interior"])
            out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="%.1f" '
                       'stroke-linecap="square"%s/>' % (X(x1), Y(y1), X(x2), Y(y2), col, wid * k,
                                                       ' stroke-dasharray="%s"' % ",".join(str(float(v) * k) for v in dash.split(",")) if dash else ""))
        # puertas y muelles
        for (tipo, d) in self.dibujo:
            if tipo == "puerta":
                x, y, a, o, lab = d
                if o == "h":
                    out.append('<path d="M%.1f,%.1f A%.1f,%.1f 0 0 1 %.1f,%.1f" fill="none" stroke="#424242" '
                               'stroke-width="1" stroke-dasharray="3,2"/>' % (X(x - a / 2), Y(y), a * k, a * k, X(x + a / 2), Y(y) - a * k))
                    out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#424242" stroke-width="1.5"/>'
                               % (X(x - a / 2), Y(y), X(x - a / 2), Y(y) - a * k))
                else:
                    out.append('<path d="M%.1f,%.1f A%.1f,%.1f 0 0 0 %.1f,%.1f" fill="none" stroke="#424242" '
                               'stroke-width="1" stroke-dasharray="3,2"/>' % (X(x), Y(y - a / 2), a * k, a * k, X(x) - a * k, Y(y + a / 2)))
                    out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#424242" stroke-width="1.5"/>'
                               % (X(x), Y(y - a / 2), X(x) - a * k, Y(y - a / 2)))
                if lab:
                    out.append('<text x="%.1f" y="%.1f" font-size="10" fill="#424242">%s</text>'
                               % (X(x) + 4, Y(y) - 4, esc(lab)))
            elif tipo == "muelle":
                x, y, a, lado, lab = d
                prof = 2.5
                if lado in ("oeste", "este"):
                    x0 = x - prof if lado == "oeste" else x
                    out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#eceff1" stroke="#455a64"/>'
                               % (X(x0), Y(y + a / 2), prof * k, a * k))
                    tx = X(x0) + (-4 if lado == "oeste" else prof * k + 4)
                    out.append('<text x="%.1f" y="%.1f" font-size="11" font-weight="600" fill="#37474f" '
                               'text-anchor="%s">%s</text>' % (tx, Y(y) + 4, "end" if lado == "oeste" else "start", esc(lab)))
                else:
                    y0 = y if lado == "norte" else y - prof
                    out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#eceff1" stroke="#455a64"/>'
                               % (X(x - a / 2), Y(y0 + prof), a * k, prof * k))
                    out.append('<text x="%.1f" y="%.1f" font-size="11" fill="#37474f" text-anchor="middle">%s</text>'
                               % (X(x), Y(y0 + prof) - 4 if lado == "norte" else Y(y0) + 14, esc(lab)))
            elif tipo == "texto":
                x, y, txt, tam, col = d
                out.append('<text x="%.1f" y="%.1f" font-size="%.1f" fill="%s" text-anchor="middle">%s</text>'
                           % (X(x), Y(y), tam * k, col, esc(txt)))
        # rótulos de zona encima de todo
        for g, (area, d) in grupos.items():
            x1, y1, x2, y2 = d["rect"]
            if d.get("etiqueta_en"):
                lx, ly = X(d["etiqueta_en"][0]), Y(d["etiqueta_en"][1])
            else:
                lx, ly = X((x1 + x2) / 2), Y(max(y1, y2)) + 18
            out.append('<text x="%.1f" y="%.1f" font-size="14" font-weight="700" fill="#263238" text-anchor="middle" '
                       'opacity="0.85">%s</text>' % (lx, ly, esc(d["etiqueta"])))
        # rótulos de objetos
        etiquetas = etiquetas or {}
        for n, (cx, cy, sx, sy) in pos.items():
            if n not in etiquetas:
                continue
            txt, donde = etiquetas[n] if isinstance(etiquetas[n], tuple) else (etiquetas[n], "arriba")
            tx, ty, anc = {"arriba": (X(cx), Y(cy + sy / 2) - 3, "middle"),
                           "abajo": (X(cx), Y(cy - sy / 2) + 11, "middle"),
                           "izquierda": (X(cx - sx / 2) - 3, Y(cy) + 3, "end"),
                           "derecha": (X(cx + sx / 2) + 3, Y(cy) + 3, "start")}[donde]
            out.append('<text x="%.1f" y="%.1f" font-size="9.5" fill="#212121" text-anchor="%s" '
                       'stroke="#ffffff" stroke-width="2.5" paint-order="stroke">%s</text>'
                       % (tx, ty, anc, esc(txt)))
        # cotas generales, norte y escala
        nav = [d["seg"] for (_, t, n, d) in self.visual if t == "cube" and d["tipo"] == "exterior"]
        if nav:
            ex1 = min(min(s[0], s[2]) for s in nav); ex2 = max(max(s[0], s[2]) for s in nav)
            ey1 = min(min(s[1], s[3]) for s in nav); ey2 = max(max(s[1], s[3]) for s in nav)
            yy = Y(ey1) + 3.6 * k
            out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#616161" stroke-width="1" '
                       'marker-start="url(#flecha)" marker-end="url(#flecha)"/>' % (X(ex1), yy, X(ex2), yy))
            out.append('<text x="%.1f" y="%.1f" font-size="12" text-anchor="middle" fill="#424242">%s m</text>'
                       % ((X(ex1) + X(ex2)) / 2, yy - 4, _num(ex2 - ex1)))
            xx = X(ex1) - 5.5 * k
            out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#616161" stroke-width="1" '
                       'marker-start="url(#flecha)" marker-end="url(#flecha)"/>' % (xx, Y(ey1), xx, Y(ey2)))
            out.append('<text x="%.1f" y="%.1f" font-size="12" text-anchor="middle" fill="#424242" '
                       'transform="rotate(-90 %.1f %.1f)">%s m</text>' % (xx - 5, (Y(ey1) + Y(ey2)) / 2, xx - 5,
                                                                        (Y(ey1) + Y(ey2)) / 2, _num(ey2 - ey1)))
        bx, by = X(xmax) - 12 * k, H - 22
        out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="5" fill="#212121"/>' % (bx, by, 5 * k))
        out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="5" fill="#fff" stroke="#212121"/>' % (bx + 5 * k, by, 5 * k))
        for d, lab in ((0, "0"), (5, "5"), (10, "10 m")):
            out.append('<text x="%.1f" y="%.1f" font-size="11" fill="#212121" text-anchor="middle">%s</text>'
                       % (bx + d * k, by - 4, lab))
        nx, ny = X(xmax) - 3 * k, 72
        out.append('<path d="M%.1f,%.1f l7,20 l-7,-6 l-7,6 z" fill="#212121"/><text x="%.1f" y="%.1f" font-size="13" '
                   'font-weight="700" text-anchor="middle">N</text>' % (nx, ny, nx, ny - 4))
        # panel derecho: leyenda, tabla, notas
        px, py = X(xmax) + 18, 80
        out.append('<rect x="%.1f" y="%d" width="%d" height="%d" fill="#fafafa" stroke="#cfd8dc"/>' % (px - 10, 62, panel - 24, H - 80))
        if tabla:
            out.append('<text x="%.1f" y="%d" font-size="14" font-weight="700">Superficies</text>' % (px, py)); py += 8
            for fila in tabla:
                py += 18
                col = fila[2] if len(fila) > 2 else None
                if col:
                    out.append('<rect x="%.1f" y="%d" width="12" height="12" fill="rgb(%d,%d,%d)" stroke="#90a4ae"/>'
                               % ((px, py - 10) + tuple(int(255 * c) for c in col)))
                out.append('<text x="%.1f" y="%d" font-size="12">%s</text>' % (px + 18, py, esc(fila[0])))
                out.append('<text x="%.1f" y="%d" font-size="12" text-anchor="end">%s</text>' % (px + panel - 40, py, esc(fila[1])))
            py += 16
        if leyenda:
            py += 10
            out.append('<text x="%.1f" y="%d" font-size="14" font-weight="700">Leyenda</text>' % (px, py)); py += 6
            for (simbolo, txt) in leyenda:
                py += 20
                tipo, val = simbolo
                if tipo == "muro":
                    col, wid, dash = est[val]
                    out.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s" stroke-width="%.1f"%s/>'
                               % (px, py - 4, px + 26, py - 4, col, max(2.5, wid * k * 0.6),
                                  ' stroke-dasharray="6,3"' if dash else ""))
                elif tipo == "clase":
                    out.append('<rect x="%.1f" y="%d" width="14" height="12" fill="%s" stroke="#37474f"/>'
                               % (px + 6, py - 10, self.COLOR_CLASE.get(val, "#ccc")))
                elif tipo == "rack":
                    out.append('<rect x="%.1f" y="%d" width="26" height="10" fill="url(#rackp)" stroke="%s" stroke-width="%s"/>'
                               % (px, py - 10, "#d84315" if val else "#5d4037", "2" if val else "0.8"))
                elif tipo == "cinta":
                    out.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="#90a4ae" stroke-width="7"/>'
                               % (px, py - 4, px + 26, py - 4))
                elif tipo == "circulo":
                    out.append('<circle cx="%.1f" cy="%d" r="6" fill="%s" stroke="#263238"/>'
                               % (px + 13, py - 4, self.COLOR_CLASE.get(val, "#999")))
                elif tipo == "puerta":
                    out.append('<path d="M%.1f,%d A12,12 0 0 1 %.1f,%d" fill="none" stroke="#424242" stroke-dasharray="3,2"/>'
                               % (px + 2, py, px + 14, py - 12))
                elif tipo == "muelle":
                    out.append('<rect x="%.1f" y="%d" width="20" height="12" fill="#eceff1" stroke="#455a64"/>' % (px + 3, py - 10))
                out.append('<text x="%.1f" y="%d" font-size="12">%s</text>' % (px + 34, py, esc(txt)))
        if notas:
            py += 26
            out.append('<text x="%.1f" y="%d" font-size="14" font-weight="700">Notas</text>' % (px, py))
            for linea in notas:
                for trozo in _trocear(linea, int((panel - 40) / 6.2)):
                    py += 16
                    out.append('<text x="%.1f" y="%d" font-size="11" fill="#424242">%s</text>' % (px, py, esc(trozo)))
                py += 4
        out.append("</svg>")
        io.open(ruta, "w", encoding="utf-8", newline="\n").write("\n".join(out))
        return ruta

    # ------------------------------------------------------------- PNG de fondo (sin texto)
    def png_fondo(self, ruta, px_por_m=10, margen=5, tamanos=None, rect=None):
        """Imagen sin rótulos para el Model Background de FlexSim. rect=(x1, y1, x2, y2) en
        metros fija el área (por defecto la de las paredes exteriores + margen). Devuelve el
        rectángulo cubierto, que es el que hay que dar al fondo en FlexSim."""
        pos, cintas = self.previsualizar(tamanos)
        if rect is None:
            segs = [d["seg"] for (_, t, n, d) in self.visual if t == "cube"] or [(0, 0, 10, 10)]
            rect = (min(min(s[0], s[2]) for s in segs) - margen, min(min(s[1], s[3]) for s in segs) - margen,
                    max(max(s[0], s[2]) for s in segs) + margen, max(max(s[1], s[3]) for s in segs) + margen)
        x0, y0, x1, y1 = rect
        k = px_por_m
        W, H = int(round((x1 - x0) * k)), int(round((y1 - y0) * k))
        buf = bytearray(b"\xff" * (W * H * 3))

        def fill(ax, ay, bx, by, col):
            ia, ib = sorted((int((ax - x0) * k), int((bx - x0) * k)))
            ja, jb = sorted((int((y1 - ay) * k), int((y1 - by) * k)))
            ia, ja, ib, jb = max(0, ia), max(0, ja), min(W, ib), min(H, jb)
            row = bytes(col) * max(0, ib - ia)
            for j in range(ja, jb):
                o = (j * W + ia) * 3
                buf[o:o + len(row)] = row

        def line(ax, ay, bx, by, wid, col):
            n = int(max(abs(bx - ax), abs(by - ay)) * k * 2) + 1
            h = wid / 2
            for i in range(n + 1):
                t = i / n
                x, y = ax + (bx - ax) * t, ay + (by - ay) * t
                fill(x - h, y - h, x + h, y + h, col)

        for (_, t, n, d) in self.visual:
            if t == "plane":
                a, b, c, e = d["rect"]
                fill(a, b, c, e, tuple(int(255 * v) for v in d["color"]))
        for n, (cx, cy, sx, sy) in pos.items():
            base = (self.clase_de(n) or "").split("::")[-1]
            if base == "Rack":
                fill(cx - sx / 2, cy - sy / 2, cx + sx / 2, cy + sy / 2, (141, 110, 99))
        for n, ((a, b), (c, e)) in cintas.items():
            line(a, b, c, e, 0.9, (144, 164, 174))
        for (_, t, n, d) in self.visual:
            if t == "cube":
                a, b, c, e = d["seg"]
                col = {"camara": (21, 101, 192), "cortafuegos": (198, 40, 40)}.get(d["tipo"], (34, 34, 34))
                line(a, b, c, e, max(0.3, d["grosor"]), col)
        raw = b"".join(b"\x00" + bytes(buf[j * W * 3:(j + 1) * W * 3]) for j in range(H))

        def chunk(tag, data):
            return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)

        png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
               + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
        io.open(ruta, "wb").write(png)
        return rect


def _trocear(texto, n):
    palabras, out, cur = texto.split(), [], ""
    for p in palabras:
        if len(cur) + len(p) + 1 > n and cur:
            out.append(cur)
            cur = p
        else:
            cur = (cur + " " + p).strip()
    if cur:
        out.append(cur)
    return out


if __name__ == "__main__":
    print(__doc__)
