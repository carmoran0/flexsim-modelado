# Automatizar y hacer más fácil la construcción

Opciones investigadas en la ayuda de FlexSim 2027. Indica qué se puede hacer por script y qué
requiere la GUI. Nada de esto se ha ejecutado salvo donde se dice.

## Índice
0. Ejecutar y verificar tú mismo en FlexSim real (FlexSimPy) → references/flexsimpy.md
1. Generar el script en vez de escribirlo a mano
2. Ejecutar bloques sin copiar y pegar (`executefsfile`)
3. Verificar nombres de clase dudosos
4. Llegadas por franjas horarias (oleadas, turnos)
5. Escenarios: Model Parameters + Experimenter
6. Cambios masivos de propiedades (SQL sobre objetos)
7. Datos desde CSV o Excel
8. Muros, puertas y recorridos: A\*
9. Prioridades y FEFO: Lists
10. Lo que sigue siendo de la GUI

---

## 1. Generar el script

Para más de unos pocos objetos, describe la escena en Python con `scripts/generar_escena.py`
(objetos, colocación, cintas, conexiones, propiedades) y genera desde ahí. Ventajas:
- Los nombres nunca se desincronizan entre crear, colocar, conectar y lógica.
- El orden crear → colocar → conectar sale siempre bien.
- Cada cambio se hace en un sitio y se regenera.

Guarda el fichero de escena junto a los entregables del usuario. Para cambiar la escena, se edita
el fichero de escena, no el `.flexscript` generado.

## 2. Ejecutar bloques sin copiar y pegar

`executefsfile("C:/ruta/bloque.fs", 1)` carga y ejecuta un fichero de FlexScript (con
`direct = 1`, la ruta se usa tal cual). El generador escribe un `.fs` por bloque y un
`EJECUTAR_<prefijo>.txt` con una línea por bloque: el usuario pega esas líneas en la Script
Console.
- Usa rutas con `/`.
- La ayuda lo marca «For developer use». Si falla, vuelve a pegar los bloques a mano.
- Cada fichero se analiza por separado, así que un error de sintaxis en uno no impide ejecutar
  los demás (esperado, sin probar).

## 3. Verificar nombres de clase dudosos

La propiedad general `Class` devuelve el nombre de clase de un objeto. Pide al usuario que
arrastre uno desde la librería y ejecute en la consola:

```flexscript
model().find("Divider1").as(Object).getProperty("Class")
```

El resultado es el string exacto para `Object.create`. Sirve para módulos (A\*, AGV, People...)
cuyos nombres de clase no aparecen en la ayuda.

## 4. Llegadas por franjas horarias

`InterArrivalTime` es de tipo Code. Plantilla para oleadas diarias (ajusta las horas, la
ventana y el ritmo, que son datos de la escena):

```flexscript
double dia = 86400; double ventana = 7200; double ritmo = 30;
double t = Math.fmod(Model.time, dia);
double s1 = 21600; double s2 = 46800; double s3 = 68400;
if ((t >= s1 && t < s1 + ventana) || (t >= s2 && t < s2 + ventana) || (t >= s3 && t < s3 + ventana)) {
    return exponential(0, ritmo, 21);
}
if (t < s1) { return s1 - t; }
if (t < s2) { return s2 - t; }
if (t < s3) { return s3 - t; }
return dia - t + s1;
```

Alternativas en la GUI:
- *Arrival Schedule* del Source: tabla de horas, cantidades y etiquetas.
- *Time Tables*: paradas programadas de objetos (turnos, descansos).

## 5. Escenarios: Model Parameters + Experimenter

- El Experimenter genera escenarios cambiando **parámetros de modelo**: un trabajo
  *Experiment* lista los escenarios y las réplicas, uno *Optimization* busca un objetivo y uno
  *Range Based* recorre rangos.
- En código, un parámetro se lee con `Model.parameters.Nombre`.
- Cada parámetro tiene un trigger **OnSet**, que se ejecuta al cambiarlo y en cada Reset. Recibe
  la referencia, el valor nuevo, el valor anterior y un indicador de reset. En el OnSet se aplica
  el cambio, por ejemplo
  `model().find("Cola").as(Object).setProperty("MaxContent", param(2));`.
- Para variar el número de recursos sin crear ni borrar objetos: crea el máximo de recursos y
  activa o desactiva el sobrante con `AvailableOnStart` en el OnSet (sin probar).
- Crear parámetros o trabajos del Experimenter por script **no está documentado**: se hace en la
  GUI. El script sí puede dejar preparado todo lo que esos parámetros controlan.

## 6. Cambios masivos de propiedades

Las *Property Tables* muestran el modelo como una tabla SQL de objetos:

```flexscript
Table.query("UPDATE Objects() SET MaxSpeed = 2 WHERE 'Carretillas' IN Groups");
```

Sirve para aplicar una configuración a muchos objetos a la vez (por grupo, clase o nombre). Una
property table también puede guardar una configuración en una Global Table y restaurarla con
«Update from Global Table», lo que da una forma rápida de cambiar de escenario a mano.

## 7. Datos desde CSV o Excel

- `importtable(nodoTabla, "C:/ruta/datos.csv", 1, 1)` carga un CSV en una tabla.
- Comandos `excelopen`, `excelimporttable`... y la herramienta *Excel Interface*.
- Así el código de las propiedades puede leer parámetros de una Global Table, p. ej.
  `Table("Parametros")["Torno"]["Tmedio"]`, en vez de llevarlos escritos. Crear la Global Table
  es un paso de la GUI. Compensa cuando los datos van a cambiar a menudo.

## 8. Muros, puertas y recorridos: A\*

- Los objetos **Barrier** (zona prohibida, `TravelPatterns`) y **Divider** (línea infranqueable,
  `PathPoints` = array 2D de puntos) definen muros.
- **Bridge**, **Preferred Path** y **Mandatory Path** (subclases de Divider, con `ConditionalRule`)
  sirven para pasos, puertas y pasillos preferentes.
- El **A\* Navigator** se añade solo al poner el primer objeto A\*.
- Los Task Executers solo respetan los obstáculos si usan el navegador A\* (propiedad
  `Navigator`). Los objetos fijos conectados al A\* también cuentan como obstáculo.
- Por script (probado en generación, no ejecutado): las clases salen del código fuente del módulo
  (`AStar::AStarNavigator`, `AStar::Divider`...); `generar_escena.py` crea el navegador, mete cada
  Divider dentro, fija `PathPoints` y conecta los recursos. Ver api.md §4b y patrones.md §9.
- Paredes visuales con VisualTool Cube y suelos con Plane; fondo con el plano en PNG (sin
  rótulos) generado por `png_fondo`, que se carga a mano en Model Background.

## 9. Prioridades y FEFO: Lists

- Las *Lists* reemplazan las conexiones por puertos con consultas SQL. Los objetos de origen
  empujan items a una Item List (pick option de Send To Port) y el de destino tira de ella con
  una consulta (pick option de Pull Strategy), por ejemplo `ORDER BY caducidad ASC` para FEFO, o
  `WHERE tipo = 3`.
- Requiere que los items esperen en algún sitio: un almacén con `MinimumDwellTime` 0 suelta
  todo enseguida y no deja nada que priorizar.
- Crear Global Lists por script no está documentado: se configuran en la GUI.

## 10. Lo que sigue siendo de la GUI

- Triggers: **ya no** (api.md §3: nodo `variables/<trigger>` por script). Sí sigue siendo de la
  GUI editar uno con la lista de opciones.
- Parámetros de modelo y trabajos del Experimenter.
- Global Lists, Global Tables, Time Tables y MTBF/MTTR.
- Dashboards y paneles de rendimiento.
- Guardar (Ctrl+S).

Documenta en la guía de la escena dónde va cada uno y, cuando se pueda, deja el código listo
para pegar.
