#!/usr/bin/env python3
"""Consulta comandos globales en la ayuda XML instalada de FlexSim.

Uso:
    python flexhelp.py contextdragconnection Object.create model find
    python flexhelp.py --xml "D:\\ruta\\Commands.xml" labels

La ruta por defecto es la de FlexSim 2027; se puede cambiar con --xml o con la
variable de entorno FLEXSIM_HELP_XML (útil si hay otra versión o el XML se copió
a otro sitio).

Códigos de salida: 0 todo encontrado, 1 algún comando no existe, 2 no hay ayuda.
Si sale 2, la API consultada queda SIN VERIFICAR y así hay que reportarla.
"""
import difflib
import io
import os
import re
import sys

DEFAULT = r"C:\Program Files\Autodesk\FlexSim 2027\help\CommandReference\Commands.xml"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
except AttributeError:
    pass


def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


def main(argv):
    path = os.environ.get("FLEXSIM_HELP_XML", DEFAULT)
    if "--xml" in argv:
        i = argv.index("--xml")
        if i + 1 >= len(argv):
            print("Falta la ruta de --xml")
            return 2
        path = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if not argv:
        print(__doc__)
        return 0
    if not os.path.isfile(path):
        print("NO HAY AYUDA: no existe %s" % path)
        print("Marca como SIN VERIFICAR toda API que no esté en references/api.md,")
        print("o pide al usuario que ejecute este script en su máquina y pegue el resultado.")
        return 2

    t = io.open(path, encoding="utf-8").read()
    names = re.findall(r"<command>\s*<name>(.*?)</name>", t)
    missing = 0
    for want in argv:
        m = re.search(r"<command>\s*<name>" + re.escape(want) + r"</name>(.*?)</command>", t, re.S)
        if not m:
            missing += 1
            close = difflib.get_close_matches(want, names, n=3, cutoff=0.6)
            print("###", want, "NO EXISTE como comando global" +
                  ("  (¿quizá: %s?)" % ", ".join(close) if close else ""))
            print("   Si es un método de clase (Object.create, treenode.find...), "
                  "mira FlexScriptAPIReference\\Tree\\*.xml")
            print()
            continue
        blk = m.group(1)

        def g(tag):
            mm = re.search(r"<" + tag + r">(.*?)</" + tag + r">", blk, re.S)
            return clean(mm.group(1)) if mm else ""

        print("###", want)
        print("  params :", g("parameters"), "  (entre [corchetes] = opcional; el resto es OBLIGATORIO)")
        print("  short  :", g("shortdescription"))
        print("  return :", g("returntype"))
        print("  desc   :", g("description")[:400])
        print("  example:", g("example"))
        print()
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
