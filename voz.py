"""
voz.py — Módulo de voz del Melcochómetro.

Toma la chapa YA generada (texto pelado), le pone el MARCO discursivo de
Melcochita ("Mi querido… / Mi querida… / A este le dicen…") y la manda a
ElevenLabs con el clon de su voz. Devuelve el MP3. Incluye caché en disco
por texto para no re-sintetizar ni gastar créditos de más.

NO toca generar_chapa.py ni la lógica del motor. El frontend sigue
mostrando la chapa pelada; esto solo produce el audio con el marco.

Requiere en el entorno (.env), cargado con load_dotenv() igual que la key
de OpenAI:
    ELEVENLABS_API_KEY=...
    MELCOCHITA_VOICE_ID=...        (el voice_id del clon)
    ELEVEN_MODEL_ID=eleven_multilingual_v2   (opcional)

La config se lee de forma DIFERIDA (en cada llamada, no al importar), así
que no importa el orden de imports en app.py: para cuando /voz se invoca,
load_dotenv() ya corrió. Además este módulo llama load_dotenv() por su
cuenta como salvaguarda.

La key nunca se expone al frontend: se usa solo server-side.

SEGURIDAD: llamar sintetizar_chapa() SOLO con chapas que salieron de
/generar. Ese endpoint ya aplicó el filtro de seguridad del motor, que es
lo que protege la reputación de Melcochita: su voz no debe decir nada que
no haya pasado ese filtro.
"""

import os
import base64
import hashlib
from pathlib import Path
from typing import Optional

import httpx  # ya viene como dependencia de openai

try:
    from dotenv import load_dotenv  # ya es dependencia del proyecto
except Exception:  # pragma: no cover
    def load_dotenv(*a, **k):
        return False

_BASE = "https://api.elevenlabs.io"

# Caché en disco, junto a las métricas ya existentes: outputs/voz_cache/
_CACHE_DIR = Path(__file__).resolve().parent / "outputs" / "voz_cache"

# Marcos discursivos hallados en el análisis del corpus (ADN v2).
# "le dicen" es neutro de género; "mi querido/a" da calidez. Como el motor
# no captura el género de la víctima, rotamos entre neutro y masculino por
# defecto. Estas palabras están muy presentes en la grabación: el clon las
# pronuncia clavadas y "arrastran" con naturalidad a la chapa nueva.
_MARCOS = ["mi querido", "le dicen", "mi querido", "le dicen", "mi querida"]

# Voz muy marcada: stability bajo = más carácter; similarity alto = más
# parecido. Estos valores salieron de la prueba; ajústalos si hace falta.
_VOICE_SETTINGS = {
    "stability": 0.35,
    "similarity_boost": 0.90,
    "style": 0.40,
    "use_speaker_boost": True,
}


class VozNoConfigurada(RuntimeError):
    """Faltan ELEVENLABS_API_KEY o MELCOCHITA_VOICE_ID."""


class VozError(RuntimeError):
    """Fallo al generar el audio (red o API)."""


def _cfg():
    """Lee la config del entorno de forma diferida (idempotente)."""
    # override=True: el .env es la fuente de verdad. Si cambias el
    # voice_id o la key en .env, se toma sin arrastrar valores viejos que
    # hubieran quedado en os.environ de un arranque anterior.
    load_dotenv(override=True)
    return (
        os.environ.get("ELEVENLABS_API_KEY"),
        os.environ.get("MELCOCHITA_VOICE_ID"),
        os.environ.get("ELEVEN_MODEL_ID", "eleven_multilingual_v2"),
    )


def voz_disponible() -> bool:
    api_key, voice_id, _ = _cfg()
    return bool(api_key and voice_id)


def _marco_determinista(texto: str) -> str:
    """
    Elige el marco de forma ESTABLE según el texto: la misma chapa recibe
    siempre el mismo marco. Así cada chapa genera UN solo audio en caché
    (y no uno por marco), que es lo que hace rendir los créditos con
    tráfico masivo. Reparte entre los marcos según _MARCOS (con su peso).
    """
    h = int(hashlib.sha256(texto.lower().encode("utf-8")).hexdigest(), 16)
    return _MARCOS[h % len(_MARCOS)]


def enmarcar(chapa: str, marco: Optional[str] = None) -> str:
    """Envuelve la chapa pelada con el marco discursivo de Melcochita."""
    limpio = chapa.strip().strip(".!¡ ").strip()
    if marco is None:
        marco = _marco_determinista(limpio)
    if marco == "le dicen":
        return f"A este le dicen... ¡{limpio}!"
    if marco == "mi querida":
        return f"Mi querida... ¡{limpio}!"
    return f"Mi querido... ¡{limpio}!"


def _clave_cache(voice_id: str, model_id: str, frase: str) -> str:
    return hashlib.sha256(
        f"{voice_id}|{model_id}|{frase}".encode("utf-8")
    ).hexdigest()[:32]


# --- Caché externo persistente (Upstash Redis vía REST) -------------------
# El disco de Render (plan free) es EFÍMERO: se borra en cada redeploy y cada
# vez que el servicio despierta de su "sleep" por inactividad. Para que la
# caché de audios sobreviva —y no se re-gasten créditos de ElevenLabs por
# chapas repetidas— además del disco local guardamos cada MP3 en Upstash
# Redis (tier gratis). Todo es best-effort: si Redis no está configurado o
# falla, la síntesis sigue funcionando exactamente igual.
_REDIS_PREFIJO = "melco:voz:"


def _redis_cfg():
    url = os.environ.get("UPSTASH_REDIS_REST_URL")
    tok = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    return (url.rstrip("/") if url else None, tok)


def _redis_get(clave: str):
    """MP3 (bytes) guardado en Redis para esa clave, o None."""
    url, tok = _redis_cfg()
    if not url or not tok:
        return None
    try:
        r = httpx.post(
            url,
            headers={"Authorization": f"Bearer {tok}"},
            json=["GET", _REDIS_PREFIJO + clave],
            timeout=5,
        )
        if r.status_code >= 300:
            return None
        res = r.json().get("result")
        if not res:
            return None
        return base64.b64decode(res)
    except Exception:
        return None


def _redis_set(clave: str, audio: bytes) -> None:
    """Guarda el MP3 (base64) en Redis. No interrumpe si falla."""
    url, tok = _redis_cfg()
    if not url or not tok:
        return
    try:
        cmd = ["SET", _REDIS_PREFIJO + clave, base64.b64encode(audio).decode("ascii")]
        try:
            ttl_dias = int(os.environ.get("VOZ_CACHE_TTL_DIAS", "0") or "0")
        except ValueError:
            ttl_dias = 0
        if ttl_dias > 0:  # 0 = sin expirar
            cmd += ["EX", str(ttl_dias * 86400)]
        httpx.post(
            url,
            headers={"Authorization": f"Bearer {tok}"},
            json=cmd,
            timeout=8,
        )
    except Exception:
        pass


def _guardar_local(ruta, audio: bytes) -> None:
    """Escritura atómica del MP3 en el disco local (caché del proceso)."""
    try:
        tmp = ruta.with_suffix(".mp3.tmp")
        tmp.write_bytes(audio)
        tmp.replace(ruta)
    except Exception:
        pass


def redis_cmd(arr, timeout: float = 5):
    """Ejecuta un comando Redis (como array) vía REST y devuelve su 'result'.

    Best-effort y de uso general (contadores de métricas, etc.): si Redis no
    está configurado o algo falla, devuelve None y nunca lanza. Reutiliza la
    misma config de Upstash del caché de voz.
    """
    url, tok = _redis_cfg()
    if not url or not tok:
        return None
    try:
        r = httpx.post(
            url,
            headers={"Authorization": f"Bearer {tok}"},
            json=arr,
            timeout=timeout,
        )
        if r.status_code >= 300:
            return None
        return r.json().get("result")
    except Exception:
        return None


def sintetizar_chapa(chapa: str, marco: Optional[str] = None) -> bytes:
    """
    Devuelve el MP3 (bytes) de la chapa enmarcada y dicha por Melcochita.
    Usa caché en disco: si esa frase ya se sintetizó, la sirve al instante
    sin volver a llamar (ni pagar) a ElevenLabs.
    """
    api_key, voice_id, model_id = _cfg()
    if not api_key or not voice_id:
        raise VozNoConfigurada("Falta ELEVENLABS_API_KEY o MELCOCHITA_VOICE_ID.")

    # Por defecto NO se añade el marco ("Mi querido…"): ahora ese arranque
    # lo dan los intros PREGRABADOS con la voz real de Melcochita que el
    # frontend reproduce antes de la chapa. Así no se dice dos veces y se
    # sintetiza solo la chapa pelada (más corta = menos créditos). Para
    # volver al marco sintetizado, poner VOZ_CON_MARCO=true en el .env.
    con_marco = os.environ.get("VOZ_CON_MARCO", "false").lower() in ("1", "true", "yes", "si", "sí")
    frase = enmarcar(chapa, marco) if con_marco else chapa.strip().strip(".!¡ ").strip()
    clave = _clave_cache(voice_id, model_id, frase)
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ruta = _CACHE_DIR / f"{clave}.mp3"

    # 1) Caché local (disco del proceso actual).
    if ruta.exists():
        return ruta.read_bytes()

    # 2) Caché externo persistente (Upstash): sobrevive redeploys y el "sleep"
    #    del plan free. Si está, se sirve sin volver a pagar a ElevenLabs.
    audio_remoto = _redis_get(clave)
    if audio_remoto:
        _guardar_local(ruta, audio_remoto)  # repuebla el disco local
        return audio_remoto

    url = f"{_BASE}/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128"
    try:
        r = httpx.post(
            url,
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            json={
                "text": frase,
                "model_id": model_id,
                "voice_settings": _VOICE_SETTINGS,
            },
            timeout=60,
        )
    except httpx.HTTPError as e:
        raise VozError(f"Fallo de red con ElevenLabs: {e}") from e

    if r.status_code >= 300:
        raise VozError(f"ElevenLabs {r.status_code}: {r.text[:200]}")

    audio = r.content
    # Guarda en ambos cachés: local (rápido) y externo (persistente).
    _guardar_local(ruta, audio)
    _redis_set(clave, audio)
    return audio
