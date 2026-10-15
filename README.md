# flexsim-modelado

Skill de Claude para construir modelos de [FlexSim](https://www.flexsim.com/) mediante scripts FlexScript
sin repetir errores ya diagnosticados, y para verificarlos ejecutándolos en FlexSim real con
[FlexSimPy](https://github.com/flexsim/FlexSimPy).

Cubre: crear, colocar, conectar y configurar objetos (Source, Queue, Processor, Rack, cintas, operarios,
carretillas, AMR, robots), suelos, paredes y muros A*, plano 2D coherente con la simulación,
automatización de escenarios y verificación/simulación headless.

## Contenido

| Ruta | Qué es |
|---|---|
| `SKILL.md` | Punto de entrada: cuándo se activa y flujo de trabajo |
| `references/api.md` | Comandos FlexScript verificados y su sintaxis |
| `references/patrones.md` | Patrones de construcción (orden, colocación, conexión, plano) |
| `references/errores.md` | Errores frecuentes, causa y arreglo |
| `references/automatizacion.md` | Generar escenas y datos por código |
| `references/flexsimpy.md` | Compilar y usar FlexSimPy; ejecutar scripts en FlexSim real |
| `scripts/check_script.py` | Linter estático de scripts FlexScript |
| `scripts/flexsim_check.py` | Ejecuta un script en FlexSim real, comprueba bloques, propiedades, posiciones y A* |
| `scripts/generar_escena.py` | Generador de escenas con plano 2D (SVG) |
| `scripts/flexhelp.py` | Consulta la documentación oficial de comandos |
| `scripts/prueba_humo.py`, `scripts/replicas.py` | Prueba de humo y réplicas con FlexSimPy |

## Instalación

Empaqueta la carpeta como `.skill` (un zip con `SKILL.md` en la raíz de `flexsim-modelado/`) y súbela en
Ajustes → Capacidades → Skills, o cópiala a `~/.claude/skills/flexsim-modelado/` para Claude Code.

## Requisitos opcionales

Python 3 y FlexSim instalado (para `flexsim_check.py`, `prueba_humo.py` y `replicas.py`, que usan FlexSimPy;
ver `references/flexsimpy.md`). El resto funciona sin FlexSim.

## Licencia

[MIT](LICENSE).

## Créditos y licencias de terceros

- **[FlexSimPy](https://github.com/flexsim/FlexSimPy)** — © 2022 FlexSim Software Products Inc., licencia MIT.
  Este repositorio **no incluye** su código: `scripts/flexsim_check.py` lo importa en ejecución desde la
  carpeta donde cada usuario lo haya compilado (ver `references/flexsimpy.md`).
- **FlexSim** y su SDK (cabeceras y librerías necesarias para compilar FlexSimPy) son software propietario de
  FlexSim Software Products Inc. / Autodesk. No se incluyen ni se redistribuyen; hace falta una instalación
  de FlexSim con licencia propia para usar los scripts que lo ejecutan.
- La documentación oficial de FlexSim es propiedad de sus autores; esta skill solo la consulta
  (`scripts/flexhelp.py`) y resume comandos y sintaxis con palabras propias.
- Proyecto independiente, sin afiliación ni respaldo de FlexSim ni de Autodesk. FlexSim es marca de sus titulares.
