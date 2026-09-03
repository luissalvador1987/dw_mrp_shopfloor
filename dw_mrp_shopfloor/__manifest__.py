{
    'name': "Taller de Fabricación (Shop Floor) para MRP",
    'summary': "Pantalla táctil para operarios: iniciar/pausar/finalizar órdenes de trabajo, "
               "ver materiales, instrucciones y escanear lotes — sobre el MRP de Community.",
    'description': """
Le agrega al módulo de Fabricación (Community) la interfaz de "Taller" que hoy es exclusiva de
Odoo Enterprise (``mrp_workorder``), sin reemplazar ni duplicar nada del motor de Fabricación: usa
directamente los mismos modelos y botones que ya trae Odoo (``mrp.workorder.button_start`` /
``button_pending`` / ``button_finish``, el bloqueo de centros de trabajo, el registro de tiempos en
``mrp.workcenter.productivity``), solo les pone encima una pantalla pensada para tocar con el dedo
en una tablet o pantalla táctil de planta.

Qué incluye:

* **Selector de Centro de Trabajo**: tarjetas grandes, una por centro de trabajo, con la cantidad de
  órdenes de trabajo pendientes.
* **Cola de órdenes**: lista de las órdenes de trabajo listas o en curso de ese centro, en el orden
  en que hay que hacerlas.
* **Pantalla de ejecución**: producto y cantidad a fabricar bien grandes, cronómetro en vivo, y
  botones grandes Iniciar / Pausar / Finalizar — llaman directamente a los métodos nativos de Odoo,
  así que el tiempo registrado es el mismo que ve Contabilidad/Costos y el que muestra cualquier
  reporte estándar de Fabricación.
* **Materiales**: la lista de componentes que pide esta orden de trabajo, cantidad necesaria vs.
  registrada, y un campo para escanear (o tipear) el lote/serie de un componente rastreado — un
  lector de código de barras común (que "escribe" el código y Enter) alcanza, no hace falta
  hardware especial.
* **Instrucciones**: la nota de la operación y la hoja de trabajo (PDF) configuradas en la ruta de
  fabricación, visibles sin salir de la pantalla.
* **Cantidad producida y lote/serie del producto terminado**, con creación de un número de serie
  nuevo si hace falta.
* **Reportar avería / bloquear el centro de trabajo**, con motivo — usa el mismo mecanismo nativo de
  pérdidas (``mrp.workcenter.productivity.loss``) que ya trae Odoo, solo con menos clics.
* **Grupo "Operario de Taller"**: acceso de solo lo necesario para operar el Taller, sin exponer el
  resto del back-office de Fabricación — para dar de alta usuarios de planta sin darles acceso a
  costos, compras, ni configuración.

Honestidad técnica — qué NO incluye, a propósito:

* **Modo sin conexión**: esta primera versión necesita conexión al servidor para cada acción
  (iniciar, pausar, escanear). Un modo realmente offline (cola local y sincronización al reconectar)
  es un desarrollo bastante más grande y queda para una versión futura — no está simulado acá.
* **Hardware IoT** (calibres digitales, pedales, cámaras vía IoT Box): depende de la app Enterprise
  de IoT Box y de hardware físico que no está disponible para desarrollar ni probar contra un
  dispositivo real — no se ofrece un botón que "parecería" andar pero no tendría con qué
  conectarse. Un lector de código de barras USB/Bluetooth normal (que actúa como teclado) sí
  funciona con el campo de escaneo de esta pantalla, sin necesitar IoT Box.
* El escaneo de materiales asigna lote/serie por **coincidencia de texto exacto**, no interpreta
  códigos GS1/EPC compuestos (fecha de vencimiento, cantidad embebida, etc.).
    """,
    'version': '18.0.1.0.0',
    'category': 'Manufacturing',
    'author': "Designweblp",
    'maintainer': "Designweblp",
    'website': "https://github.com/luissalvador1987/dw_mrp_shopfloor",
    'support': "luissalvador1987@gmail.com",
    'license': 'OPL-1',
    'price': 100.0,
    'currency': 'USD',
    'images': ['static/description/banner.png'],
    'depends': ['mrp'],
    'data': [
        'security/dw_mrp_shopfloor_groups.xml',
        'security/ir.model.access.csv',
        'views/mrp_shopfloor_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'dw_mrp_shopfloor/static/src/js/**/*',
            'dw_mrp_shopfloor/static/src/xml/**/*',
            'dw_mrp_shopfloor/static/src/scss/**/*',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
