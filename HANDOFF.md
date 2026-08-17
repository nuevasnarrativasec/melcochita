# HANDOFF — Melcochómetro MVP

Este paquete es el MVP funcional del Melcochómetro, listo para que el
equipo de desarrollo lo integre y despliegue en la infraestructura de
El Comercio. El motor generativo ya pasó por varias rondas de validación
(esquema de análisis del corpus, pilotos, prueba de estrés con 4
perfiles, ajuste de scoring) — funciona y está cerrado. Lo que falta es
diseño visual final e integración con el landing definitivo.

Arranque rápido: ver `README.md`.

## QUÉ PUEDE CAMBIAR EL PROGRAMADOR

Libremente, sin coordinar con nosotros:

- Reemplazar completamente HTML/CSS/JS de `web/` (es un frontend de
  prueba, no el diseño final).
- Integrar el formulario al landing de El Comercio (otro framework,
  otro stack de frontend, como se prefiera).
- Cambiar textos, estilos, copys, branding.
- Adaptar responsive / accesibilidad.
- Integrar analytics del medio (Google Analytics, etc. — el MVP
  actual deliberadamente no lo trae).
- Adaptar el deployment/infraestructura (Docker, el hosting que sea,
  variables de entorno vía su gestor de secretos, etc.).
- Conectar el endpoint `POST /generar` al frontend definitivo que se
  decida.
- Agregar sus propios logs/monitoreo alrededor de `app.py` (mientras no
  se toque la lógica interna descrita abajo).

## QUÉ NO DEBE CAMBIAR SIN COORDINACIÓN

Esto ya fue validado con datos reales (corpus de 73 chapas, prueba de
estrés con 4 perfiles, ajuste de umbral de conexión con el input) — un
cambio aquí puede degradar silenciosamente la calidad de las chapas:

- **`src/generar_chapa.py`** completo: no modificar.
  - El **prompt** del sistema (`construir_system_prompt`).
  - El **scoring** de 6 dimensiones (`correccion_linguistica`,
    `conexion_con_input`, `sorpresa_semantica`, `absurdo_controlado`,
    `adn_melcocha`, `originalidad_vs_corpus`).
  - Los **umbrales** (`UMBRAL_ADN_MELCOCHA`, `UMBRAL_SORPRESA_SEMANTICA`,
    `UMBRAL_ORIGINALIDAD_VS_CORPUS`, y el umbral de conexión en `app.py`).
  - Los **filtros de seguridad** (`filtrar_seguridad`,
    `contiene_palabra_alerta`, la lista `PALABRAS_ALERTA_SENSIBLE`, las
    reglas de contenido prohibido en el prompt).
- **Corpus Gold** y **ADN v2** (`data/corpus/chapas_unicas_gold.csv`,
  `data/analysis/adn_humoristico_v2.csv`): son el resultado de un
  proceso de curaduría humana + validación. No editar su contenido.
- La **lógica de selección del ganador** en `app.py`
  (`_es_elegible_final`, `_prioridad`, `_elegir_ganador`,
  `_generar_resultado`) — decide qué candidato de los generados se
  muestra al usuario.

Si alguna de estas piezas necesita cambiar (por ejemplo, ajustar el
umbral de seguridad, agregar un nuevo mecanismo humorístico, ampliar el
corpus), coordinar con el equipo que construyó el motor antes de tocarlo.

## CONTRATO DEL FRONTEND

Esto es lo único que el landing definitivo necesita saber para
integrarse con el backend — no necesita conocer nada del motor, del
corpus, ni del scoring.

### `POST /generar`

Enviar (siempre los 4 campos de texto; `origen` es opcional):

```json
{
  "nombre_o_apodo": "string",
  "caracteristica": "string",
  "costumbre": "string",
  "objeto_que_siempre_usa": "string",
  "origen": "primera"
}
```

- Los 4 campos de texto deben enviarse siempre (pueden ser `""` si el
  campo quedó vacío — el backend no los valida por longitud/obligatoriedad;
  esa validación vive hoy en `web/script.js` y debe reimplementarse en el
  frontend definitivo: **nombre obligatorio + al menos 2 de los otros 3**).
- `origen`: mandar `"otra_chapa"` cuando el usuario pide otra chapa con
  los mismos datos (para que la métrica anónima cuente ese clic aparte);
  mandar `"primera"` (o simplemente omitirlo) en la primera generación.

Recibir:

```json
{ "chapa": "texto de la chapa generada" }
```

o, ante un error (`502`/`500`):

```json
{ "detail": "mensaje genérico para mostrar al usuario" }
```

El frontend nunca debe intentar leer/mostrar nada más que `chapa` — no
hay otros campos en la respuesta exitosa, y nunca habrá scoring, patrón
ni información del corpus en la respuesta.

### `POST /feedback`

Enviar:

```json
{ "valor": "positivo" }
```

(`"positivo"` o `"negativo"`, nada más — no enviar la chapa ni datos del
formulario).

Recibir: `{ "ok": true }`. Es "fire and forget": el frontend no debe
bloquear la interfaz esperando esta respuesta ni mostrar error si falla.

### Reglas para cualquier frontend nuevo

- La API key de OpenAI nunca debe aparecer en el frontend ni en ningún
  request/response — el backend ya la maneja.
- No hace falta CORS especial si el frontend se sirve desde el mismo
  origen que `app.py`; si se sirve desde otro dominio, el programador
  deberá agregar CORS en `app.py` (no lo trae este MVP).
- No hay autenticación/login — el endpoint es público tal como está.
