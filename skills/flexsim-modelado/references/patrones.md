# Patrones de construcción de escena

Patrones generales, probados en una escena real con unos 60 objetos, cintas, robots, operarios
y carretillas. Los nombres de los ejemplos son genéricos: sustitúyelos por los de cada escena.
`scripts/generar_escena.py` ya genera todos estos patrones.

## Índice
1. Orden de bloques: crear → colocar → conectar → propiedades
2. Crear de forma repetible
3. Colocar: pegados sin transporte, huecos solo con transporte
4. Cintas
5. Conectar de forma repetible (marcas en etiquetas)
6. Recursos: operarios, carretillas, AMR, robots
7. Lógica por propiedades *Code*: ruteo, etiquetas, transporte
8. Comprobaciones visuales al entregar
9. Plano: geometría única, suelos, paredes y A*
10. Operación realista (almacenes y logística)
11. Patrones listos en `generar_escena.py`
12. Validar resultados: vigilante, réplicas y prueba de humo
13. Estaciones reservadas y cadena de custodia

---

## 1. Orden de bloques

```
Crear (temáticos, también suelos y paredes) → Propiedades que cambian el tamaño (dimensiones de racks)
→ Colocar → Geometría del plano → Conectar → A* (navegador, muros, miembros) → Propiedades
```

- **Colocar antes de conectar, por las cintas.** Al conectar con `"A"` una cinta con otro
  objeto, FlexSim crea en ese momento una *Entry/Exit Transfer* en el punto de la cinta más
  cercano. Si después mueves los extremos de la cinta, la transferencia **no se mueve**. Puede
  quedar al final o fuera de la cinta, y la simulación se detiene con *«EntryTransferN has a
  range that extends too far to the end of the conveyor»*. Su posición no se puede corregir por
  script.
- **Las propiedades al final**, en bloques separados, porque son lo más frágil (nombres de
  propiedad, código dentro de texto). Así un fallo ahí no deja la estructura a medias. Pon
  primero lo imprescindible (lógica) y después lo opcional (tiempos, escenarios).
- Cada bloque lleva la cabecera `/* BLOQUE N - qué hace */` y es auto-contenido: localiza lo que
  necesita con `model().find()`. Las variables locales no sobreviven entre ejecuciones sueltas de
  la consola.
- Sin funciones propias: FlexScript no las admite en la Script Console.
- Si hay FlexSim y FlexSimPy, ejecuta cada bloque con un `return "OK";` final para saber si
  terminó: "OK" = terminó; None = excepción; 0.0 = no compila (references/flexsimpy.md).

## 2. Crear de forma repetible

```flexscript
treenode tTorno = model().find("Torno");
if (!objectexists(tTorno)) {
    tTorno = Object.create("Processor");
    tTorno.name = "Torno";
}
```

Pegar el bloque dos veces no duplica nada. No se posiciona aquí: de eso se encarga el bloque de
colocación.

## 3. Colocar

**Regla anti-teletransporte.** Si dos objetos se pasan items con una conexión `"A"` sin
`UseTransport`, el item salta al instante. Si están separados, se ve un salto. Por tanto:

- Los pares **sin transporte** van **pegados** (hueco de unos 0,5 m entre bordes).
- Solo hay **huecos** donde algo cubre la distancia: una cinta, o un Task Executer
  (operario, carretilla, AMR, robot) con `UseTransport = 1` en el origen.
- Revisa la lista de conexiones buscando pares separados sin cinta ni transporte. Es el fallo
  visual más habitual.

**Colocar en tiempo de ejecución, encadenando desde un ancla.** El tamaño por defecto de cada
clase es desconocido y `location` no es el centro, así que no se pueden poner coordenadas fijas
y esperar que encajen. Usa factores sobre el tamaño real:

```flexscript
treenode tA = model().find("Entrada");
if (objectexists(tA)) { tA.as(Object).setLocation(0, 0, 0, 0.5, 0.5, 0); }          /* ancla: centro en (0,0) */
treenode tB = model().find("Torno");
treenode rB = model().find("Entrada");
if (objectexists(tB) && objectexists(rB)) {
    Vec3 eB = rB.as(Object).getLocation(1, 0.5, 0);                                   /* borde derecho de Entrada */
    tB.as(Object).setLocation(eB.x + 0.5, eB.y, 0, 0, 0.5, 0);                        /* borde izquierdo de Torno a 0,5 m */
}
```

- Para colocar a la izquierda, lee `getLocation(0, 0.5, 0)` y fija con factor x = 1.
- Para recursos, coloca el centro relativo al centro de su puesto: `getLocation(0.5, 0.5, 0)`
  más un desplazamiento.
- Robots: entre el objeto que suelta y la cinta, a 1–1,5 m del borde y desplazados en y. Su
  base no se mueve, así que todo lo que manipulan tiene que quedar a su alcance.
- Si un objeto se coloca según varios (p. ej. «12 m después del rack que más sobresale»),
  calcula con `Math.max` sobre sus `getLocation(1, 0.5, 0).x`.
- Usa x = 0/1 para bordes e y = 0.5 para el centro: el sentido del factor y no está aclarado.
- **Para encadenar en y (o en cualquier eje) sin depender de factores**, trabaja con el centro y
  el tamaño: `Vec3 c = r.getLocation(0.5, 0.5, 0); Vec3 s = r.size;` y coloca el centro del
  siguiente en `c.y - s.y / 2 - hueco - o.size.y / 2` con `setLocation(x, y, 0, 0.5, 0.5, 0)`.
  Es lo que hace `encadenar(..., dir="-y")` en `generar_escena.py`. Sirve para líneas norte-sur,
  como una columna de picking estrecha.
- El bloque de colocación es idempotente: se puede volver a ejecutar para recolocar.

## 4. Cintas

```flexscript
double zCinta = 0;   /* altura; 0.8-1 para cintas elevadas */
treenode c1 = model().find("Cinta1");
treenode s1 = model().find("Torno");
treenode d1 = model().find("Salida");
if (objectexists(c1) && objectexists(s1) && objectexists(d1)) {
    Vec3 a1 = s1.as(Object).getLocation(1, 0.5, 0);
    Vec3 b1 = d1.as(Object).getLocation(0, 0.5, 0);
    c1.as(Object).location = Vec3(0, 0, 0);
    c1.as(Object).setProperty("StartLocation", [a1.x, a1.y, zCinta]);
    c1.as(Object).setProperty("EndLocation", [b1.x, b1.y, zCinta]);
}
```

- **Cinta en `location = (0,0,0)` antes de fijar los extremos.** La ayuda no aclara si
  `StartLocation`/`EndLocation` son absolutos o relativos a la cinta; con la cinta en el origen
  da igual.
- Cinta entre dos objetos: del borde del origen que mira al destino al borde del destino que mira
  al origen, en el eje dominante (x o y); `cinta_auto` lo calcula con centros y tamaños. Si un robot o un operario carga
  la cinta, deja un hueco al inicio (`a1.x + 3`).
- **Abanico desde un objeto a varias cintas:** desplaza el inicio de cada cinta en y dentro del
  tamaño del origen (`a1.y + f * s1.as(Object).size.y / 2`, con f entre -0,75 y 0,75) para que
  no salgan todas del mismo punto.
- Conectar `objeto → cinta` crea una Entry Transfer y `cinta → objeto` una Exit Transfer. Una
  Exit Transfer puede pedir transporte: conexión `"S"` a un Task Executer y `UseTransport` en la
  transferencia.
- Si una transferencia quedó mal: borra la cinta, vuelve a crearla, colócala y conéctala. En la
  GUI también se arregla arrastrando la transferencia.

## 5. Conectar de forma repetible

En un bloque aparte ya no sirve la marca de «objeto recién creado». Marca cada par con una
etiqueta en **los dos extremos** y conecta solo si falta alguna:

```flexscript
treenode ka = model().find("Torno");
treenode kb = model().find("Cinta1");
if (objectexists(ka) && objectexists(kb)) {
    if (ka.labels.assert("cxA_Cinta1", 0).value == 0 || kb.labels.assert("cxA_Torno", 0).value == 0) {
        contextdragconnection(ka, kb, "A");
        ka.labels.assert("cxA_Cinta1", 0).value = 1;
        kb.labels.assert("cxA_Torno", 0).value = 1;
    }
}
```

- Repetir el bloque no duplica nada. Un objeto recreado pierde sus marcas y se reconecta.
- No compruebes la conexión por los puertos: con cintas, `outObjects` contiene la
  transferencia y no el objeto.
- Un modelo construido sin marcas (versión anterior del script) duplicaría las conexiones:
  empieza un modelo vacío.
- Ramificar = una conexión por par. El **número de puerto** es el orden en que se hicieron las
  conexiones `"A"` desde ese objeto.

## 6. Recursos

| Necesidad | Cómo |
|---|---|
| Equipo (pool) de operarios o carretillas | `Dispatcher` + miembros; conexión `"A"` del Dispatcher a cada miembro |
| Operario que trabaja **en** un Processor | `"S"` Processor ↔ Dispatcher (o el operario); `UseProcessOperators = 1`, `NumProcessOperators = n`, y mejor `OperatorRef` explícito |
| Transporte de A a B (operario, carretilla, AMR, robot) | `"S"` A ↔ recurso; en A: `UseTransport = 1` y `TransportRef` explícito |
| Robot | Task Executer de base fija: igual que un transporte, colocado al alcance del origen y del destino |
| Carretilla | `Transporter`; AMR: `TaskExecuter` (por su forma de AGV) |

**Referencias explícitas por nombre.** Si un Processor usa a la vez operarios y transporte, los
dos buscan por defecto en `centerObjects[1]` y se pisan. Fija ambos campos:

```flexscript
obj.setProperty("OperatorRef", "return model().find(\"Pool_Operarios\");");
obj.setProperty("TransportRef", "return model().find(\"Robot1\");");
```

Con referencias por nombre, las conexiones `"S"` dejan de ser necesarias para la lógica. Mantenlas
de todos modos, porque documentan la relación en la vista 3D.

## 7. Lógica por propiedades *Code*

- **El código va como texto.** Escapa `\` y `"` (`\"`). Ponlo en una sola línea, separando las
  sentencias con espacios. Usa la cabecera `Object current = ownerobject(c); Object item = param(1);`.
  En la GUI el campo aparecerá vacío, pero el código está ahí.
- **Etiquetar items al crearlos.** `SendToPort` del Source se evalúa una vez por item al
  soltarlo: asigna ahí las etiquetas y el color y devuelve `0`. Protege contra la reevaluación
  con `labels.assert("x", inicial)`: si la etiqueta ya tiene valor, no la sobrescribas. (También
  vale un trigger; ver api.md.)
- **Clasificar o rutear por tipo.** La `SendToPort` por defecto devuelve `0` (primer puerto
  libre), así que sin configurarla **todos los items van al primer destino libre**. Guarda el
  destino en una etiqueta y devuelve el puerto:

  ```flexscript
  string destino = item.labels.assert("destino", "").value;
  for (int i = 1; i <= current.outObjects.length; i++) {
      Object o = current.outObjects[i];
      if (o.name == destino || o.up.name == destino) { return i; }
      if (o.outObjects.length > 0) { if (o.outObjects[1].name == destino) { return i; } }
  }
  return 0;   /* o un respaldo por orden de conexión */
  ```

  Las dos comprobaciones extra cubren el caso de que el puerto apunte a una transferencia de
  cinta. Añade como respaldo el puerto según el orden de conexión.
- **Medir tiempos entre dos puntos** (p. ej. tiempo fuera de una zona): en el `SendToPort` del
  primer objeto guarda `t0 = Model.time` en una etiqueta. En el `SendToPort` del segundo, calcula
  `Model.time - t0`, acumúlalo y márcalo; protégelo con una etiqueta de «ya medido».
- **Tiempos de proceso:** `ProcessTime` = `"return triangular(min, max, moda, stream);"`. Usa un
  stream distinto por objeto para que los escenarios sean comparables.
- **Llegadas por franjas horarias:** `InterArrivalTime` con `Math.fmod(Model.time, 86400)` (ver
  automatizacion.md).
- **Triggers por script** (api.md §3): On Entry, On Exit, On Process Finish, On Reset. Úsalos para
  medir (marcas de tiempo, contadores) y para ajustar el objeto al item que entra (lista de
  componentes de un Combiner). Para parar objetos o abrir puertos, `senddelayedmessage`.
- **Contadores en etiquetas = On Reset.** Las etiquetas no vuelven solas a 0 con Reset: cada
  ejecución sumaría a la anterior. Ponlas a 0 en On Reset (no toques las marcas `cx*`).

## 8. Comprobaciones visuales al entregar

Repasa con el usuario o en la vista 3D:
1. ¿Hay algún par conectado, separado, sin cinta y sin transporte? → teletransporte.
2. ¿Cada cinta empieza en el borde de su origen y termina en el de su destino?
3. ¿Los robots alcanzan su origen y su destino?
4. ¿Las transferencias de cinta están en los extremos y no en medio o fuera?
5. ¿Los items cambian de color o de etiqueta donde deben? Con eso se ve si la clasificación
   funciona.

## 9. Plano: geometría única, suelos, paredes y A*

Cuando la escena necesita un plano «con sentido» (zonas, paredes, puertas, muelles):

1. **Una sola fuente de geometría.** Define zonas (rectángulos), muros (segmentos), puertas y
   muelles en el fichero de escena, y genera desde ahí el script de FlexSim **y** el plano 2D
   (`svg_plano`, `png_fondo` de `generar_escena.py`). Así plano y simulación no se desalinean.
2. **Comprueba superficies por programa.** Si la especificación da m² por zona, haz que el
   generador verifique las áreas exactas, que no haya solapes ni huecos (muestreo en rejilla) y
   que el total cuadre con la nave. Un plano que no cuadra no se entrega.
3. **Coloca los objetos dentro de su zona**, con sus playas (colas) delante de la puerta de cada
   sala y las estanterías en filas con pasillos. El tamaño real del rack depende de sus
   propiedades; aplica las dimensiones antes de colocar.
4. **Paredes en dos capas:**
   - *Visual* (VisualTool Cube): se ve, pero no bloquea a nadie.
   - *Lógica* (AStar::Divider dentro de `AStarNavigator`, creado con
     `createinstance(library().find("?AStarNavigator"), model())`), más la conexión «A» del navegador a
     cada Task Executer móvil: los recursos rodean las paredes y pasan por las puertas, y las
     distancias recorridas salen realistas.
   - Puertas = huecos entre Dividers.
   - Robots y objetos fijos no son miembros (no viajan).
5. **Fachada cerrada para A\*.** Dibuja los muelles como huecos en la pared visual, pero en A\*
   usa un perímetro cerrado. Si no, los recursos pueden salir de la nave para rodear un muro.
6. **Variantes de layout en bloques propios** (p. ej. muros cortafuegos solo en un escenario):
   creación, geometría y A\* van en bloques cuyo nombre lo dice, y el usuario los ejecuta o los
   salta.
7. **Suelos de colores por zona** (VisualTool Plane con `ShowName`) sirven de leyenda en 3D. El
   PNG de fondo es opcional (Model Background, a mano).
8. **Rótulos del plano SVG:** con objetos de 2 m y líneas densas, los rótulos chocan. Alterna su
   posición (arriba, abajo, izquierda, derecha) y revisa el SVG en el navegador antes de
   entregarlo.

## 10. Operación realista (almacenes y logística)

Lo que distingue un modelo que «funciona» de uno que se comporta como un almacén de verdad.
Todo probado en FlexSim 2027 con FlexSimPy (5 días simulados de una escena de ~190 objetos).

### 10.1 Balance de capacidad antes de construir

Para cada recurso: **carga = volumen diario × tiempo medio** (media de una triangular =
(a + b + c) / 3) y **capacidad = n.º de unidades × horas de trabajo × 3.600**. Si carga >
~85 % de la capacidad, ese recurso hará cola sin fin. Compruébalo también en las horas punta
(oleadas). Comprueba que **entradas = salidas** de material (si no, el stock se agota o se
desborda en pocos días) y que el inventario inicial cubre el arranque. Con datos que no
cuadran, el modelo se atasca por mucho que la lógica esté bien: presenta las cifras al usuario
y decide con él qué cambia (demanda, tiempos o dotación).

### 10.2 Tiempos fijos solo para manipular; los recorridos los simula FlexSim

Un tiempo como «ubicar un palé: 7-12 min» ya incluye el recorrido. Si además el recurso viaja
por el plano, se cuenta dos veces, y el layout deja de influir. Deja en `LoadTime`/`UnloadTime`
o en `ProcessTime` solo la manipulación (20-60 s para una carretilla), fija velocidades reales
(`MaxSpeed`: carretilla ~2 m/s, AMR ~1,2, a pie ~1,2) y mide el tiempo resultante como KPI.

### 10.3 Entrada por lote: un camión, N palés

El item que llega es la entrega. La descarga, la inspección documental y la cuarentena se
hacen por lote; al liberarse, un `Separator` en modo Split (`unpack` = 0, `splitquantity` con
código) lo convierte en N palés que heredan las etiquetas (familia, lote, caducidad). Varios
muelles = un Processor sin operarios con `MaxContent` = n.º de muelles. `e.separador_lote(...)` (§11).

### 10.4 Stock inicial

Un Source conectado a los racks que crea el inventario en t = 0:
`InterArrivalTime` = `if (current.stats.output.value < N - 1) return 0; return 1e10;` (crea N),
y su `SendToPort` reparte por familia según el número de orden. Sin transporte: es el estado
inicial, no un movimiento.

### 10.5 Pedidos que tiran del stock

- Cada estación de picking es un `Combiner`: puerto 1 = pedido (contenedor); puertos 2.. = un
  rack por familia. En On Entry (puerto 1), lista de componentes desde las etiquetas del pedido
  + `targetcomponentsum` (api.md §3b). `e.estacion_fefo(...)` lo monta entero (§11).
- **FEFO**: `Pull` = 1 y `PullRequirement` que acepta solo el palé libre de caducidad mínima del
  rack de ese puerto; al aceptarlo, marca qué estación lo reservó (`reservado_por` = nombre de
  la estación) y acéptalo siempre para esa misma estación: si dos estaciones pudieran quedarse
  con el mismo palé, una esperaría para siempre. Guarda el mínimo en etiquetas del rack con una clave (instante, contenido, n.º de
  reservas) para no recorrer el rack en cada evaluación. Verificado: los palés consumidos salen
  ordenados por caducidad.
- **Más estaciones que operarios**: mientras las carretillas traen palés a una estación, el
  operario trabaja en otra. Con estaciones = operarios, cada operario espera los recorridos.
- **No transportes información.** Si el «pedido» que entra en la estación es una orden del SGA
  (la estación ya tiene sus bases de palé), conéctalo sin transporte. Un AMR o una carretilla
  por pedido satura la flota justo en las puntas: medido, el cumplimiento en plazo pasó de 94 %
  a 98 % solo con este cambio.
- **Liberar solo con stock** (como un SGA): `PullRequirement` en el objeto que saca pedidos de la
  cartera; deja salir un pedido solo si hay stock libre no comprometido de todo lo que pide y,
  al salir, lo compromete. Contadores en etiquetas del rack: `libres` (+1 al entrar, −1 al
  reservar) y `comprometido` (+n al liberar, −1 al reservar). Cuando entra stock y la
  liberación está parada, `receiveitem(obj)`. Sin esto, un pedido sin stock bloquea una
  estación indefinidamente.
- **Reaprovisionar por posición de inventario**: la familia de cada camión se elige con peso
  mezcla × objetivo / (libres + en camino − comprometido), y nunca hacia una zona sin hueco
  para el lote entero. Reaprovisionar mirando solo el stock físico sobrepide (no ve lo que ya
  viene) y una zona llena bloquea la clasificación de todas.

### 10.6 Llegadas por ventanas y oleadas

`InterArrivalTime` con `Math.fmod(Model.time, 86400)`: si la próxima llegada cae fuera de la
ventana, devolver el tiempo hasta la apertura siguiente (automatizacion.md §4). Así se ven las
puntas reales (p. ej. 240 pedidos en 80 min) en vez de un flujo uniforme.

### 10.7 Puestos con operarios

- Un Processor con `MaxContent` > 1 y operarios de proceso **deja operarios enganchados** en
  «utilize» y el proceso esperando operario (reproducido aislado). Un puesto = un Processor de
  capacidad 1. Un equipo que trabaja junto = `NumProcessOperators` = tamaño del equipo.
  `e.puestos(...)` + `e.equipo(...)` (§11).
- `ProcessTime` = 0 → el puesto no llama a ningún operario (el item pasa sin trabajo).
- Varias mesas alimentadas desde una cola: un robot (o los propios operarios) como transporte
  de la cola a la mesa libre y de la mesa a la cinta de salida; prioridad con `PullRequirement`
  en las mesas (p. ej. el producto de frío primero).
- Varias estaciones pueden cargar **de lado** una misma cinta colectora: conecta cada estación
  a la cinta después de colocarla y la transferencia se crea en el punto más cercano
  (verificado).

### 10.8 Pasillos y A\*

Con el A\* por defecto los recursos se esquivan (evitación de colisiones activada). En un
pasillo donde no caben una carretilla y un recurso parado, la simulación puede quedarse
bloqueada para siempre a mitad de ejecución. Dibuja los pasillos con su anchura real (≥ 2,5-3 m
para carretillas) y, si hace falta, desactiva la evitación (api.md, A\* Navigator). El vigilante
(§12) saca a la luz estos bloqueos: SIN PROGRESO con la carretilla bloqueada como sospechosa.

### 10.9 KPIs dentro del modelo

Etiquetas en el Sink (On Entry): pedidos, en plazo, suma de ciclos, máximos, excursiones...
con un calentamiento (solo pedidos creados después de t₀) y On Reset que las pone a 0. Fuera
del modelo, `flexsim_check.py --consulta` o un ejecutor propio (flexsimpy.md §7) las lee junto
con utilizaciones (`stats.state()`) y colas (`stats.content.average/.maximum`).

## 11. Patrones listos en `generar_escena.py`

Cada uno resuelve un fallo silencioso medido. Úsalos en vez de reescribir la lógica:

| Método | Qué hace | Fallo que evita |
|---|---|---|
| `e.equipo(disp, "Operator", "Operario_", n, usuarios)` | crea Dispatcher + n recursos; conecta Dispatcher → miembros («A») y usuarios → Dispatcher («S»). Devuelve los nombres (colócalos tú) | recursos sin conectar o conectados al revés |
| `e.puestos("Mesa_", n, disp, operarios=1)` | n Processors de capacidad 1 con `UseProcessOperators`, `NumProcessOperators` y `OperatorRef` explícito | operarios enganchados con `MaxContent` > 1 (errores #27); recurso equivocado (#14) |
| `e.estacion_fefo(comb, ["n_a", "n_b"], caducidad="caducidad", equipo=None, al_reservar=[...])` | Combiner que tira de las fuentes conectadas en los puertos 2.. (en el orden de la lista) con FEFO y reservas; On Entry fija `componentlist` y `targetcomponentsum`; On Reset limpia la caché | Combiner en «collecting» (#29); dos estaciones esperando el mismo palé; O(n²) recorriendo el rack |
| `e.separador_lote(sep, "n_unidades")` | Separator en Split con `splitquantity` = etiqueta del lote | lote que sale entero |
| `e.barreras_astar([racks, estaciones, mesas, playas])` | conexión «A» del navegador a cada objeto fijo: A\* lo rodea | recursos que pasan por encima de estanterías y puestos (errores #40) |

Además, el bloque de colocación fija la **posición de reset** de todos los Task Executers
(`setresetposition`): sin eso, cada reset los deja donde acabaron (errores #35).

Los métodos que crean objetos (`equipo`, `puestos`) no los colocan; los que configuran
(`estacion_fefo`, `separador_lote`) esperan el objeto ya creado y conectado. `estacion_fefo`
usa los triggers On Entry y On Reset del Combiner: si necesitas más lógica ahí, añádela con
`al_reservar` o copia el código del método.

## 12. Validar resultados: vigilante, réplicas y prueba de humo

- **Vigilante** (`flexsim_check.py --correr T --vigilar 3600`, o `Sesion.correr(T, vigilar=3600)`):
  simula a trozos y da tres alarmas que FlexSim nunca da:
  - SIN PROGRESO: ningún objeto saca nada durante `--parada` (4 trozos) con items dentro. Lista
    sospechosos con su estado (`getstatestr`): un puesto «waiting for operator» con los
    operarios en «utilize» todo el rato es el fallo #27.
  - ATASCO: un objeto recibe pero no saca nada. Puede ser legítimo (un Combiner que espera
    stock); revisa el estado.
  - CRECE: un objeto acaba cada día con más contenido que el anterior (3 días seguidos): la
    carga supera la capacidad y la cola no se estabilizará.
  No vigila Racks (guardan stock a propósito). En un almacén con noches sin pedidos, sube
  `--parada` (p. ej. 8 h) para no confundir la noche con un bloqueo.
- **Réplicas** (`scripts/replicas.py`): una corrida no es un resultado. Lanza N procesos con
  semillas distintas (`--semilla` en el ejecutor), da media, desviación, IC y cuántas réplicas
  harían falta para la precisión pedida. Para comparar dos escenarios usa `--comparar`: mismas
  semillas en los dos y análisis de la diferencia pareada; «significativa» si el IC no contiene 0.
  Una diferencia menor que el IC no se puede presentar como mejora.
- **Recorridos** (`flexsim_check.py --recorridos 2 --desde 21600`): muestrea cada segundo la
  posición real (`updatelocations`) de cada recurso móvil y cuenta cruces de muros A\* y pasos por
  encima de estanterías, puestos y colas. Hazlo en horas activas (`--desde`): de noche no se mueve
  nada y saldría 0 sin demostrar nada. Debe dar 0 y 0.
- **Prueba de humo** (`scripts/prueba_humo.py`): tras cambiar `generar_escena.py`,
  `flexsim_check.py` o al estrenar una instalación de FlexSim, comprueba en 1 min que los
  patrones siguen dando el comportamiento esperado (ver flexsimpy.md §9).

## 13. Estaciones reservadas y cadena de custodia

Patrón para pedidos que solo puede preparar un subconjunto de puestos (jaula de custodia,
producto peligroso, cliente con requisitos propios), medido con un almacén de 12 estaciones:

- **Marca en el item y en la estación** (`custodia` = 1). El `PullRequirement` del puerto 1 de
  cada estación solo acepta pedidos de su clase y el FEFO de los demás puertos solo palés de su
  clase (mínimo de caducidad separado por clase en la caché del rack).
- **Stock separado por clase**: contadores `libres_c` / `comprometido_c` / `en_camino_c` además de
  los normales, en la liberación, en el FEFO y en la entrada al rack; la reposición elige la clase
  del lote por su cuota (posición custodiada < cuota × posición total), no al azar.
- **Liberar solo si la estación reservada puede aceptarlo** (contador «en curso») y, al terminar,
  `receiveitem()` sobre el que reparte; si no, bloqueo en cabeza de cola (errores #42).
- **Añadir** las estaciones reservadas, no restarlas de las normales (errores #43). Medido: una
  sola jaula preparando de uno en uno dejó los custodiados en plazo al 73 %; dos jaulas que
  comparten un equipo de 2 custodios, al 93 %, con los custodios al 28 % de utilización (esperan
  palés, no trabajo).
- **Doble verificación** = `NumProcessOperators` = 2 con un equipo propio de personal autorizado.
- **Cadena de custodia medible**: contadores por item de cambios de manos (`c_total`) y de los
  hechos por personas (`c_humanas`): +1 en el `LoadTime` de cada recurso móvil (humano si es
  Operator o Transporter) y en el `ProcessTime` de cada puesto con personas (+2 si es doble).
  El pedido suma los suyos y los de sus palés en el Sink. Escaneo en cada cambio (5-15 s),
  precinto en expedición y una probabilidad de incidencia (lote retenido, fallo de escaneo) con
  su tiempo de bloqueo.
