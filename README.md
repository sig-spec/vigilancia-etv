# Vigilancia de ETV · Secretaría de Salud del Guaviare

Aplicación web en **Streamlit** con mapas y análisis de malaria, dengue, leishmaniasis, chikunguña y zika (SIVIGILA),
ovitrampas y encuesta larvaria (Epicollect5). Es **gratis**: corre en Streamlit Community Cloud y guarda los datos
en un repositorio privado de GitHub. Nadie necesita cuenta para consultar; para cargar datos se usa una clave.

## Qué tiene

| Página | Contenido |
|---|---|
| **Casos** | Mapa por vereda y barrio, canal endémico por cuartiles, casos por año, pirámide de edad y sexo, especie o clasificación, casos por municipio, tabla descargable |
| **Análisis espacial** | Radio de acción (buffer) con área cubierta, población DANE y ovitrampas dentro; conglomerados espacio-temporales; mapa de calor; incidencia de dengue por barrio; persistencia; estratificación de riesgo |
| **Aedes · ovitrampas** | IPO, mapa de trampas por clase de IPO, IPO por barrio, serie mensual |
| **Encuesta larvaria** | Índices de Breteau, de vivienda y de recipientes, pupas, mapa por barrio, tipos de recipiente, pacientes con síntomas |
| **Cargar datos** (con clave) | SIVIGILA (.xls/.xlsx/.csv), ovitrampas, todos los CSV de Epicollect5, historial de cargues y asignación de lugares sin ubicar |

Cada gráfico tiene un botón de cámara (arriba a la derecha) para descargarlo en PNG. Las tablas se descargan en CSV.

## Publicarla (una sola vez, unos 15 minutos)

1. **GitHub**: cree una cuenta (gratis) y un repositorio **privado**, por ejemplo `vigilancia-etv`. Suba todo el contenido de esta carpeta
   (en la página del repositorio: *Add file → Upload files*, arrastre las carpetas y archivos). **No suba** `.streamlit/secrets.toml`.
2. **Token para guardar cargues**: en GitHub vaya a *Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token*.
   - Repository access: *Only select repositories* → `vigilancia-etv`.
   - Permissions → Repository permissions → **Contents: Read and write**.
   - Copie el token (empieza por `github_pat_`).
3. **Streamlit Community Cloud**: entre a <https://share.streamlit.io> con la misma cuenta de GitHub → *Create app* →
   elija el repositorio, rama `main` y archivo `app.py`. En *Advanced settings → Secrets* pegue:

   ```toml
   CLAVE_CARGUE = "una-clave-larga-para-quien-carga"
   # CLAVE_CONSULTA = "clave-para-ver"   # opcional: quítele el # si también quiere clave para consultar

   [github]
   token = "github_pat_xxxxxxxxxxxxxxxx"
   repo = "su-usuario/vigilancia-etv"
   branch = "main"
   ```
4. *Deploy*. Queda una dirección como `https://vigilancia-etv-guaviare.streamlit.app` (puede cambiar el nombre en *Settings*).
5. En la app, en *Settings → Sharing*, deje **"This app is public"** si quiere que cualquiera con el enlace la vea
   (el código y los datos siguen privados en GitHub), o restrinja por correo.

## Cómo se guardan los datos

- `datos/base/` trae la base consolidada PNEET 2019–2026.
- Cada cargue se guarda en `datos/cargue/` y **reemplaza** a la base para el mismo evento y año (casos) o el mismo mes
  (ovitrampas y encuesta). En *Cargar datos → Datos en la base* puede quitar un cargue y volver a la base.
- Cada cargue queda como un commit en el repositorio: hay historial de quién cargó qué y cuándo, y se puede revertir.
- Si no configura el token, la app funciona, pero los cargues se pierden cuando Streamlit reinicia la app.

## Privacidad

- No se guardan nombres, documentos, teléfonos ni direcciones: de cada caso solo se conserva semana, lugar (vereda o barrio),
  sexo, grupo de edad, hospitalización, condición final, especie o clasificación y coordenadas.
- Mantenga el repositorio **privado**. La página de cargue avisa si el repositorio quedó público.

## Correr en un computador

```bash
pip install -r requirements.txt
streamlit run app.py
```

Para probar el cargue, cree `.streamlit/secrets.toml` con `CLAVE_CARGUE = "..."`.

## Recomendaciones para los archivos

- **SIVIGILA**: suba la exportación tal cual. La app reconoce las columnas de la ficha (cod_eve, año, semana, nmun_proce, vereda_, bar_ver_,
  esp_pla, ajuste_, lat_dir, long_dir…). Si alguna no se reconoce, se puede elegir a mano.
- **Epicollect5**: exporte en CSV y suba todos los archivos (form-1 y las ramas) **sin abrirlos en Excel**; Excel daña las coordenadas
  y borra respuestas.
- Los lugares de SIVIGILA que no coinciden con ninguna vereda o barrio se asignan una vez en *Sin ubicar* y quedan guardados.
