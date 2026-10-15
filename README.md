# flexsim-modelado

> *Claude skill for building and verifying FlexSim models via FlexScript. Documentation and prompts are in Spanish; not tested in English.*

Skill de Claude para construir modelos de [FlexSim](https://www.flexsim.com/) mediante scripts FlexScript
sin repetir errores ya diagnosticados, y para verificarlos ejecutándolos en FlexSim real con
[FlexSimPy](https://github.com/flexsim/FlexSimPy).

Cubre: crear, colocar, conectar y configurar objetos (Source, Queue, Processor, Rack, cintas, operarios,
carretillas, AMR, robots), suelos, paredes y muros A*, plano 2D coherente con la simulación,
automatización de escenarios y verificación/simulación headless.

## Contenido

| Ruta | Qué es |
|---|---|
| `skills/flexsim-modelado/SKILL.md` | Punto de entrada: cuándo se activa y flujo de trabajo |
| `skills/flexsim-modelado/references/api.md` | Comandos FlexScript verificados y su sintaxis |
| `skills/flexsim-modelado/references/patrones.md` | Patrones de construcción (orden, colocación, conexión, plano) |
| `skills/flexsim-modelado/references/errores.md` | Errores frecuentes, causa y arreglo |
| `skills/flexsim-modelado/references/automatizacion.md` | Generar escenas y datos por código |
| `skills/flexsim-modelado/references/flexsimpy.md` | Compilar y usar FlexSimPy; ejecutar scripts en FlexSim real |
| `skills/flexsim-modelado/scripts/check_script.py` | Linter estático de scripts FlexScript |
| `skills/flexsim-modelado/scripts/flexsim_check.py` | Ejecuta un script en FlexSim real, comprueba bloques, propiedades, posiciones y A* |
| `skills/flexsim-modelado/scripts/generar_escena.py` | Generador de escenas con plano 2D (SVG) |
| `skills/flexsim-modelado/scripts/flexhelp.py` | Consulta la documentación oficial de comandos |
| `skills/flexsim-modelado/scripts/prueba_humo.py`, `replicas.py` | Prueba de humo y réplicas con FlexSimPy |
| `.claude-plugin/` | Manifiestos de plugin y de marketplace |
| `tools/empaquetar.py` | Genera `dist/flexsim-modelado.skill` |

## Instalación

**Claude Code (plugin):**

```
/plugin marketplace add carmoran0/flexsim-modelado
/plugin install flexsim-modelado@flexsim-modelado
```

**claude.ai:** ejecuta `python tools/empaquetar.py` y sube `dist/flexsim-modelado.skill` en
Ajustes → Capacidades → Skills (o descárgalo de la sección Releases).

**Manual:** copia `skills/flexsim-modelado/` a `~/.claude/skills/`.

## Requisitos opcionales

Python 3 y FlexSim instalado (para `flexsim_check.py`, `prueba_humo.py` y `replicas.py`, que usan FlexSimPy;
ver `skills/flexsim-modelado/references/flexsimpy.md`). El resto funciona sin FlexSim.

## Verificación rápida

Sin FlexSim (solo análisis estático, cualquier SO):

```bash
python skills/flexsim-modelado/scripts/check_script.py mi_escena.flexscript
```

Con FlexSim 2027 en Windows y FlexSimPy compilado (`skills/flexsim-modelado/references/flexsimpy.md`):

```bash
set FLEXSIMPY_DIR=C:/ruta/FlexSimPy/out/Rel_3_12
set FLEXSIM_BASE_MODEL=C:/ruta/FlexSimPy/TestFlexSimPy/PostOfficeModel.fsm
py -3.12 skills/flexsim-modelado/scripts/prueba_humo.py
```

La prueba de humo (~30 s) construye una escena mínima, la simula y comprueba comportamiento
(operarios, FEFO, semillas, vigilante de interbloqueos). Probada desde un clon limpio con FlexSim 2027.

## Licencia

[MIT](LICENSE).

## Créditos y licencias de terceros

- **[FlexSimPy](https://github.com/flexsim/FlexSimPy)** — © 2022 FlexSim Software Products Inc., licencia MIT.
  Este repositorio **no incluye** su código: `skills/flexsim-modelado/scripts/flexsim_check.py` lo importa en ejecución desde la
  carpeta donde cada usuario lo haya compilado (ver `skills/flexsim-modelado/references/flexsimpy.md`).
- **FlexSim** y su SDK (cabeceras y librerías necesarias para compilar FlexSimPy) son software propietario de
  FlexSim Software Products Inc. / Autodesk. No se incluyen ni se redistribuyen; hace falta una instalación
  de FlexSim con licencia propia para usar los scripts que lo ejecutan.
- La documentación oficial de FlexSim es propiedad de sus autores; esta skill solo la consulta
  (`flexhelp.py`) y resume comandos y sintaxis con palabras propias.
- Proyecto independiente, sin afiliación ni respaldo de FlexSim ni de Autodesk. FlexSim es marca de sus titulares.
