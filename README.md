# Listado de emergencias en vivo — Coquimbo a O'Higgins

Listado compacto (lluvia DMC, boletines DMC, emergencias MOP, cortes eléctricos y cauces DGA) para insertar por URL en ArcGIS Experience Builder.

- **GitHub Pages** aloja `index.html`.
- **GitHub Actions** consulta cada 15 minutos la API de la DMC (con tu token guardado como secreto) y la de emergencias MOP, y publica `datos/ema.json` y `datos/mop.json` junto al listado.
- El listado lee esos JSON y consulta directo, cada 5 minutos, las capas ArcGIS Online (boletines DMC, cortes eléctricos, DGA).

## Puesta en marcha (una sola vez, ~10 minutos)

1. **Crear el repositorio.** En GitHub: *New repository* → nombre `emergencias` → **Public** (GitHub Pages gratis requiere repositorio público; el token no queda expuesto porque va como secreto) → *Create*.
2. **Subir los archivos.** *Add file → Upload files* y arrastra `index.html`, `README.md` y la carpeta `scripts`. Luego crea el flujo: *Add file → Create new file*, escribe como nombre `.github/workflows/actualizar.yml` y pega el contenido de ese archivo. (Se crea a mano porque algunos sistemas ocultan las carpetas que empiezan con punto al arrastrar.)
3. **Guardar el token como secreto.** *Settings → Secrets and variables → Actions → New repository secret*:
   - `DMC_USUARIO` = tu correo registrado en la DMC
   - `DMC_TOKEN` = tu token
4. **Activar Pages.** *Settings → Pages → Build and deployment → Source:* **GitHub Actions**.
5. **Primera ejecución.** *Actions → Actualizar listado de emergencias → Run workflow*. En 1–2 minutos el paso *deploy* muestra la URL, del tipo `https://TU_USUARIO.github.io/emergencias/`.
6. **Revisar.** Abre la URL. El pie debe decir "DMC · MOP · Electricidad · DGA · lluvia DMC hh:mm". Si dice "Sin respuesta: EMA", abre la ejecución en *Actions* y lee la línea `EMA:` del paso *Descargar*.

## Insertar en la Experience

Widget **Insertar** → **Por URL** → pega `https://TU_USUARIO.github.io/emergencias/`. Tamaño sugerido 380 × 560 px o más.

Si prefieres el modo **Código**, pega solo esta línea (cabe de sobra en el límite de 8 KB):

```html
<iframe src="https://TU_USUARIO.github.io/emergencias/" width="100%" height="100%"></iframe>
```

El modo Código no admite el listado completo: tiene un límite de 8 KB y no ejecuta `<script>`.

## Ajustes

En `index.html`, bloque `CONFIG`: minutos de refresco, días de emergencias MOP, regiones, mm mínimos para mostrar una estación y la URL opcional de la capa `estado_quebradas` del conector. En `.github/workflows/actualizar.yml`, la línea `cron` define cada cuánto se consulta la DMC.

## Notas

- GitHub puede retrasar las tareas programadas varios minutos en horas de alta demanda; la hora de la lluvia DMC se muestra en el pie.
- GitHub desactiva las tareas programadas de un repositorio público tras 60 días sin cambios; se reactivan con un clic en *Actions*.
- La API de la DMC entrega "hoy" y "ayer" como días UTC (se reinician a las 21:00 de Chile). El listado muestra la suma para no perder la lluvia de la tarde.
- Si el certificado del servidor de la DMC no se puede verificar, el script lo lee igual y deja el aviso en `datos/ema.json`.
