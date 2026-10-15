---
name: "flexsim-modelado"
description: "Escribe, amplía, corrige y verifica scripts FlexScript que construyen la escena de un modelo FlexSim (Source, Queue, Processor, Rack, cintas, operarios, carretillas, AMR, robots, suelos, paredes, muros A*) y el plano 2D coherente con la simulación: crear, colocar, conectar y configurar objetos, rutear o clasificar items, asignar operarios y transporte, automatizar escenarios y datos, y ejecutar y simular en FlexSim real con FlexSimPy. Úsalo siempre que el usuario mencione FlexSim o FlexScript, quiera «montar el modelo» o un layout por script, o cuente síntomas como items que se teletransportan, cintas mal colocadas, paquetes sin clasificar o errores como «Unknown command», «Not enough parameters», «Could not finish parsing» o «EntryTransfer has a range that extends too far», aunque no diga «script»."
---

# FlexSim: scripts de construcción de escena

Guía para **crear o modificar** scripts FlexScript que construyen la escena de un modelo FlexSim
sin repetir errores ya diagnosticados. Cubre *cómo* construir, no el contenido de cada escena:
topología, nombres, parámetros y escenarios salen de los entregables del usuario (especificación,
tablas de parámetros, guía). Si faltan datos de la escena, como dónde va un robot, qué tramos
llevan cinta o qué representa un item, pregúntalo: inventarlo produce un modelo que parece
correcto y no lo es.

## Archivos del skill

| Archivo | Cuándo leerlo |
|---|---|
| `references/api.md` | antes de escribir cualquier comando o propiedad: API verificada, propiedades por clase, distribuciones, obsoletos, dónde está la ayuda |
| `references/patrones.md` | al construir: orden de bloques, colocación, cintas, conexiones, recursos, lógica por propiedades *Code* y triggers, §10 operación realista (balance de capacidad, lotes, stock, pedidos que tiran del stock, FEFO, KPIs), §11 patrones listos del generador §12 validar resultados (vigilante, réplicas, prueba de humo) y §13 estaciones reservadas y cadena de custodia |
| `references/automatizacion.md` | cuando algo «queda para la GUI» o el usuario pide simplificar: `executefsfile`, generador, Model Parameters/Experimenter, llegadas por turnos, SQL sobre objetos, CSV/Excel, A\*, Lists |
| `references/errores.md` | cuando el usuario trae un error o un síntoma raro |
| `scripts/generar_escena.py` | escenas de más de unos pocos objetos: describes la escena en Python (objetos, colocación en x/y, cintas, zonas, paredes, muros A\*, conexiones, propiedades, triggers y variables internas) y genera el script completo, la limpieza, un `.fs` por bloque, las líneas `executefsfile` y el plano 2D (SVG con rótulos y PNG de fondo) |
| `scripts/check_script.py` | siempre, antes de entregar (incluye nombres de variable prohibidos) |
| `scripts/flexsim_check.py` + `references/flexsimpy.md` | si hay FlexSim instalado (Windows): construye el script en FlexSim real sin interfaz, verifica bloques, propiedades, posiciones y A\*, simula y guarda el .fsm. Léelo antes de decir «no puedo ejecutar FlexSim» |
| `scripts/replicas.py` | siempre que des cifras de una simulación estocástica: N réplicas con semillas distintas, IC, réplicas necesarias y comparación pareada de escenarios (`--comparar`) |
| `scripts/prueba_humo.py` | tras tocar los scripts del skill o en una instalación nueva: comprueba en ~45 s, en FlexSim real, que los patrones dan el comportamiento esperado y que el vigilante detecta un interbloqueo |
| `scripts/flexhelp.py` | para consultar comandos globales en la ayuda instalada |

## Flujo de trabajo

1. **Reúne los datos de la escena** de los entregables y no los contradigas. **Haz el balance de
   capacidad antes de construir** (patrones.md §10.1): carga diaria de cada recurso = volumen ×
   tiempo medio, frente a lo que da su dotación. Si la carga supera la capacidad, el modelo se
   atascará por mucho que la lógica esté bien: díselo al usuario con las cifras. En modo
   *modificar*, pide los nombres exactos de los objetos que ya existen (`--existing` en el
   verificador). Si los datos chocan entre sí (p. ej. «14 camiones/día» frente a «interarribo
   de 60 s»), señálalo en vez de elegir uno en silencio.
2. **Verifica cada API antes de escribirla** (`references/api.md`, `flexhelp.py`, la ayuda
   online). FlexSim solo se queja al ejecutar, y a veces ni eso.
3. **Construye en el orden crear → colocar → conectar → propiedades**
   (`references/patrones.md`). Con más de unos 15 objetos, usa `scripts/generar_escena.py` y
   guarda el fichero de escena junto a los entregables: los cambios se hacen ahí y se regenera.
4. **Ejecuta** `python scripts/check_script.py <script>` y corrige todo FAIL. Un WARN se corrige
   o se justifica.
4b. **Si hay FlexSim en la máquina, ejecútalo de verdad** con `scripts/flexsim_check.py`
   (references/flexsimpy.md: compilar FlexSimPy una vez, modelo base, opciones). Corrige la causa
   en el generador y repite hasta que todos los bloques den OK, las posiciones coincidan con el
   plano y la simulación avance **sin alarmas del vigilante** (`--vigilar 3600`: interbloqueos,
   atascos, colas que crecen). Entrega también el .fsm guardado.
4c. **Si das cifras, da réplicas.** Ejecutor con `--semilla` + `scripts/replicas.py` (10 réplicas
   por defecto): media ± IC. Para comparar escenarios, `--comparar` con las mismas semillas; una
   diferencia que no es significativa no es una mejora.
5. **Entrega** con un informe honesto (abajo) y las comprobaciones visuales de patrones.md §8.
6. **Si vuelve con un error**, búscalo en `references/errores.md`. Si es nuevo, diagnostícalo,
   corrige la causa en el generador o en el patrón (no solo en el script) y añade la fila.

## Reglas que más errores han evitado

- **No adivines una API.** Los fallos más caros fueron comandos plausibles pero inventados
  (`Model.addNode`, `Model.build`) y el código que traen las especificaciones (`getparam`,
  `insertnodefirst`), que nadie había comprobado. Lo que no esté verificado se marca como tal.
- **Crear → colocar → conectar.** Las transferencias de una cinta se crean al conectarla y no se
  mueven con ella. Si conectas antes de colocar, la simulación se detiene con
  «EntryTransfer… extends too far to the end of the conveyor».
- **Sin transporte, objetos pegados.** Una conexión `"A"` sin `UseTransport` mueve el item al
  instante. Si los objetos están separados, se ve un teletransporte. Solo hay hueco donde hay
  una cinta o un recurso que transporta.
- **Coloca en tiempo de ejecución** con `getLocation`/`setLocation` y factores sobre el tamaño
  real. Para las cintas, `location = (0,0,0)` y luego los extremos calculados desde los bordes.
  `location` no es el centro y el tamaño por defecto de cada clase es desconocido.
- **Las paredes visuales no bloquean.** Para que operarios y carretillas pasen por las puertas,
  añade muros A\* (`AStar::Divider` dentro de `AStarNavigator`) y conecta cada recurso móvil
  al navegador con «A». Plano y simulación salen de la misma geometría (patrones.md §9).
  **Los objetos fijos tampoco bloquean**: estanterías, estaciones, mesas y playas se conectan al
  navegador con «A» como barreras (`e.barreras_astar`); si no, los recursos les pasan por encima.
  Compruébalo con `flexsim_check.py --recorridos` (0 cruces de muros y de objetos).
- **La lógica por item va en propiedades *Code*** (`SendToPort`, `TransportRef`, `OperatorRef`,
  `ProcessTime`...) como texto con FlexScript. **Los triggers sí se fijan por script**: nodo
  `variables/entrytrigger` (`exittrigger`, `processfinishtrigger`, `resettrigger`...) +
  `enablecode` + `buildnodeflexscript` + `rebindobjectattributes` (api.md §3b;
  `generar_escena.trigger`). Sin una `SendToPort` propia, todos los items van al primer destino libre.
- **Un código que no compila falla en silencio** dentro de un campo Code o un trigger: el objeto
  simplemente no hace nada. Causa típica: una variable con nombre de comando (`ne`, `eq`, `local`,
  `param`, `setitem`...). `check_script.py` (comprobación 10) lo detecta y `flexsim_check.py`
  compila cada campo por separado.
- **Un puesto con operarios = un Processor de capacidad 1.** Con `MaxContent` > 1 y operarios de
  proceso, los operarios se quedan enganchados (medido). Varios puestos = varios objetos.
  Usa los patrones del generador (`e.equipo`, `e.puestos`, `e.estacion_fefo`, `e.separador_lote`,
  patrones.md §11) en vez de reescribir esa lógica.
- **Una corrida no es un resultado.** Sin sembrar tras el reset (`randinit`), todas las réplicas
  salen iguales; sin `setresetposition`, la misma semilla da resultados distintos. Con el
  generador y `--semilla` las dos cosas están resueltas.
- **Referencias explícitas** (`return model().find("X");`) en `OperatorRef`/`TransportRef` cuando
  un objeto usa a la vez operarios y transporte: por defecto los dos tiran de `centerObjects[1]`.
- **Todo bloque repetible.** Crea con `find` + `objectexists` y conecta con marcas en las
  etiquetas de los dos extremos. Así un bloque que falla se repite sin limpiar nada y un
  objeto recreado se reconecta solo.
- **Bloques auto-contenidos, sin funciones propias.** Cada bloque localiza lo que necesita por
  nombre: las variables no sobreviven entre ejecuciones de la consola y FlexScript no admite
  funciones en ella.
- **Verifica `setProperty` con `getProperty`.** Un nombre de propiedad inexistente no da error:
  no hace nada (medido en FlexSim).
- **Navegador A\***: `createinstance(library().find("?AStarNavigator"), model())`, nunca
  `Object.create("AStar::AStarNavigator")`, que devuelve otro nodo del interfaz.
- **Guardado.** `savebyname(model(), "C:/ruta/modelo.fsm")` guarda sin diálogo (verificado). Si
  no lo usas, el usuario guarda con Ctrl+S. La cabecera del script dice cómo.

## Qué entregar

- El script completo (`<escena>.flexscript`) para pegar bloque a bloque, con cabecera de uso,
  el orden de bloques y la nota de guardado.
- La limpieza (`limpiar_<escena>.flexscript`) por bloques, más una sección «solo cintas».
- Opcional, pero ahorra tiempo al usuario: un `.fs` por bloque y `EJECUTAR_<escena>.txt` con
  una línea `executefsfile(...)` por bloque. Advierte de que ese comando está marcado «For
  developer use».
- Un documento con lo que queda para la GUI, cómo automatizarlo (`references/automatizacion.md`)
  y qué decisiones faltan.

Informe al entregar. No escribas «funciona» si no se ha ejecutado:

```
Construido:    <bloques y objetos>
Verificado:    API contra la ayuda; check_script.py: <N FAIL, M WARN>
Ejecutado:     flexsim_check.py: <bloques OK, Code que compilan>; vigilante: <alarmas o ninguna>
Resultados:    <KPI = media ± IC 95 % con N réplicas> (o «sin ejecutar»)
No verificado: <APIs o clases sin verificar; ejecución en FlexSim si no la hubo>
Uso:           modelo vacío o existente; orden de bloques; guardar con Ctrl+S
Pendiente:     <lo que queda para la GUI y las decisiones abiertas>
```

Si la escena tiene métricas, **no inventes cifras**: sin ejecución, la plantilla de resultados se
entrega vacía y se explica por qué. Con ejecución, cada cifra va con su intervalo de confianza y
el número de réplicas. Si FlexSim está instalado, sí puedes ejecutar: FlexSimPy
funciona, pero `evaluate()` evalúa un **nodo** por su ruta, no texto (references/flexsimpy.md).
Informa de lo que ejecutaste y de lo que viste (estado por bloque, posiciones, simulación).
Sin FlexSim, quien verifica la ejecución real es el usuario: pídele el mensaje exacto de
cualquier error.
