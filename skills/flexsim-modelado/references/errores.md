# Errores ya resueltos en FlexSim 2027

Si el error que trae el usuario aparece aquí, aplica la resolución tal cual sin volver a
diagnosticarlo. Si no aparece, diagnostícalo con la ayuda (`references/api.md`, sección 1) y
añade la fila (ver «Cómo añadir una entrada»).

Hay dos tipos: errores con **mensaje** de FlexSim y fallos **silenciosos**, en los que el modelo
corre pero hace otra cosa. Estos segundos solo se ven mirando la vista 3D o las estadísticas.

## Con mensaje

| # | Mensaje | Causa | Resolución |
|---|---|---|---|
| 1 | `syntax error` en la línea de `treenode mk(...)` y en la llave de cierre | FlexScript no admite funciones definidas por el usuario en la Script Console. | Inlinear todo; nada de `treenode f(...) {}`. Si se repite mucho código, genéralo con `scripts/generar_escena.py`. |
| 2 | `Unknown command addNode being called` (y `connect`, `save`) | API inventada. | `Model.addNode` → `Object.create()`; `Model.connect` → `contextdragconnection(a, b, "A")`; `Model.save` → no existe: Ctrl+S. |
| 3 | `Not enough parameters passed to command contextdragconnection` | El 3.er parámetro (la tecla de la GUI) es obligatorio. | `"A"` flujo, `"S"` puerto central, `"D"` extendida; `"Q"`/`"W"`/`"E"` desconectan. (Versiones antiguas del skill decían que `"S"` desconectaba: es falso.) |
| 4 | `Could not finish parsing because of previous errors.` | Solo avisa de errores anteriores. | Corrige los errores previos. |
| 5 | *invalid cast exception* en `Object x = model().find("N");` | `N` no es un objeto (p. ej. una carpeta del árbol). | `treenode x = model().find("N"); if (objectexists(x)) { x.as(Object)... }` |
| 12 | `exception: ErrorEntryTransfer8 has a range that extends too far to the end of the conveyor. There must be full space on the conveyor to put an item on it.` (el modelo se atasca en una cinta) | La cinta se **conectó antes de colocarla**. La transferencia se crea al conectar y no sigue a la cinta cuando se mueven sus extremos. Su posición no se puede fijar por script. | Orden crear → colocar → **conectar** (patrones.md §1). En un modelo ya afectado: borra la cinta y vuelve a crearla, colocarla y conectarla, o empieza un modelo vacío. En la GUI se arregla arrastrando la transferencia. `check_script.py` lo avisa en su comprobación 9. |

## Silenciosos (sin mensaje)

| # | Síntoma | Causa | Resolución |
|---|---|---|---|
| 6 | `node("ruta")` «encuentra» un objeto que no existe | `node()` devuelve una referencia que nunca es `NULL`. | `model().find()` + `objectexists()`. |
| 7 | Los items no se clasifican por tipo: todos van al primer destino | Nadie pone etiqueta de tipo y la `SendToPort` sigue por defecto (`0` = primer puerto libre). | Etiquetar en la `SendToPort` del Source (o en un trigger) y rutear en la del objeto que ramifica (patrones.md §7). |
| 8 | `flexhelp.py` dice «NO EXISTE» de `uniform`, `triangular`, `erlang`... | Fallo del script antiguo (no admitía un salto de línea entre `<command>` y `<name>`). | Corregido. Ante una duda, `grep -n "<name>X</name>" Commands.xml`. |
| 9 | Tiempos con la moda equivocada | Una especificación escribe `triang(min, moda, max)` y FlexSim es `triangular(min, max, moda)`. `erlang` es `(location, scale, shape)`. | Reordenar al pasar los datos al código. |
| 10 | Los items «se teletransportan» entre objetos | Conexión `"A"` sin transporte entre objetos separados: el item salta al instante. | Pegarlos (colocación relativa) o activar `UseTransport` + `TransportRef`. Solo hay hueco donde hay cinta o transporte (patrones.md §3). |
| 11 | Las cintas no empiezan ni acaban en sus objetos | Extremos con coordenadas fijas (`location` no es el centro) o cinta creada lejos del origen. | Cinta en `location = (0,0,0)` y extremos calculados con `getLocation` de los bordes (patrones.md §4). |
| 13 | El ruteo por nombre de destino falla con cintas | El puerto de salida apunta a la Entry Transfer, no a la cinta. | Compara también `o.up.name` y `o.outObjects[1].name`, con respaldo por orden de conexión (patrones.md §7). |
| 14 | Un Processor con operarios y transporte llama al recurso equivocado | `OperatorRef` y `TransportRef` usan por defecto `centerObjects[1]`, el mismo objeto. | Fija los dos con `return model().find("...");`. |
| 15 | Conexiones duplicadas al repetir el bloque de conexiones | Se conectó sin marcas, o sobre un modelo construido por una versión sin marcas. | Marcas `cx<tecla>_<otro>` en las etiquetas de los dos extremos (patrones.md §5); modelo vacío para la primera construcción. |
| 16 | `Model.build(a, b, c)` crea una cadena en vez de una ramificación | API inventada que «funciona» de otra forma. | Una `contextdragconnection` por par. |
| 17 | Objetos duplicados al pegar un bloque dos veces | `Object.create` no comprueba nombres. | Patrón `find` + `objectexists` antes de crear (patrones.md §2). |
| 18 | Operarios o carretillas atraviesan las paredes | Las paredes son solo visuales (VisualTool, Walls sin A\*). | Muros lógicos `AStar::Divider` dentro de `AStarNavigator` y conexión «A» del navegador a cada Task Executer (api.md §4b, patrones.md §9). |
| 19 | Con A\*, los recursos salen de la nave para rodear un muro | La fachada tiene huecos (muelles) en A\* o no tiene divider. | Perímetro de fachada cerrado como Divider (repite el primer punto); los huecos de muelle solo en la pared visual. |
| 20 | Los muros A\* no hacen nada | El navegador no se llama exactamente `AStarNavigator`, el Divider no está dentro de él o no se registró. | `nav.name = "AStarNavigator"`; `d.up = nav;` `function_s(d, "assertNavigator");` y al final `function_s(nav, "rebuildMeshes");`. Los Task Executers deben ser miembros (conexión «A»). |
| 21 | Los muros A\* desaparecen (solo quedan los de bloques posteriores) | `Object.create("AStar::AStarNavigator")` devolvió otro nodo (la SystemConsole de la vista), el script lo renombró y metió ahí los Divider. | `createinstance(library().find("?AStarNavigator"), model())` y comprobar su `Class` antes de usarlo. Medido con FlexSimPy. |
| 22 | Una propiedad «no se aplica» y no hay error | `setProperty` con un nombre inexistente no hace nada. | Verificar con `getProperty` (None = no existe); `flexsim_check.py` lo hace solo. |
| 23 | La simulación no crea items (Source vacío, el reloj salta y para) | El modelo no tiene `Tools/FlowItemBin` (p. ej. un .fsx mínimo hecho a mano). | Construir sobre un modelo real (File > New Model, o un .fsm existente vaciado). |
| 24 | `evaluate()` de FlexSimPy devuelve None con cualquier código | Evalúa el NODO de esa ruta, no texto FlexScript. | Nodo FlexScript `executestring(param(1))` en el modelo (references/flexsimpy.md §3). |
| 25 | Objetos solapados o fuera de su zona aunque el plano estaba bien | El plano suponía 2 × 2 m y un Processor mide 4 × 3 por defecto. | Tamaños medidos en el generador y `setProperty("Size", [...])` antes de colocar; comparar con `flexsim_check.py --posiciones`. |
| 26 | Rutas relativas que dejan de funcionar tras `launch()` | FlexSim cambia el directorio de trabajo del proceso. | Pasar todas las rutas a absolutas antes de lanzar. |
| 27 | Operarios en «utilize» sin hacer nada; el proceso espera operario; el flujo se frena | Processor con `MaxContent` > 1 y operarios de proceso: la llamada y la liberación de operarios es una sola marca por objeto. | Un puesto = un Processor de capacidad 1 (o un equipo: `NumProcessOperators` = n con capacidad 1). Reproducido aislado con FlexSimPy; la prueba de humo lo reproduce y el vigilante lo marca como SIN PROGRESO. |
| 28 | Un trigger o un campo Code «no hace nada» | El código no compila y FlexSim no avisa. Caso real: una variable llamada `ne` (es un comando). | `check_script.py` (comprobación 10) y `flexsim_check.py` (compila cada campo con `if (0) { ... }`). Lista de nombres prohibidos en api.md §4. |
| 29 | Combiner en «collecting» con la lista de componentes ya completa | Se cambió `componentlist` en On Entry sin actualizar `targetcomponentsum`. | `setvarnum(current, "targetcomponentsum", suma)` en el mismo trigger. |
| 30 | Cartera de pedidos que crece sin fin; estaciones ocupadas mucho tiempo con pocos operarios ocupados | Pedidos liberados sin stock (esperan palés que no hay) o recursos que no dan para la carga. | Balance de capacidad (patrones.md §10.1); liberar solo con stock (§10.5); más estaciones que operarios. El vigilante (`--vigilar`) avisa con CRECE. |
| 31 | Toda la entrada se para aunque solo una zona está llena | Una cinta o desviador compartido se bloquea detrás del lote de la zona llena; reaprovisionamiento que mira solo el stock físico. | Reaprovisionar por posición de inventario (§10.5) y playas con capacidad. |
| 32 | Los KPIs de la segunda ejecución salen el doble | Las etiquetas-contador no se ponen a 0 con Reset. | Trigger On Reset que las ponga a 0. |
| 33 | Una consulta de estadísticas devuelve 0.0 | `.stats.content.max`/`.min` o `string.find` no existen: no compila. | `.maximum`, `.average`; recorrer con `.length`/`.substr`. |
| 34 | A mitad de simulación todo se para para siempre: una carretilla en estado 4 (bloqueada) con su palé, el resto ocioso | El navegador A\* trae **la evitación de colisiones activada** (`enableCollisionAvoidance` = 1) y en un pasillo estrecho (2 m entre pared y estaciones, carretilla de 2,4 × 1,4 m) quedó un interbloqueo permanente con recursos parados. | Pasillos de anchura real (≥ 2,5-3 m donde pasan carretillas) y, si aun así se bloquea, `setvarnum(nav, "enableCollisionAvoidance", 0)` (los recursos se atraviesan). Detectarlo: `--vigilar 3600` (alarma SIN PROGRESO con la carretilla como sospechosa). |
| 35 | Dos corridas con la misma semilla dan resultados algo distintos (p. ej. utilización 0,7634 frente a 0,7632) | Un reset no devuelve los Task Executers a donde se colocaron por script: empiezan donde acabó la corrida anterior. | `setresetposition(obj)` tras colocar (lo hace `generar_escena.py`). Medido con la prueba de humo. |
| 36 | Todas las réplicas dan exactamente lo mismo | Con «Repeat Random Streams» el reset devuelve los streams a la semilla por defecto. | Sembrar tras el reset: `randinit(stream, semilla)` para 0-99 (`Sesion.sembrar`, `--semilla`); una semilla distinta por réplica (`replicas.py`). |
| 37 | Un Combiner «saca» más items de los que recibe como pedidos | `stats.output` cuenta también los componentes empaquetados. | Pedidos = salidas − componentes, o contar en el On Entry del Sink. |
| 38 | Llegan muchos menos items de los esperados | `exponential(1800, 400)` en `InterArrivalTime` suma los 1800 s de `location` a **cada** intervalo, no solo al primero. | Para retrasar el arranque: `if (Model.time < 1800) { return 1800; } return exponential(0, 400, s);` |
| 39 | Una playa de entrada a stock pasa horas en «waiting for transport» aunque el recurso está libre a ratos | El rack de destino está lleno o casi: lo que ya va en camino ocupa el hueco que queda. | Capacidad del rack y reposición por posición de inventario (patrones.md §10.5). El vigilante lo marca como ATASCO. |
| 40 | Operarios, carretillas o AMR **atraviesan estanterías, puestos y colas** aunque sí respetan las paredes | A\* solo esquiva los muros (`AStar::Divider`). Un objeto fijo (Rack, Combiner, Processor, Queue) no es obstáculo salvo que se conecte al navegador con «A» (barrera). Medido: 698 pasos por encima de racks y estaciones en 7,5 h; 0 con barreras. | `e.barreras_astar([...])` (conexión «A» navegador → objeto) para estanterías, estaciones, mesas y playas. Coste medido: despreciable (OTIF 96,2 → 95,6 % en una réplica). Comprobarlo: `flexsim_check.py --recorridos 2 --desde 21600`. |
| 41 | Una comprobación de recorridos ve saltos imposibles (54 m en 3 s) y cruces que en la vista 3D no existen | `getLocation` de un recurso que viaja devuelve la posición del **último evento**, no la interpolada. | `updatelocations(obj)` antes de leer la posición (lo hace `revisar_recorridos`). |
| 42 | Al reservar estaciones para un tipo de pedido (p. ej. jaula de custodia), **todo** el picking se frena y la cartera crece | El objeto que reparte (capacidad 1) se queda con un pedido que solo puede tomar la estación reservada y, mientras espera, no sale ningún otro: bloqueo en cabeza de cola. Medido: OTIF 52 %. | Liberar ese tipo solo si su estación puede aceptarlo (contador «en curso» ≤ n.º de estaciones reservadas) y, al terminar, `receiveitem()` sobre el que reparte. |
| 43 | Reservar estaciones para un tipo de pedido hunde el servicio del resto | Las reservadas se restaron de las normales: con 8 operarios y 7-8 estaciones se pierde el margen «más estaciones que operarios» (patrones.md §10.5). | Las estaciones reservadas se **añaden** a las normales. |

## Cómo añadir una entrada

```
| N | `<mensaje exacto>` o síntoma | <causa real, no el síntoma> | <corrección concreta, con ejemplo> |
```

**El skill vive en la cuenta del usuario.** La carpeta local
(`AppData\Roaming\Claude\local-agent-mode-sessions\skills-plugin\...\skills\flexsim-modelado`)
es una **caché sincronizada**: editarla no actualiza el skill y puede sobrescribirse. Para que
el cambio cuente:
1. Edita una copia.
2. Empaquétala como `.skill` (un zip que contenga la carpeta `flexsim-modelado/`).
3. Pide al usuario que la suba en Ajustes → Capacidades → Skills, sustituyendo la anterior.
