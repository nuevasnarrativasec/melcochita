# Integración de la voz de Melcochita

Este paquete agrega la voz de Melcochita al Melcochómetro **sin tocar el
motor** (`src/generar_chapa.py`, scoring, corpus, filtros de seguridad).
Solo se añade un módulo nuevo (`voz.py`), un endpoint en `app.py` y un
pedazo de frontend.

Arquitectura:

```
/generar  ->  chapa pelada  (igual que hoy)         -> pantalla: "SILBATO MOJADO"
/voz      ->  voz.py: marco + ElevenLabs + caché    -> audio: "¡Mi querido… silbato mojado!"
```

El usuario **ve** la chapa pelada y **escucha** la versión enmarcada. El
marco ("mi querido / mi querida / le dicen") lo pone `voz.py`, no el motor.

---

## 1. Archivos

- `voz.py` → va en la **raíz del proyecto**, junto a `app.py` (para que
  `import voz` funcione). Ya lo dejé ahí.
- La caché de audios se crea sola en `outputs/voz_cache/`.

## 2. Variables de entorno (.env)

Agrega a tu `.env` (la key nunca llega al frontend, igual que la de OpenAI):

```
ELEVENLABS_API_KEY=sk_...tu_key...
MELCOCHITA_VOICE_ID=...el voice_id del clon Instant...
# opcional: ELEVEN_MODEL_ID=eleven_multilingual_v2
```

`httpx` ya viene como dependencia de `openai`, así que no hace falta
instalar nada nuevo.

## 3. Cambios en `app.py` (aditivos)

**a)** Junto a los otros imports de FastAPI, agrega `Response`:

```python
from fastapi.responses import Response
```

**b)** Cerca de los otros imports del proyecto, importa el módulo:

```python
import voz  # módulo de voz; no toca el motor
```

**c)** Agrega este endpoint **ANTES** de la línea
`app.mount("/", StaticFiles(...))` (las rutas API deben ir antes del
montaje del frontend estático):

```python
class SolicitudVoz(BaseModel):
    texto: str  # la chapa YA generada por /generar

@app.post("/voz")
def generar_voz(sol: SolicitudVoz):
    try:
        audio = voz.sintetizar_chapa(sol.texto)
    except voz.VozNoConfigurada:
        raise HTTPException(status_code=503, detail="Voz no configurada.")
    except voz.VozError:
        logger.exception("Error generando la voz de Melcochita")
        raise HTTPException(status_code=502, detail="No se pudo generar la voz.")
    return Response(content=audio, media_type="audio/mpeg")
```

## 4. Cambios en el frontend

**a)** En `web/index.html`, dentro de `#tarjeta-resultado` (por ejemplo
justo después del `<p id="texto-chapa">`), agrega un botón para volver a
escuchar:

```html
<button id="btn-escuchar" class="btn-secundario" hidden>🔊 Escúchalo otra vez</button>
```

**b)** En `web/script.js`, agrega la función de voz:

```javascript
// --- Voz de Melcochita ---
const btnEscuchar = document.getElementById("btn-escuchar");
let _audioMelco = null;

async function reproducirVoz(texto) {
  if (btnEscuchar) btnEscuchar.hidden = true;
  try {
    const r = await fetch("/voz", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ texto }),
    });
    if (!r.ok) return;                       // sin audio: la chapa se ve igual
    const blob = await r.blob();
    if (_audioMelco) URL.revokeObjectURL(_audioMelco.src);
    _audioMelco = new Audio(URL.createObjectURL(blob));
    if (btnEscuchar) btnEscuchar.hidden = false;
    _audioMelco.play().catch(() => {});      // si el navegador bloquea autoplay, queda el botón
  } catch (_) { /* el audio es un plus; nunca rompe la experiencia */ }
}

if (btnEscuchar) {
  btnEscuchar.addEventListener("click", () => { if (_audioMelco) _audioMelco.play(); });
}
```

**c)** En `web/script.js`, dentro de `solicitarChapa`, justo después de
`mostrarSolo(tarjetaResultado);`, dispara la voz:

```javascript
    mostrarSolo(tarjetaResultado);
    reproducirVoz(data.chapa);   // <-- agregar esta línea
```

Eso es todo. El frontend sigue mostrando `data.chapa` pelada; el audio
que suena es la versión enmarcada.

---

## Notas

- **Caché:** cada frase enmarcada se guarda como MP3 en
  `outputs/voz_cache/`. Repeticiones y chapas populares salen al instante
  y sin costo. Puedes borrar esa carpeta cuando quieras (se regenera).
- **Marco:** `voz.py` rota entre "mi querido / le dicen / mi querida".
  Si más adelante quieres que el marco coincida con el que el motor
  eligió internamente, se puede exponer ese dato desde `app.py` sin tocar
  la lógica sellada — pero así ya funciona bien.
- **Seguridad:** solo llames `/voz` con chapas que vinieron de `/generar`
  (ya pasaron el filtro de seguridad). Es lo que protege la voz de
  Melcochita.
- **Plan B gratis:** si algún día quieren bajar costos, `voz.py` se puede
  reapuntar a un servicio local de Chatterbox (requiere GPU) cambiando
  solo la función `sintetizar_chapa`. El resto queda igual.
```
