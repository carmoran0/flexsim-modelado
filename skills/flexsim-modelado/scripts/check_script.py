#!/usr/bin/env python3
"""Comprobaciones estáticas sobre un script FlexScript de construcción de escena.

Uso:
    python check_script.py escena.txt
    python check_script.py escena.txt --existing Fresadora1,Salida

--existing: nombres de objetos que ya están en el modelo (modo "modificar") y que
            el script puede localizar con model().find() sin haberlos creado él.

Salida: una línea PASS / WARN / FAIL por comprobación. Código de salida 1 si hay FAIL.
Esto es análisis de texto: no sustituye a ejecutar el script en FlexSim.
"""
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except AttributeError:
    pass

INVENTED = ["Model.addNode", "Model.connect", "Model.save", "Model.build", "addNode"]
DEPRECATED = {
    "connect": "contextdragconnection()",
    "objectconnect": "contextdragconnection()",
    "defaultdragconnection": "contextdragconnection()",
    "node": "model().find()",
    "nodetomodelpath": "treenode.getPath()",
    "anode": "tonode()",
    "addlabel": "treenode.labels.assert()",
    "nodeinsertinto": "treenode.subnodes.add()",
    "createinstance": "Object.create()",
    "nodeadddata": "treenode.value / treenode.dataType",
}
BLOCK_MARK = "\x00"
# Cabecera de bloque "/* BLOQUE 3 - Conectar */": admite espacios de más, minúsculas y cualquier
# separador (-, —, :). flexsim_check.py parte el script con la misma (partir_bloques).
INICIO_BLOQUE = re.compile(r"/\*\s*BLOQUE\s*(\d+)", re.I)
# Nombres que no se pueden declarar como variable (medido en FlexSim 2027, 13/10/2026)
RESERVADOS = ["break", "case", "continue", "default", "else", "eq", "for", "forobjectlayerunder",
              "forobjectsbefore", "forobjectsbehind", "forobjecttreeunder", "if", "inheritcode", "iterate",
              "local", "localarray", "msgparam", "msgsendingobject", "ne", "param", "parnode", "parqty",
              "parstr", "parval", "return", "setcurrent", "setitem", "setport", "switch", "while"]
TYPES = r"(?:treenode|double|int|string|void|Object|Variant|Array|Map|bool|num|obj|str)"


def strip(text):
    """Devuelve (code, code_sin_strings): sin comentarios; el 2.º además con strings vaciados.
    Respeta que '//' dentro de un string no es comentario."""
    code, blank = [], []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j == -1 else j + 2
            seg = text[i:j]
            keep = "\n" * seg.count("\n")          # conserva las líneas
            if INICIO_BLOQUE.match(seg):
                keep = BLOCK_MARK + keep            # marca dónde empieza cada bloque
            code.append(keep); blank.append(keep); i = j
        elif text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j == -1 else j
            i = j
        elif c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            j = min(j + 1, n)
            code.append(text[i:j]); blank.append('""'); i = j
        else:
            code.append(c); blank.append(c); i += 1
    return "".join(code), "".join(blank)


def partir_bloques(text):
    """[(número, texto)] de cada bloque, desde su cabecera hasta la siguiente."""
    cab = list(INICIO_BLOQUE.finditer(text))
    fin = [m.start() for m in cab[1:]] + [len(text)]
    return [(int(m.group(1)), text[m.start():f]) for m, f in zip(cab, fin)]


def call_args(code, start):
    """Dado el índice del '(' de una llamada, devuelve la lista de argumentos de nivel superior."""
    depth, args, cur, i, n = 0, [], [], start, len(code)
    while i < n:
        c = code[i]
        if c == '"':
            j = i + 1
            while j < n and code[j] != '"':
                j += 2 if code[j] == "\\" else 1
            cur.append(code[i:j + 1]); i = j + 1; continue
        if c in "([{":
            depth += 1
            if depth > 1:
                cur.append(c)
        elif c in ")]}":
            depth -= 1
            if depth == 0:
                tail = "".join(cur).strip()
                if tail or args:
                    args.append(tail)
                return args
            cur.append(c)
        elif c == "," and depth == 1:
            args.append("".join(cur).strip()); cur = []
        else:
            cur.append(c)
        i += 1
    return None  # paréntesis sin cerrar


def line_of(code, pos):
    return code.count("\n", 0, pos) + 1


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 0
    existing = set()
    if "--existing" in argv:
        i = argv.index("--existing")
        if i + 1 >= len(argv):
            print("Falta la lista de --existing (p. ej. --existing Fresadora1,Salida)"); return 2
        existing = {s.strip() for s in argv[i + 1].split(",") if s.strip()}
        argv = argv[:i] + argv[i + 2:]
    if not argv:
        print(__doc__); return 2
    path = argv[0]
    try:
        raw = open(path, encoding="utf-8-sig").read()   # -sig: un BOM no cuenta como carácter no ASCII
    except OSError as e:
        print("No se puede leer %s: %s" % (path, e)); return 2
    code, blank = strip(raw)
    results = []   # (nivel, titulo, detalle)

    def add(level, title, detail=""):
        results.append((level, title, detail))

    # 1. API inventada
    hits = [(k, len(re.findall(re.escape(k), code))) for k in INVENTED]
    hits = [(k, c) for k, c in hits if c]
    if hits:
        add("FAIL", "1. API inventada", "; ".join("%s x%d" % h for h in hits))
    else:
        add("PASS", "1. API inventada", "ninguna (fuera de comentarios)")

    # 1b. Obsoletos
    dep = []
    for name, repl in DEPRECATED.items():
        for m in re.finditer(r"(?<![\w.])" + name + r"\s*\(", blank):
            if name == "createinstance" and re.match(r"createinstance\s*\(\s*library\(\)\.find", blank[m.start():m.start() + 60]):
                continue   # vía legítima para clases que Object.create no crea (p. ej. AStarNavigator)
            dep.append("línea %d: %s() -> %s" % (line_of(blank, m.start()), name, repl))
    if dep:
        add("WARN", "1b. Comandos obsoletos", " | ".join(dep))

    # 2. Aridad de contextdragconnection
    bad, total = [], 0
    for m in re.finditer(r"contextdragconnection\s*\(", code):
        total += 1
        args = call_args(code, m.end() - 1)
        ln = line_of(code, m.start())
        if args is None:
            bad.append("línea %d: paréntesis sin cerrar" % ln)
        elif len(args) != 3:
            bad.append("línea %d: %d argumentos (deben ser 3)" % (ln, len(args)))
        elif args[2] not in ('"A"', '"S"', '"D"', '"Q"', '"W"', '"E"'):
            bad.append("línea %d: 3.er argumento %s (A/S/D conectan, Q/W/E desconectan)" % (ln, args[2]))
    if bad:
        add("FAIL", "2. Aridad de conexiones", " | ".join(bad))
    else:
        add("PASS", "2. Aridad de conexiones", "%d llamada(s) correctas" % total)

    # 3. find() -> nombre creado antes (o declarado como existente)
    created = [(m.group(1), m.start()) for m in re.finditer(r"\.name\s*=\s*\"([^\"]+)\"", code)]
    # createinstance(library().find("?Clase"), model()) crea un objeto llamado como la clase
    created += [(m.group(1), m.start()) for m in
                re.finditer(r"createinstance\s*\(\s*library\(\)\.find\(\s*\"\?(\w+)\"", code)]
    first_created = {}
    for nm, pos in created:
        first_created.setdefault(nm, pos)
    broken = []
    for m in re.finditer(r"\.find\s*\(\s*\"([^\"]+)\"", code):
        if code[max(0, m.start() - 9):m.start()] == "library()":
            continue   # búsqueda en la librería, no en el modelo
        ref = m.group(1)
        if ref.startswith(">"):
            continue   # árbol de atributos del propio objeto (p. ej. ">variables"), no un nombre
        leaf = ref.split("/")[-1]
        if ref in existing or leaf in existing:
            continue
        if leaf not in first_created:
            broken.append("línea %d: find(\"%s\") nunca creado con .name" % (line_of(code, m.start()), ref))
        elif first_created[leaf] > m.start():
            blk = code.count(BLOCK_MARK, 0, m.start())
            same_block = blk > 0 and blk == code.count(BLOCK_MARK, 0, first_created[leaf])
            if not same_block:   # mismo bloque = patrón "buscar y crear si no existe"
                broken.append("línea %d: find(\"%s\") se usa antes de crearse" % (line_of(code, m.start()), ref))
    if broken:
        add("FAIL", "3. Referencias por nombre", " | ".join(broken) +
            "  (si ya existe en el modelo, pásalo en --existing)")
    else:
        add("PASS", "3. Referencias por nombre", "todas resueltas")

    # 4. Nombres duplicados
    seen, dups = {}, []
    for nm, pos in created:
        seen[nm] = seen.get(nm, 0) + 1
    dups = ["%s x%d" % (k, v) for k, v in seen.items() if v > 1]
    clash = sorted(k for k in seen if k in existing)
    dups += ["%s (ya existe en el modelo)" % k for k in clash]
    add("FAIL" if dups else "PASS", "4. Nombres duplicados", ", ".join(dups) if dups else "ninguno")

    # 5. Balance de delimitadores
    probs = []
    for o, c in ("()", "[]", "{}"):
        if blank.count(o) != blank.count(c):
            probs.append("%s%s: %d vs %d" % (o, c, blank.count(o), blank.count(c)))
    add("FAIL" if probs else "PASS", "5. Balance de (), [], {}", ", ".join(probs) if probs else "equilibrado")

    # 6. Funciones propias
    funcs = [("línea %d: %s" % (line_of(blank, m.start()), m.group(0).strip()))
             for m in re.finditer(r"^[ \t]*" + TYPES + r"[ \t]+\w+[ \t]*\([^)\n]*\)[ \t]*\{", blank, re.M)]
    funcs += [("línea %d: %s" % (line_of(blank, m.start()), m.group(0).strip()))
              for m in re.finditer(r"^[ \t]*function\b[^\n]*", blank, re.M)]
    add("FAIL" if funcs else "PASS", "6. Funciones propias", " | ".join(funcs) if funcs else "ninguna")

    # 7. Guardado
    save_calls = [m.group(0) for m in re.finditer(r"(?<![\w.])(cmdsaveas|savetree|savemodel)\s*\(", blank)]
    doc_ok = bool(re.search(r"Ctrl\s*\+\s*S", raw, re.I)) or "savebyname" in raw
    if save_calls:
        add("WARN", "7. Guardado", "el script llama %s (abre un diálogo; sin diálogo: savebyname(model(), ruta))" % ", ".join(save_calls))
    if not doc_ok:
        add("FAIL", "7. Guardado documentado", "falta la nota de guardado (Ctrl+S o savebyname(model(), ruta))")
    else:
        add("PASS", "7. Guardado documentado", "nota de Ctrl+S presente")

    # 8. Bloques: variables locales usadas fuera del bloque donde se declararon
    # Los encabezados de bloque son comentarios: se separan sobre el texto original
    partes = [strip(p) for _, p in partir_bloques(raw)]
    blocks = [c for c, _ in partes]
    if len(blocks) > 1:
        decl = []   # (var, idx)
        for idx, b in enumerate(blocks):
            for m in re.finditer(r"\b" + TYPES + r"\s+(\w+)\s*=", b):
                decl.append((m.group(1), idx))
        leaks = []
        # Identificadores de cada bloque, una sola pasada (antes: una búsqueda por variable y bloque,
        # 4 de los 5 s del linter en una escena de 250 conexiones)
        usados = [set(re.findall(r"(?<![\w.\"])(\w+)\b(?!\s*\")", b)) for _, b in partes]
        propias = set(decl)
        for var, di in sorted(propias, key=lambda d: d[1]):
            for idx, u in enumerate(usados):
                if idx != di and (var, idx) not in propias and var in u:
                    leaks.append("'%s' (declarada en bloque %d, usada en bloque %d)" % (var, di + 1, idx + 1))
        add("WARN" if leaks else "PASS", "8. Bloques independientes",
            " | ".join(sorted(set(leaks))) if leaks else "%d bloques, sin variables compartidas" % len(blocks))
    else:
        add("WARN", "8. Bloques independientes", "no hay bloques '/* BLOQUE N - ... */' (o solo hay uno)")

    # 9. Cintas conectadas antes de colocarlas (EntryTransfer fuera de sitio, errores.md #12)
    conv_names = set()
    for m in re.finditer(r"(\w+)\s*=\s*Object\.create\(\s*\"Conveyor::[^\"]+\"\s*\)\s*;\s*\1\.name\s*=\s*\"([^\"]+)\"", code):
        conv_names.add(m.group(2))
    var_of = {}
    for m in re.finditer(r"(\w+)\s*=\s*model\(\)\.find\(\s*\"([^\"]+)\"\s*\)", code):
        var_of.setdefault(m.group(2), set()).add(m.group(1))
    for m in re.finditer(r"(\w+)\s*=\s*Object\.create\(\s*\"Conveyor::[^\"]+\"\s*\)\s*;\s*\1\.name\s*=\s*\"([^\"]+)\"", code):
        var_of.setdefault(m.group(2), set()).add(m.group(1))
    early = []
    if conv_names and "StartLocation" in code:
        for nm in sorted(conv_names):
            vs = var_of.get(nm, set())
            pats = [r"\.find\(\s*\"%s\"\s*\)" % re.escape(nm)] + [r"\b%s\b" % re.escape(v) for v in vs]
            first_conn = None
            for m in re.finditer(r"contextdragconnection\s*\(", code):
                args = call_args(code, m.end() - 1) or []
                if any(re.search(pt, a) for a in args[:2] for pt in pats):
                    first_conn = m.start(); break
            first_place = None
            for m in re.finditer(r"(\w+)\.as\(Object\)\.setProperty\(\s*\"StartLocation\"", code):
                if m.group(1) in vs:
                    first_place = m.start(); break
            if first_conn is not None and (first_place is None or first_conn < first_place):
                early.append(nm)
    if early:
        add("WARN", "9. Cintas conectadas antes de colocarlas",
            ", ".join(early) + " — las transferencias se crean al conectar y no siguen a la cinta: "
            "coloca (StartLocation/EndLocation) y conecta después")
    elif conv_names:
        add("PASS", "9. Cintas conectadas antes de colocarlas", "orden crear -> colocar -> conectar respetado")

    # 10. Variables con nombre reservado: FlexScript no compila y, dentro de un campo Code o de un
    # trigger, el fallo es silencioso (el código no se ejecuta). Lista MEDIDA en FlexSim 2027
    # declarando "int <comando> = 1;" para los 1.214 comandos de Commands.xml.
    texto = code.replace('\\"', '"')    # sin comentarios, pero también dentro de las cadenas de código
    malos = []
    for m in re.finditer(r"\b%s\s+(%s)\s*(?:=|;|,)" % (TYPES, "|".join(RESERVADOS)), texto):
        malos.append("línea %d: '%s'" % (texto.count("\n", 0, m.start()) + 1, m.group(1)))
    if malos:
        add("FAIL", "10. Variables con nombre de comando", " | ".join(sorted(set(malos))[:12]) +
            " — FlexScript no lo compila (en un Code/trigger falla sin avisar): renómbrala")
    else:
        add("PASS", "10. Variables con nombre de comando", "ninguna")

    # 11. Caracteres no ASCII fuera de cadenas y comentarios: FlexScript no compila un identificador
    # con tildes (medido: «treenode tCámara = model();» no compila; «"Cámara"» en una cadena sí)
    noascii = [i for i, ln in enumerate(blank.split("\n"), 1) if not ln.isascii()]
    if noascii:
        add("FAIL", "11. Caracteres no ASCII en el código", "líneas %s — FlexScript no compila identificadores "
            "con tildes o ñ: quítalas del nombre de la variable (en cadenas sí valen)" % noascii[:12])
    else:
        add("PASS", "11. Caracteres no ASCII en el código", "ninguno fuera de cadenas y comentarios")

    # Extra: location como string
    locstr = [line_of(code, m.start()) for m in re.finditer(r"\.location\s*=\s*\"", code)]
    if locstr:
        add("WARN", "Extra. location como string", "líneas %s: usa .location.x / .location.y" % locstr)

    marks = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]"}
    for level, title, detail in results:
        print("%s %s%s" % (marks[level], title, (" — " + detail) if detail else ""))
    fails = sum(1 for r in results if r[0] == "FAIL")
    warns = sum(1 for r in results if r[0] == "WARN")
    print("\nResumen: %d FAIL, %d WARN. (Análisis estático; no se ha ejecutado FlexSim.)" % (fails, warns))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
