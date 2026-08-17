# Melcochómetro — MVP web

Generador de "chapas" (apodos humorísticos) al estilo del humorista peruano
Melcochita, entrenado sobre un corpus real de chapas verificadas. Este
paquete contiene el MVP funcional: backend FastAPI + motor generativo +
frontend de prueba mínimo (sin diseño final).

## Arquitectura

```
navegador (web/)  →  FastAPI (app.py)  →  motor (src/generar_chapa.py)  →  OpenAI API
```

- **`app.py`**: expone `POST /generar` y `POST /feedback`, sirve el frontend
  estático (`web/`), y es el único lugar donde se usa `OPENAI_API_KEY`.
- **`src/generar_chapa.py`**: el motor generativo. Dado un input del
  usuario, genera candidatos con OpenAI (Structured Outputs), los filtra
  por seguridad, calcula un scoring de 6 dimensiones y elige el mejor
  candidato. Ya está validado — **no se debe modificar sin coordinar**
  (ver `HANDOFF.md`).
- **`data/analysis/adn_humoristico_v2.csv`** y
  **`data/corpus/chapas_unicas_gold.csv`**: los únicos dos archivos de
  datos que el motor lee en tiempo de ejecución (repertorio de
  patrones/operaciones habilitados para generar, y el listado de chapas
  reales del corpus, usado para verificar que ninguna chapa generada sea
  una copia literal).
- **`web/`**: frontend de referencia (HTML/CSS/JS sin frameworks). Es
  deliberadamente simple — el programador puede reemplazarlo por completo
  (ver `HANDOFF.md`).

La API key de OpenAI **nunca** llega al navegador: se carga una sola vez
al iniciar el servidor desde `.env` y se usa exclusivamente server-side.

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Variable de entorno

Copia `.env.example` a `.env` y coloca ahí la API key real:

```bash
cp .env.example .env
# editar .env y poner: OPENAI_API_KEY=sk-...
```

`.env` nunca debe subirse a ningún repositorio (ya está en `.gitignore`).

## Ejecución local

```bash
uvicorn app:app --reload
```

Por defecto queda disponible en **http://127.0.0.1:8000/** — esa misma
URL sirve el frontend (`GET /`) y los endpoints (`POST /generar`,
`POST /feedback`).

## `POST /generar`

Genera UNA chapa a partir de 4 señales sobre una persona.

**Request** (`application/json`):

```json
{
  "nombre_o_apodo": "Eduardo",
  "caracteristica": "pelo despeinado",
  "costumbre": "siempre llega tarde",
  "objeto_que_siempre_usa": "lentes",
  "origen": "primera"
}
```

- `nombre_o_apodo`, `caracteristica`, `costumbre`, `objeto_que_siempre_usa`:
  `string` (pueden llegar vacíos — el backend NO rechaza campos vacíos;
  la regla "nombre obligatorio + al menos 2 de los otros 3" es una
  **validación del frontend actual** en `web/script.js`, no del backend).
- `origen`: `"primera"` o `"otra_chapa"` (opcional, default `"primera"`).
  Solo afecta qué contador anónimo se incrementa (ver más abajo); no
  cambia la generación.

**Response 200**:

```json
{ "chapa": "peluca de lechuga de reloj despertado" }
```

Solo se devuelve el texto de la chapa. Nunca se exponen scoring, patrón,
operación, candidatos internos ni datos del corpus.

**Errores**: `502` si falla OpenAI o no se logró generar ninguna chapa
válida, `500` ante un error interno inesperado. El `detail` del error es
siempre un mensaje genérico, nunca información técnica.

## `POST /feedback`

Registra un voto anónimo sobre la última chapa mostrada.

**Request**:

```json
{ "valor": "positivo" }
```

`valor` es `"positivo"` o `"negativo"`. No se envía la chapa ni ningún
dato del formulario — el voto es completamente anónimo.

**Response 200**: `{ "ok": true }`

## Métricas anónimas

Cada `POST /generar` exitoso incrementa `generacion_exitosa` (y también
`clic_otra_chapa` si `origen="otra_chapa"`); cada `POST /feedback`
incrementa `feedback_positivo` o `feedback_negativo`. Se guardan como
contadores agregados en `outputs/metricas_anonimas.json`, **creado
automáticamente** por el backend en el primer evento (no hace falta
crearlo a mano ni existe en este paquete). Nunca contiene nombres,
inputs del formulario, chapas generadas, IP ni ningún dato identificable
— son 4 números. No se usan cookies de seguimiento.

## Archivos necesarios en tiempo de ejecución

```
app.py
requirements.txt
.env                                       (creado por ti, no viene en el paquete)
src/generar_chapa.py
data/analysis/adn_humoristico_v2.csv
data/corpus/chapas_unicas_gold.csv
web/index.html
web/style.css
web/script.js
```

`outputs/metricas_anonimas.json` se crea solo — no hace falta incluirlo
ni crearlo manualmente.

## Frontend de referencia

`web/index.html` + `web/style.css` + `web/script.js` es un frontend
funcional pero **sin diseño final** — pensado para pruebas, no para
publicarse tal cual. Ver `HANDOFF.md` para qué se puede/no se puede
cambiar.
