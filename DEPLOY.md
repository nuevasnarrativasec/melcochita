# Despliegue en Render — Melcochómetro

El Melcochómetro es un backend **FastAPI (Python)** que llama a la API de
OpenAI, no un sitio estático: necesita un servidor con la variable de
entorno `OPENAI_API_KEY`. Estas instrucciones lo dejan corriendo en Render
con una URL pública.

## Requisitos

- El repositorio ya subido a GitHub (`nuevasnarrativasec/melcochita`).
- Una cuenta en Render (https://render.com — el plan Free alcanza para la demo).
- Tu `OPENAI_API_KEY` (`sk-...`).

## Opción A — Blueprint (recomendada, usa `render.yaml`)

1. Entra a https://dashboard.render.com y elige **New → Blueprint**.
2. Conecta tu cuenta de GitHub y selecciona el repo **melcochita**.
3. Render leerá el `render.yaml` del repo y propondrá un servicio web
   llamado **melcochometro**. Confirma (**Apply**).
4. En la configuración del servicio, agrega la variable de entorno marcada
   como secreto: **`OPENAI_API_KEY`** = tu key `sk-...`
   (está declarada con `sync: false`, así que Render la pide manualmente y
   nunca queda en el repo).
5. Render hará el build (`pip install -r requirements.txt`) y arrancará con
   `uvicorn app:app --host 0.0.0.0 --port $PORT`. Al terminar te da una URL
   pública tipo `https://melcochometro.onrender.com`.

## Opción B — Servicio web manual (sin Blueprint)

1. **New → Web Service** y conecta el repo **melcochita**.
2. Configura:
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app:app --host 0.0.0.0 --port $PORT`
3. En **Environment** agrega `OPENAI_API_KEY` = tu key `sk-...`.
4. **Create Web Service**.

## Notas importantes

- **La key debe estar configurada antes del primer arranque**: `app.py`
  carga `OPENAI_API_KEY` al iniciar el servidor; si falta, el servicio no
  levanta. Si el primer deploy falla por esto, agrega la variable y usa
  **Manual Deploy → Deploy latest commit**.
- **Plan Free**: el servicio "duerme" tras ~15 min de inactividad y la
  primera petición tras dormir tarda unos segundos en responder. Para la
  reunión, abre la URL 1–2 minutos antes para "despertarlo".
- El endpoint es público y sin login (así viene el MVP). La key de OpenAI
  vive solo en el servidor; nunca se expone al navegador.
- El frontend de `web/` es de prueba (sin diseño final); sirve para
  demostrar el flujo completo en la reunión.

## Probar localmente antes de la reunión (opcional)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # edita .env y pon OPENAI_API_KEY=sk-...
uvicorn app:app --reload  # http://127.0.0.1:8000
```
