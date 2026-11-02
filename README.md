# ForestGuard Perú

Versión estática de ForestGuard, hecha con HTML, CSS y JavaScript. No necesita
Python, servidor, ni archivos TXT o JSON para abrir y usar el panel.

## Abrir

Abre `index.html` con un navegador. Los registros y archivos adjuntos se guardan
en el almacenamiento local del navegador (IndexedDB); no se suben a un servidor
ni se comparten entre equipos o perfiles de navegador. Puedes descargar los
registros como CSV desde el botón **Exportar CSV**.

La pantalla `login.html` solo informa que esta versión no tiene autenticación.
Un sitio estático no puede proteger datos con una contraseña real; no uses esta
versión para información confidencial o que requiera acceso compartido.

El mapa usa OpenStreetMap y necesita conexión a Internet. El análisis de
fotografías se realiza en el navegador y es orientativo; requiere revisión
humana. La información que estaba en las versiones anteriores de servidor no
se importa automáticamente a este almacenamiento local. Los archivos antiguos
`forestguard.db` y `forestguard_data.json` se conservan como respaldo; esta
versión no los utiliza.
