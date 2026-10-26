# Verificar en FlexSim real con FlexSimPy

Con FlexSimPy puedes **ejecutar tú mismo** los scripts en FlexSim (sin interfaz), comprobar el
resultado y simular, en lugar de entregar «sin ejecutar». Todo lo de esta página se probó el
13/10/2026 con FlexSim 2027, Python 3.12 y Visual Studio 2022 Build Tools.

## Índice
1. Qué es y qué no es
2. Compilarlo (una vez)
3. El truco para ejecutar FlexScript
4. `scripts/flexsim_check.py`
5. Comportamientos medidos (importantes)
6. Guardar el modelo sin diálogo
7. Experimentos: barridos de escenarios y KPIs
8. Semillas y réplicas
9. Vigilante y prueba de humo

---

## 1. Qué es y qué no es

- **Es**: un módulo de Python (`FlexSimPy.pyd`, en github.com/flexsim/FlexSimPy) que arranca
  FlexSim dentro del proceso de Python y lo controla.
  - Funciones: `launch(showGUI=False, programDir=...)`, `open(ruta)`, `reset()`, `run()`,
    `runToTime(t)` (bloqueante), `stop()`, `time()`, `getParameter`/`setParameter`,
    `getPerformanceMeasure`, `evaluate`, `send`/`receive`.
- **No es** un intérprete de FlexScript. **`Controller.evaluate(ruta, *args)` evalúa el NODO del
  árbol que hay en esa ruta** (`Model::find(ruta)->evaluate(args)`). Si le pasas texto
  FlexScript, no encuentra el nodo y devuelve `None` sin avisar. Por eso, en el pasado,
  `evaluate()` parecía «no hacer nada». Un proyecto de terceros (`mcp_flexsim`) cometía el
  mismo error.
- La instalación de FlexSim trae `PyConnector`, que es la dirección contraria (FlexSim llamando
  a Python). No sirve para esto.
- No hay versiones publicadas: hay que compilarlo para la versión de Python exacta (3.9–3.12).

## 2. Compilarlo (una vez)

Requisitos: Visual Studio 2022 (o sus Build Tools) con C++ (toolset v143), Python 3.12 (también
vale el de la Microsoft Store) y FlexSim instalado.

```bash
git clone --depth 1 https://github.com/flexsim/FlexSimPy.git
cd FlexSimPy
mkdir flexsimcontent
cp "C:/Program Files/Autodesk/FlexSim 2027/program/system/include/"*.h flexsimcontent/
cp "C:/Program Files/Autodesk/FlexSim 2027/program/system/include/"*.cpp flexsimcontent/
cp "C:/Program Files/Autodesk/FlexSim 2027/program/system/include/flexsimcontent.lib" flexsimcontent/
cp "C:/Program Files/Autodesk/FlexSim 2027/program/system/lib/flexsim.lib" flexsimcontent/
"C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/MSBuild/Current/Bin/MSBuild.exe" \
   FlexSimPy/FlexSimPy.vcxproj /p:Platform=x64 /p:Configuration=Rel_3_12 /p:SolutionDir=<ruta>/FlexSimPy/
# -> out/Rel_3_12/FlexSimPy.pyd
```

- **Compila solo `FlexSimPy.vcxproj`.** La solución completa también compila `PyConnector`, cuyo
  paso previo `copyheaders.bat` espera estar dentro del árbol de FlexSim y falla. Ese paso es
  justo la copia de cabeceras que se hace a mano arriba.
- El repo trae sus propias cabeceras y librerías de Python (`python/3.12/...`), así que no hacen
  falta las de tu Python.
- Uso: `py -3.12 script.py`, con la carpeta de `FlexSimPy.pyd` en `sys.path`.
- Al salir, FlexSim imprime `Invalid host context handle marker: 0x...`. Es inofensivo.

## 3. El truco para ejecutar FlexScript

1. **Modelo base mínimo en XML (.fsx)**, con dos nodos FlexScript en `Tools`:

   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <flexsim-tree version="4" treetype="model">
   <node f="10000043" dt="4"><name>model</name><data>
    <node f="40"><name></name></node>
   </data>
    <node f="40"><name></name></node>
    <node f="43"><name>Tools</name>
     <node f="40"><name></name></node>
     <node f="442" dt="2"><name>Exec</name><data>return executestring(param(1));</data></node>
     <node f="442" dt="2"><name>RunFS</name><data>return executefsfile(param(1), 1);</data></node>
    </node>
   </node>
   </flexsim-tree>
   ```

   - `treetype="model"`, raíz `model` con `f="10000043" dt="4"` y el primer hijo
     `<node f="40"><name></name></node>`.
   - `f="442" dt="2"` = nodo de texto con FlexScript activado.
   - Un .fsx sin esa estructura (p. ej. `treetype="tree"`) se abre, pero el nodo no se encuentra.
2. `c.open(boot.fsx)` y luego `c.evaluate("Tools/Exec", "return 2*21;")` → `42.0`.
3. **Nodo fuera del modelo**: `createcopy(model().find("Tools/Exec"), model().up, 1)` lo copia a
   `MAIN:/project`. Así sobrevive a abrir otro modelo, y se llama con
   `c.evaluate("../ClaudeExec", codigo)`, porque las rutas `..` funcionan.
4. **Modelo base real para simular.** El .fsx mínimo no tiene `Tools/FlowItemBin`, así que los
   Source no crean items y la simulación termina sin hacer nada. Abre un .fsm real (sirve
   `TestFlexSimPy/PostOfficeModel.fsm` del propio repo), destruye sus objetos (conserva Tools y
   `FlexsimModelFloor`) y construye encima.

**Resultado de cada bloque.** Añade al final `return "OK";` y ejecútalo con `Exec`:

| Devuelve | Significa |
|---|---|
| `"OK"` | el bloque terminó |
| `None` | excepción en ejecución (p. ej. `.as(Object)` sobre NULL, clase inexistente en `Object.create`) |
| `0.0` | no compila (sintaxis, comando desconocido como `Model.build`) |

FlexScript **no tiene try/catch** (no compila), y el texto del error no llega a Python. Para
localizar la línea que falla, ejecuta prefijos crecientes del bloque (`--localizar`).

## 4. `scripts/flexsim_check.py`

```bash
py -3.12 scripts/flexsim_check.py escena.flexscript --fspy <carpeta con FlexSimPy.pyd> \
   --base <modelo.fsm real> [--saltar "layout B"] [--posiciones escena_posiciones.json] \
   [--correr 86400] [--semilla 1] [--vigilar 3600 [--parada 14400]] [--recorridos 2 --desde 21600]
   [--guardar modelo.fsm]
   [--json informe.json] [--localizar] [--consulta "FlexScript"]
```

Hace, en orden:
1. Ejecuta los bloques uno a uno y da el estado de cada uno (OK / EXCEPCION / NO COMPILA /
   SALTADO).
2. Hace inventario por clase (`getProperty("Class")`).
3. Revisa cada `setProperty` del script con `getProperty`: si devuelve `None`, el nombre de la
   propiedad no existe.
4. Compara las posiciones previstas por `generar_escena.py` (`<prefijo>_posiciones.json`) con
   las reales: centros y extremos de cintas, con tolerancia de 0,3 m.
5. Cuenta los Divider dentro de `AStarNavigator` y sus viajeros.
6. Guarda con `savebyname`.
7. Hace reset (y siembra con `--semilla`) y `runToTime`, y saca entradas, salidas y contenido
   de cada objeto de flujo. Con `--vigilar N` simula a trozos de N s y avisa de interbloqueos,
   atascos y colas que crecen (§9); una alarma cuenta como fallo.

Termina con «Resultado: OK» o «Resultado: N fallos», y `--json` guarda el total en `fallos`
(bloques que fallan o ninguno encontrado, Code que no compilan, propiedades inexistentes, alarmas,
cruces de recorridos). **No uses el código de salida**: al cerrar FlexSim el proceso acaba con un
*segmentation fault* (139 en bash) aunque todo haya ido bien.

Las variables `FLEXSIMPY_DIR`, `FLEXSIM_BASE_MODEL` y `FLEXSIM_PROGRAM` (carpeta `program` de
FlexSim, si no está en la ruta por defecto) evitan repetir `--fspy`, `--base` y `--programa`. FlexSim
cambia el directorio de trabajo al arrancar, así que la herramienta pasa todas las rutas a
absolutas antes de lanzarlo.

Ciclo recomendado: generar → `check_script.py` (estático) → `flexsim_check.py` (real) →
corregir la **causa** en el generador → repetir. Entrega el .fsm guardado además del script.

## 5. Comportamientos medidos (importantes)

- **`Object.create("AStar::AStarNavigator")` no crea el navegador**: devuelve otro nodo (en la
  prueba, la `SystemConsole` de la vista). Si lo renombras y metes muros dentro, los muros
  acaban en el interfaz y A\* no tiene ninguno. Créalo como el propio módulo:
  `createinstance(library().find("?AStarNavigator"), model())`, y comprueba
  `getProperty("Class") == "AStar::AStarNavigator"`. `Object.create("AStar::Divider")` sí
  funciona.
- **`setProperty` con un nombre inexistente no da error**: no hace nada. Verifícalo con
  `getProperty`.
- **Texto con tildes a través de `evaluate()`**: FlexSimPy pasa en Latin-1 (no UTF-8) un texto
  cuyos caracteres caben todos en Latin-1 («Cámara»), y devolver luego esa cadena lanza
  `SystemError`. Con algún carácter fuera de Latin-1 (`—`) va bien: `Sesion.x()` añade `// —` a
  todo texto no ASCII (errores.md #48).
- **Tamaños por defecto** (x × y × z, m):

  | Clase | Tamaño |
  |---|---|
  | Processor | 4 × 3 × 2 (no 2 × 2) |
  | Queue | 2 × 2 × 0,2 |
  | Source / Sink | 1,06 × 1,06 |
  | Rack | 20 × 1,5 × 8,4 |
  | Robot | 0,68 × 1,0 |
  | Operator | 0,4 × 0,58 |
  | Transporter | 2,38 × 1,37 |
  | TaskExecuter | 2 × 1 |
  | Dispatcher | 0,95 × 1,5 |
  | StraightConveyor | 10 × 1 |
  | VisualTool | 10 × 6 |

  `setProperty("Size", [x, y, z])` los cambia. Ponlo antes de colocar.
- **Verificado por ejecución:**
  - Clases `VisualTool` (VisualDisplay «Plane»/«Cube», que se lee como 1/2), `Rack` (con
    `NumBays`, `BaySize`, `NumLevels` y `LevelSize`) y `Conveyor::ConveyorSystem` (se crea solo).
  - `contextdragconnection` con cintas crea `Conveyor::EntryTransfer`/`ExitTransfer`.
  - Un robot carga una cinta con `UseTransport` + `TransportRef`.
  - Clasificación por `SendToPort` con código: cada palé llegó al rack de su etiqueta.
  - `PathPoints` de los Divider; conexión «A» del navegador a los Task Executers (viajeros).
- `te.stats.totalTravelDistance.value` devolvió 0 aunque los recursos se habían movido: esa
  estadística no se registra por defecto.
- `Model.time`, `runToTime` y `stats.input/output` funcionan. 24 h de simulación de un modelo de
  unos 140 objetos tardaron 0,2 s.
- `getProperty("VisualDisplay")` devuelve el número de la opción; con `GET_PROPERTY_FLAG_STRING`
  devuelve el nombre.

## 6. Guardar el modelo sin diálogo

`savebyname(model(), "C:/ruta/modelo.fsm")` guarda sin diálogo y devuelve 1. El .fsm se reabre
en otra sesión con todo, incluido el código de las propiedades *Code*. Haz reset antes de
guardar para dejar el modelo en su estado inicial. (`cmdsaveas` y `savetree` sí abren diálogo.)

## 7. Experimentos: barridos de escenarios y KPIs

- **FlexSim arranca una vez por proceso** de Python. Para comparar escenarios, lanza un
  subproceso por escenario (cada uno construye, simula y escribe un JSON) y agrega los JSON.
- Patrón de ejecutor: generar el script con los parámetros del escenario → `Sesion` →
  ejecutar los bloques → `reset` → `runToTime(días × 86400)` → leer etiquetas-KPI y
  estadísticas → JSON. Escena de ~190 objetos: 5 días en 30 s-2 min.
- `flexsim_check.py` compila además **cada campo Code y cada trigger** por separado, sin
  ejecutarlo (`if (0) { código } return "COMPILA";`): un código que no compila no da error en
  ningún otro sitio.
- Lecturas útiles: `o.stats.state().getTotalTimeAt(STATE_IDLE)` (utilización),
  `o.stats.content.average` / `.maximum`, etiquetas con `o.find(">labels")`.
- El proceso termina con un *Segmentation fault* al cerrar FlexSim (6 de 6 veces medidas; ni
  `os._exit` ni `TerminateProcess` lo evitan), después de haber escrito los resultados. Es
  inofensivo si el JSON está completo, pero el código de salida no sirve: lee el JSON.

## 8. Semillas y réplicas

- `Sesion.sembrar(n)` = `randinit(stream, semilla)` para los streams 0-99, con semillas derivadas
  de `n`. Va **después** del reset (con «Repeat Random Streams» el reset las devuelve a sus
  valores por defecto) y antes de correr. `Sesion.correr(T, semilla=n)` hace las dos cosas.
- Medido con la prueba de humo: misma semilla → resultado idéntico; otra semilla → distinto.
  Lo que se muestrea **durante** el reset (la primera llegada de un Source) usa aún la semilla
  por defecto.
- Requisito para la reproducibilidad: posición de reset de los Task Executers fijada
  (`setresetposition`; `generar_escena.py` lo hace). Sin ella, la segunda corrida del mismo
  proceso empieza con los recursos donde acabó la primera.
- `scripts/replicas.py` lanza un proceso por réplica con `{semilla}` y `{json}` en la plantilla
  del ejecutor, y saca media, desviación, IC (t de Student) y réplicas necesarias para una
  precisión dada. `--comparar` corre otro escenario con las mismas semillas y analiza la
  diferencia pareada. Por defecto, de uno en uno (`--paralelo 1`): varios FlexSim a la vez han
  dado *segmentation fault*. Una réplica sin JSON se reintenta una vez y si no, se excluye.

## 9. Vigilante y prueba de humo

- `vigilar_simulacion(s, T, paso, parada)` (o `Sesion.correr(T, vigilar=paso)`): foto de cada
  objeto (entradas, salidas, contenido, `getstatestr`) cada `paso` s. Alarmas SIN PROGRESO,
  ATASCO y CRECE (patrones.md §12). Coste: una consulta por trozo; con trozos de 1 h, 5 días de
  una escena de ~190 objetos tardan lo mismo que sin vigilar (~40 s).
- Ejemplos medidos: un Processor de capacidad 2 con operarios → SIN PROGRESO en 3 h con
  «Puesto (waiting for operator); Operario_1, Operario_2 (utilize todo el tiempo)». En un
  almacén de 5 días → ATASCO de la playa de inflamables «waiting for transport» 8 h, causado por
  el rack de esa zona al 98 %.
- `scripts/prueba_humo.py` construye una escena mínima con los patrones de patrones.md §11,
  la simula 8 h en dos procesos (variante sana y variante rota) y comprueba: bloques OK, códigos
  que compilan, llegadas, conservación de items, utilización teórica, Separator, FEFO sin
  infracciones, nombres con tilde y conexión en los dos sentidos, vigilante limpio,
  reproducibilidad por semilla y que el vigilante detecta la variante rota. La parte estática
  (sin FlexSim, salida 2) pasa además casos fijos del linter, de las cabeceras de bloque y de los
  nombres repetidos del generador. Tarda ~30 s. Pásala tras tocar los scripts del skill.
