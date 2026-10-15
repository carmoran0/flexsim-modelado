# API de FlexSim 2027 para scripts de construcción

Leída de la ayuda instalada (`Commands.xml`, `Tree\Object.xml`, `Tree\treenode.xml`, clases de
`Data\`, `Basic\`) y de la ayuda online de Autodesk, entre el 08 y el 10/10/2026. Que algo esté
aquí **no** prueba que ejecute: ver «Estado de verificación» al final.

## Índice
1. Dónde está la documentación
2. Árbol, objetos y conexiones
3. Propiedades (`setProperty`) por clase
4. Código dentro de propiedades: distribuciones, tiempo, texto, color
4b. Plano: objetos visuales (suelos, paredes) y A* (muros que bloquean el paso)
5. Obsoletos e inexistentes
6. Estado de verificación

---

## 1. Dónde está la documentación

| Contenido | Dónde |
|---|---|
| Comandos globales (1216) | `C:\Program Files\Autodesk\FlexSim 2027\help\CommandReference\Commands.xml` → `python scripts/flexhelp.py <comando>...` |
| Clases (`Object`, `treenode`, `Conveyor`, `TaskExecuter`, `Model`, `string`, `Math`, `Color`, `AStar`...) | `...\help\FlexScriptAPIReference\<Carpeta>\<Clase>.xml` (leer o hacer grep) |
| Páginas de objetos (propiedades, eventos, conexiones, paneles) | **Solo online.** Índice JSON con todos los `id`: `https://help.autodesk.com/cloudhelp/2027/ENU/FlexSim-User-Manual/files/toctree.json` (cada entrada trae `ttl`, `id` y `ln`, la ruta del HTML). Página: `https://help.autodesk.com/view/FLEXSIMIN/2027/ENU/?guid=<id>` |

- `docs.flexsim.com` ya no responde (error 1016 de Cloudflare). La ayuda migró a Autodesk.
- WebFetch puede fallar. Lo que sí funciona es abrir cualquier página de la ayuda en el navegador
  integrado y, desde ella, hacer `fetch` del `toctree.json` y de los HTML con `javascript_tool`
  (mismo origen), pasándolos a texto con `DOMParser`.
- IDs útiles: `reference_3dobjects_fixedresources_fixedresourcesconcepts` (propiedades y eventos
  comunes), `..._processor`, `..._source`, `reference_3dobjects_taskexecuters_taskexecuterconcepts`,
  `..._robot`, `..._operator`, `..._dispatcher`, `reference_3dobjects_conveyors_straightcurvedconveyor`,
  `..._entrytransfers`, `..._exittransfers`, `reference_3dobjects_warehousing_storageobject`,
  `reference_3dobjects_generalpropertylist`, `reference_tools_propertytables` (tipos de propiedad),
  `connectingflows_ports_addingremovingports` (teclas A/S/D/Q/W/E), `modellogic_modelparameters`,
  `workingwithtasks_travel_workingwithastar`, `connectingflows_lists_introsqlqueries`.
  Todos llevan el prefijo `FlexSim_User_Manual_` y el sufijo `_html`.
- `flexhelp.py` anterior al 08/10/2026 daba falsos «NO EXISTE» (no admitía un salto de línea
  entre `<command>` y `<name>`). Ante un «no existe» sospechoso: `grep -n "<name>X</name>" Commands.xml`.

## 2. Árbol, objetos y conexiones

| Tarea | API | Nota |
|---|---|---|
| Crear | `Object.create("Processor")`, `Object.create("Conveyor::StraightConveyor")` | devuelve el objeto ya añadido al modelo. **No comprueba nombres**: crear dos veces duplica |
| Renombrar | `n.name = "X"` | |
| Buscar | `model().find("X")` (también `Model.find`) | `NULL` si no existe. Rutas: `/` entra, `..` sube, `?` recursivo (`"/?X"`), `~n` el n-ésimo con ese nombre |
| Existe | `objectexists(n)` / `if (n)` | el obsoleto `node()` nunca da `NULL`: solo lo detecta `objectexists` |
| Tipo | `n.as(Object)`, `n.is(Object)` | el cast lanza *invalid cast* si el nodo no es un objeto. Guarda `find` en un `treenode` |
| Borrar | `n.destroy()` | |
| Posición | `o.location` (Vec3) / `o.location.x` | **no** es el centro: es un punto de referencia del objeto |
| Posición por factores | `Vec3 p = o.getLocation(fx, fy, fz)` · `o.setLocation(x, y, z, fx, fy, fz)` | factores 0-1 del tamaño real. `(0.5,0.5,0.5)` = centro. Usa 0/1 en x (bordes izquierdo/derecho) y 0.5 en y; el sentido del factor y no está aclarado |
| Tamaño / giro | `o.size` (Vec3), `setSize(x,y,z)`, `o.rotation`, `setRotation(x,y,z)` | |
| Conectar | `contextdragconnection(a, b, "A")` | 3.er parámetro obligatorio = tecla de la GUI: `"A"` entrada/salida (flujo), `"S"` puerto central (recursos), `"D"` extendida (solo nodos de red). `"Q"`/`"W"`/`"E"` desconectan A/S/D |
| Conexiones de un objeto | `o.inObjects`, `o.outObjects`, `o.centerObjects` | base 1. Si la conexión es con una cinta, el puerto puede apuntar a la **transferencia**, no a la cinta |
| Subnodos | `n.subnodes[1]`, `.length`, `.first`, `.last`, `.up`, `.rank` | base 1; `[0]` lanza excepción |
| Etiquetas | `n.labels.assert("x", inicial).value` | crea si falta y conserva el valor si ya existe. `n.x` falla si no existe (`n.x?` da `nullvar`) |
| Estadísticas | `o.stats.input/.output/.content/.staytime/.state()`, `te.stats.totalTravelDistance` | |
| Clase de un objeto | `o.getProperty("Class")` | crea uno en la GUI y lee su clase: así se verifica el string para `Object.create` |
| Ejecutar un fichero | `executefsfile("C:/ruta/f.fs", 1)` | marcado «For developer use»; funciona (verificado con FlexSimPy) |
| Guardar sin diálogo | `savebyname(model(), "C:/ruta/modelo.fsm")` | devuelve 1; el .fsm se reabre completo (verificado). Haz `resetmodel()` antes |
| Copiar un nodo | `createcopy(nodo, contenedor, 1)` | |
| Ejecutar un texto | `executestring("...")` | |
| Reset | `resetmodel()` | |
| Carpeta del modelo | `modeldir()` | |
| Importar CSV a tabla | `importtable(nodo, "f.csv", 1, 1)` | también comandos `excel*` |

## 3. Propiedades por clase (`o.setProperty("Nombre", valor)` / `getProperty`)

Nombres en *PascalCase*: `interarrivaltime`, `capacity` o `processtime` **no** existen.

| Clase | Propiedades |
|---|---|
| Cualquier objeto | `Name`, `Class` (solo lectura), `Location`, `Rotation`, `Size` (Array(3)), `Color` (Array(4)), `ShowName`, `Groups`, `InObjects`/`OutObjects`/`CenterObjects` |
| Todo Fixed Resource (Source, Queue, Processor, Sink, Combiner, Separator, MultiProcessor, Storage, transfers de cinta) | `MaxContent`, `Pull`, `PullRequirement`, `PullStrategy`, **`SendToPort`** (Code), `UseTransport`, `TransportRef` (Code), `TransportPriority`, `TransportPreempt` |
| Processor | `ProcessTime`, `SetupTime` (Unit Code), `UseProcessOperators`, `NumProcessOperators`, `UseSetupOperators`, `NumSetupOperators`, `UseSameNumOperators`, `OperatorRef` (Code), `OperatorPriority`, `OperatorPreempt`, `AnimateItems` |
| Source | `InterArrivalTime` (Unit Code), `ArrivalStyle`, `FlowItemClass` (Options), `TimeZeroArrival`, `RepeatTable`, `ArrivalSchedule`, `ArrivalSequence` |
| Task Executer (Operator, Transporter, Robot, TaskExecuter, Crane, ASRSvehicle...) | `MaxSpeed`, `Acceleration`, `Deceleration`, `LiftSpeed`, `ExtensionSpeed`, `LoadTime`, `UnloadTime` (Unit Code), `PassTo`, `QueueStrategy`, `BreakTo` (Code), `Navigator` (Node), `OffsetTravel`, `AvailableOnStart`, `DoAnimations`, `RotateTraveling`, `FlipThreshold` |
| Robot (además) | `MotionMode`, `MoveTime` (Unit Code), `JointSpeeds`, `YRotationSpeed`, `ZRotationSpeed`. Base fija: sin navigator no viaja, solo alcanza con el brazo |
| Operator (además) | `IdleAnimation`, `WalkAnimation`, `WalkLoadedAnimation`, `UtilizeAnimation` |
| Cinta recta/curva | `StartLocation`, `EndLocation` (Array(3)), `Speed`, `Width`, `Acceleration`, `Deceleration`, `IsAccumulating`, `UseVirtualLength`, `VirtualLength`, `CatchCondition` (Code) |
| Entry Transfer | `EntryOrientation`, `HoldTransports`, `ItemInsertionMode`, `MaxTransportsIn` (+ Fixed Resource). Su posición en la cinta **no** es una propiedad |
| Exit Transfer | `StopAtEnd`, `ContinuousPickPrediction`, `PickPredictionInterval`, `IgnoreOnPredictLatePickup` (+ Fixed Resource) |
| Storage Object / Rack | `MinimumDwellTime` (Unit Code), `SlotAssignmentStrategy` (Code), `UseAsFixedResource`, `NumBays`, `NumLevels`, `SlotsPerBay`, `BaySize`, `LevelSize`...; Rack: `ExtendColumns`, `PickPlaceYOffset`, `ShelfTilt`. La lógica de fixed resource se activa con una conexión `"A"`. Capacidad = `MaxContent` (verificado: un Rack de 8 × 4 huecos admitió 601 items; las celdas se apilan) |
| A\* Barrier | `TravelPatterns`, `ConditionalRule` |
| A\* Divider / Path / Bridge | `PathPoints` (array 2D), `TwoWay`, `ConditionalRule`, `UseVirtualDistance`/`VirtualDistance` (Bridge) |
| A\* Navigator (variables, sin propiedad) | `enableCollisionAvoidance` (**1 por defecto**: los recursos se esperan entre sí; puede interbloquear en pasillos estrechos), `ignoreInactiveMemberCollisions` (1), `routeByTravelTime`, `cachePaths`, `defaultPathWeight`... `setvarnum(nav, "enableCollisionAvoidance", 0)` |

**Tipos de valor:**
- *Number* y *Boolean*: un número.
- *Unit*: un número en unidades del modelo, o `[valor, "unidad"]`.
- *Options*: el número o el nombre en inglés de la opción.
- *Node*: un nodo o una ruta en texto.
- *Array*: `[1, 2, 3]`.
- *Code*: **un texto con FlexScript**. Se guarda y se ejecuta, pero el campo de la GUI
  aparece vacío porque le faltan las marcas de pick-option. Lo confirma un hilo del foro de
  Autodesk.

**Los triggers (On Entry, On Exit...) no son propiedades, pero sí se fijan por script**
(verificado con FlexSimPy el 13/10/2026). Cada trigger es un nodo de código en `variables`:

```flexscript
treenode t = obj.find(">variables").subnodes.assert("entrytrigger");
t.value = "Object current = ownerobject(c); Object item = param(1); int port = param(2); ...";
enablecode(t, 1); buildnodeflexscript(t); rebindobjectattributes(obj);
```

| Trigger | Nodo | Verificado en |
|---|---|---|
| On Entry | `entrytrigger` | Processor, Queue, Combiner, Sink, Rack |
| On Exit | `exittrigger` | Processor (también con transporte), Rack |
| On Process Finish | `processfinishtrigger` | Processor |
| On Reset | `resettrigger` | Queue, Rack, Sink, Source, Combiner (pone a 0 las etiquetas-contador) |
| On Setup Finish, On Creation, On Message | `setupfinishtrigger`, `creationtrigger`, `messagetrigger` | sin probar (mismo patrón en el código de la librería) |

- Sustituye lo que hubiera (también la lista de opciones de la GUI).
- **Si el código no compila, no hay ningún aviso**: el trigger no hace nada. Compílalo antes
  (`flexsim_check.py` lo hace con `if (0) { código }`).
- `scripts/generar_escena.py`: `e.trigger(obj, "OnEntry", lineas)`.

### 3b. Variables internas sin propiedad

Algunas opciones de la GUI no tienen propiedad; se fijan en `variables` (verificado):

| Objeto | Variable | Valores |
|---|---|---|
| Separator | `unpack` | 1 = Unpack (por defecto), 0 = Split. `setvarnum(o, "unpack", 0)` |
| Separator | `splitquantity` | nodo de código: `Object item = param(1); return item.labels["n"].value;` (n = copias de salida en total, original incluido) |
| Combiner | `pack` | 1 = Pack (por defecto) |
| Combiner | `componentlist` | una fila por puerto de entrada ≥ 2 («From Input Port 2»...) con hijos `Target Quantity` y `Current Quantity`. Las filas aparecen al hacer Reset |
| Combiner | `targetcomponentsum` | **hay que fijarlo** si cambias la lista en On Entry del contenedor; si no, el Combiner se queda en «collecting» con la lista ya completa |

Lista de componentes por pedido (On Entry del Combiner, puerto 1 = contenedor):

```flexscript
if (port == 1) {
    treenode cl = getvarnode(current, "componentlist");
    cl.subnodes[1].subnodes[1].value = item.labels["n_a"].value;   /* puerto 2 */
    cl.subnodes[2].subnodes[1].value = item.labels["n_b"].value;   /* puerto 3 */
    setvarnum(current, "targetcomponentsum", item.labels["n_a"].value + item.labels["n_b"].value);
}
```

**Valores de retorno de los campos *Code* más usados:**
- `SendToPort`: `0` = primer puerto libre (por defecto), `n` = ese puerto, `-1` = no liberar.
- `TransportRef` y `OperatorRef`: el Task Executer o Dispatcher que hará el trabajo. Si es `0`,
  se supone que el código creó la secuencia de tareas por su cuenta.
- `PullStrategy`: el puerto del que tirar.
- `PullRequirement`: `1` o `0` (`param(2)` = puerto). Se evalúa por item disponible hasta que
  uno devuelve 1: es el sitio para FEFO o para «solo si hay stock» (patrones.md §10).
- `LoadTime`/`UnloadTime` de un Task Executer: `param(1)` = item, `param(2)` = objeto de origen o
  destino (verificado en LoadTime: sirve para marcar «salió de la cámara»).

## 4. Código dentro de propiedades

Cabecera estándar de un campo de código: `Object current = ownerobject(c); Object item = param(1);`.

| Tarea | API | Nota |
|---|---|---|
| Distribuciones | `triangular(min, max, moda)`, `uniform(min, max)`, `duniform(min, max)`, `exponential(loc, escala)`, `erlang(loc, escala, forma)`, `bernoulli(prob_0_100, si, no)`, `dempirical(tabla)`; último parámetro opcional = stream | **la moda de `triangular` va la última**: `triang(min, moda, max)` de una especificación → `triangular(min, max, moda)`. La media de `erlang` es loc + escala·forma |
| Tiempo | `Model.time` | `time()` está obsoleto. `getentrytime(item)` |
| Matemáticas | `Math.fmod`, `Math.max`, `Math.min`, `Math.floor`, `Math.round`... | |
| Texto | `string.fromNum(n, decimales)`, `.toNum()`, `.length`, `.includes`, `.replace`, `.split` | `"LOT-" + string.fromNum(x, 0)` |
| Color | `item.color = Color.blue;` | `red`, `green`, `orange`, `purple`, `yellow`, `aqua`, `brown`... `Color.random()` |
| Parámetros de modelo | `Model.parameters.Nombre`, `Model.parameters["N"].evaluate(...)` | se crean en la GUI; cada uno tiene trigger OnSet |
| Mensaje diferido | `senddelayedmessage(obj, 0, current)` | para parar objetos o abrir y cerrar puertos desde On Entry/On Exit |
| Reevaluar un pull | `receiveitem(obj)`, `evaluatepullcriteria(obj, item, puerto)` | p. ej. al llegar stock, que la liberación de pedidos vuelva a mirar |
| Estadísticas | `o.stats.input.value`, `.output.value`, `o.stats.content.average`, `.maximum`, `o.stats.staytime.average`, `o.stats.state().getTotalTimeAt(STATE_IDLE)` | **`.max` y `.min` no existen** (no compila). Utilización de un recurso = 1 − idle / tiempo. `stats.totalTravelDistance` no se registra por defecto: distancia ≈ tiempo en `STATE_TRAVEL_EMPTY` + `STATE_TRAVEL_LOADED` × velocidad |
| Etiquetas de un objeto | `o.find(">labels").subnodes` | para recorrerlas |
| Semillas | `randinit(stream, semilla)` | tras `reset` y antes de correr, para los streams 0-99: réplicas reproducibles e independientes. Con «Repeat Random Streams» el reset las devuelve a sus valores por defecto: sin sembrar, todas las réplicas salen iguales. `flexsim_check.Sesion.sembrar(n)` |
| Estado de un objeto | `getstatestr(obj)` (texto: «idle», «utilize», «waiting for operator», «waiting for transport», «releasing»...), `getstatenum(obj)` | lo usa el vigilante de interbloqueos |
| Posición de reset | `setresetposition(obj)` | fija como posición de reset la actual. Colocar un Task Executer por script NO la cambia: cada reset lo deja donde acabó y dos corridas con la misma semilla difieren (medido). `generar_escena.py` lo hace al colocar |
| Salidas de un Combiner | `o.stats.output.value` | cuenta **también los componentes** empaquetados (12 pedidos con 27 palés dan 39). Pedidos = salidas − componentes, o cuéntalos en el Sink |

**Nombres que no se pueden usar como variable** (medido declarando `int <nombre> = 1;` con los
1.214 comandos de la ayuda): `break case continue default else eq for forobjectlayerunder
forobjectsbefore forobjectsbehind forobjecttreeunder if inheritcode iterate local localarray
msgparam msgsendingobject ne param parnode parqty parstr parval return setcurrent setitem setport
switch while`. Ojo con `ne` y `eq` como abreviaturas («n.º de excursiones»). Tampoco existe
`string.find`.

## 4b. Plano: objetos visuales y A*

**Objetos visuales (decorado: no bloquean a nadie).**

| Tarea | API | Nota |
|---|---|---|
| Suelo coloreado / pared 3D | `Object.create("VisualTool")` + `setProperty("VisualDisplay", "Plane")` o `"Cube"` | opciones de VisualDisplay (ayuda): Plane, Cube, Column, Sphere, Imported Shape, Text, Presentation Slide. Clase **«VisualTool» verificada por ejecución** (FlexSimPy) |
| Tamaño, posición, color | `setSize(x, y, z)`, `setLocation(cx, cy, 0, 0.5, 0.5, 0)`, `o.color = Color(r, g, b[, a])` | `Color(r,g,b,a)` es constructor documentado (componentes 0-1). Pared alineada con x: tamaño (largo, grosor, alto) |
| Rótulo visible | `setProperty("ShowName", 1)` | muestra el nombre del objeto en 3D |
| Propiedades de VisualTool | `VisualDisplay`, `Texture`, `TextureXRepeat`, `TextureYRepeat`, `Luminous`, `TextDisplay`, `TextSize`, `PolygonOffsetFactor/Units`, `BillboardMode` | |
| Objeto «Walls» de la librería | módulo People; pilares conectados, puede ser miembro A* | clase sin documentar: no se crea por script con garantías |
| Fondo con un plano | Toolbox > Add > Visual > Model Background | acepta .dwg (ideal), .png/.bmp/.jpg/.gif e .fbx. Solo GUI; se ajusta posición y tamaño en metros |

**A\* (muros lógicos: lo que hace que los recursos rodeen las paredes).** Nombres de clase leídos
en el código fuente del módulo (github.com/flexsim/AStar, `AStar.fsx` y `AStarDLL/*.cpp`).

| Tarea | API | Nota |
|---|---|---|
| Navegador | `createinstance(library().find("?AStarNavigator"), model())` (se llama `AStarNavigator`) | **no** uses `Object.create("AStar::AStarNavigator")`: devuelve otro nodo (medido). Comprueba `getProperty("Class") == "AStar::AStarNavigator"`. `Barrier::assertNavigator` lo busca por el nombre exacto |
| Muro (línea infranqueable) | `Object.create("AStar::Divider")` y moverlo **dentro** del navegador: `d.up = nav;` | la herramienta de la GUI lo crea así (`createinstance(clase, navegador)`). `treenode.up` es asignable (treenode.xml) |
| Registrar el muro | `function_s(d, "assertNavigator");` | callback del Barrier: lo añade a la lista del navegador si aún no está |
| Puntos | `d.setProperty("PathPoints", [[x1, y1, 0], [x2, y2, 0], ...])` | array de puntos en coordenadas del contenedor (el navegador). Una puerta = un hueco entre dos Divider. Polígono cerrado: repite el primer punto al final |
| Redibujar | `function_s(nav, "rebuildMeshes");` | igual que hace la GUI tras editar puntos |
| Recurso que respeta los muros | `contextdragconnection(nav, te, "A")` | `AStarNavigator::dragConnection` con "A" sobre un Task Executer lo añade como viajero; "Q" lo quita. Sobre un objeto fijo, "A" lo convierte en obstáculo |
| Otras clases | `AStar::Barrier` (área, `TravelPatterns`), `AStar::Bridge`, `AStar::PreferredPath`, `AStar::MandatoryPath`, `AStar::Grid` | Bridge / Preferred / Mandatory heredan de Divider |
| Objeto fijo como obstáculo | `contextdragconnection(nav, obj, "A")` (navegador → Rack, Combiner, Processor, Queue) | **verificado** (14/10/2026): sin ella los recursos pasan por encima de estanterías y puestos; con ella los rodean y se detienen en su borde. `generar_escena.barreras_astar` |
| Ruta A\* de un recurso | `AStar.Traveler tr = AStar.Traveler(te); tr.isActive; tr.travelPath[k].cell; AStar.navigator.getLocation(cell)` | verificado: sirve para comprobar que la ruta no cruza muros |
| Posición real de un recurso que viaja | `updatelocations(obj)` y después `getLocation` | sin `updatelocations`, la posición es la del último evento (saltos de decenas de metros) |

Sin muros A\*, una pared visual es solo decorado: los recursos la atraviesan.

## 5. Obsoletos e inexistentes

| Obsoleto | Reemplazo |
|---|---|
| `connect`, `objectconnect`, `defaultdragconnection` | `contextdragconnection()` |
| `node("ruta")` | `model().find()` |
| `nodetomodelpath(n)` | `n.getPath()` |
| `anode(x)` | `tonode(x)` |
| `addlabel(o, n, v)` | `o.labels.assert()` |
| `nodeinsertinto(c)` | `c.subnodes.add()` |
| `createinstance(cls, loc)` | `Object.create()` |
| `nodeadddata(n, t)` | `n.value` / `n.dataType` |
| `getVariable` / `setVariable` | `getProperty` / `setProperty` |
| `time()` | `Model.time` |

**No existen** (`Unknown command`): `Model.addNode`, `Model.connect`, `Model.save`, `Model.build`.
**Guardado:** `cmdsaveas()` y `savetree()` abren un diálogo; `savebyname(model(), ruta)` guarda
sin diálogo (verificado el 13/10/2026).

Comandos que suelen aparecer en especificaciones sin estar verificados: `getparam("entrytime")`,
`insertnodefirst`, `format`. No los copies: compruébalos antes.

## 6. Estado de verificación (14/10/2026)

**Prueba de humo** (`scripts/prueba_humo.py`, 14/10/2026): equipo de operarios con puestos de
capacidad 1, Separator por lote, Combiner con FEFO tirando de un Rack, triggers On Entry/On Exit/
On Reset en Rack, Source y Combiner, `randinit`, `setresetposition`, `getstatestr`. Todo medido
con resultados esperados (utilización teórica, 0 infracciones FEFO, reproducibilidad por semilla).

**Ejecutado por Claude en FlexSim 2027 con FlexSimPy** (references/flexsimpy.md):
- Escena de unos 140 objetos construida, guardada y simulada 24 h.
- Clases: `Source`, `Queue`, `Processor`, `Sink`, `Rack`, `Robot`, `Operator`, `Transporter`,
  `TaskExecuter`, `Dispatcher`, `Conveyor::StraightConveyor`, `VisualTool` y `AStar::Divider`.
  El navegador se crea con `createinstance`.
- Todas las propiedades de las tablas usadas en esa escena (`getProperty` las devuelve).
- `getLocation`/`setLocation` con factores; `StartLocation`/`EndLocation`.
- Clasificación por `SendToPort` con código; robot cargando una cinta; muros A\* y viajeros.
- `savebyname`, `executefsfile` y `createcopy`.
- Tamaños por defecto medidos (tabla en references/flexsimpy.md).

Estado anterior (10/10/2026), conservado como historial:

- **Verificado contra la ayuda:** todo lo de las tablas 2 y 4, y los nombres de propiedad de la
  tabla 3 (leídos en la ayuda online).
- **Ejecutado en FlexSim por el usuario (sin que informara de errores de clase o de sintaxis):**
  `Object.create` con `Source`, `Queue`, `Processor`, `Sink`, `Rack`, `Robot`, `Operator`,
  `Transporter`, `TaskExecuter`, `Dispatcher` y `Conveyor::StraightConveyor`; bloques de
  `setProperty` con código (`SendToPort`, `TransportRef`, `OperatorRef`); `getLocation`/
  `setLocation` con factores; `StartLocation`/`EndLocation`; y las conexiones con cintas.
  - Lo único que falló fue el orden: conectar las cintas antes de colocarlas (errores.md #12).
  - La valoración del usuario fue «mucho mejor», pero no ha confirmado explícitamente que la
    clasificación por etiqueta reparta bien.
- **Leído en el código fuente, sin ejecutar:** las clases y callbacks de A\* de la sección 4b.
- **Sin verificar entonces** (después verificado con FlexSimPy salvo `AvailableOnStart` y lo de
  `StartLocation`): `executefsfile`, `MaxContent` en Rack, `AvailableOnStart` como interruptor de
  escenarios, la clase `"VisualTool"`, las dimensiones de rack por propiedad (`NumBays`, `BaySize`,
  `NumLevels`, `LevelSize`), y si `StartLocation` es absoluto o relativo a la `location` de la
  cinta. Con la cinta en (0,0,0) da igual.
- **Erratas de la ayuda:** el ejemplo de `contextdragconnection` trae `subnodes3]`.
