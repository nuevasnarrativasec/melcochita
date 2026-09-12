"""
app.py

Melcochómetro — MVP WEB.

    navegador -> FastAPI -> [chapa original 30% | generación nueva 70%] -> resultado
                 (+ voz de Melcochita vía /voz)

Fusión: motor v3 (mezcla original/nueva, sexo, score_estilo_original) + capa
de voz (voz.py / ElevenLabs), audios de carga y límite por IP. No se modifica
la lógica de scoring del motor; solo se parametriza la latencia
(objetivo_candidatos, portado de main) y se añaden endpoints alrededor.

OPENAI_API_KEY y ELEVENLABS_API_KEY se cargan desde .env y NUNCA se envían al
frontend: solo se usan server-side.

Uso:
    uvicorn app:app --reload
"""

import datetime
import json
import logging
import os
import random
import re
import sys
import threading
import unicodedata
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
import generar_chapa as gc  # motor v3

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response
from pydantic import BaseModel
from openai import OpenAI
import openai as openai_module

import voz  # módulo de voz de Melcochita; no toca el motor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("melcochometro")

PROJECT_ROOT = Path(__file__).resolve().parent
WEB_DIR = PROJECT_ROOT / "web"

app = FastAPI(title="Melcochómetro MVP")

# --------------------------------------------------------------------------
# Límite por IP/día (salvaguarda de costo): evita que un pico viral vacíe
# el saldo de ElevenLabs/OpenAI. En memoria y por proceso — tope simple, no
# antifraude. Para varios workers, migrar a Redis. Ajustable con
# LIMITE_POR_IP_DIA. No cuenta caché ni errores; solo requests efectivos.
# --------------------------------------------------------------------------
LIMITE_POR_IP_DIA = int(os.environ.get("LIMITE_POR_IP_DIA", "40"))
_rate_lock = threading.Lock()
_rate_data = {}  # {(bucket, ip, fecha_iso): conteo}


def _ip_cliente(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "desconocido"


def _chequear_limite(request: Request, bucket: str):
    ip = _ip_cliente(request)
    hoy = datetime.date.today().isoformat()
    clave = (bucket, ip, hoy)
    with _rate_lock:
        if len(_rate_data) > 10000:
            for k in [k for k in _rate_data if k[2] != hoy]:
                del _rate_data[k]
        n = _rate_data.get(clave, 0)
        if n >= LIMITE_POR_IP_DIA:
            raise HTTPException(
                status_code=429,
                detail="¡Ya melcochaste bastante por hoy! Vuelve mañana. 😄",
            )
        _rate_data[clave] = n + 1

# --------------------------------------------------------------------------
# Métricas ANÓNIMAS de uso: solo contadores agregados server-side. NUNCA se
# guarda nombre, inputs, chapa, IP ni identificador de persona.
# --------------------------------------------------------------------------
METRICAS_PATH = PROJECT_ROOT / "outputs" / "metricas_anonimas.json"
_metricas_lock = threading.Lock()
_CLAVES_METRICAS = ["generacion_exitosa", "generacion_original", "generacion_nueva", "clic_otra_chapa", "feedback_positivo", "feedback_negativo"]


def _cargar_metricas():
    if METRICAS_PATH.exists():
        try:
            with open(METRICAS_PATH, "r", encoding="utf-8") as f:
                datos = json.load(f)
        except (json.JSONDecodeError, OSError):
            datos = {}
    else:
        datos = {}
    for clave in _CLAVES_METRICAS:
        datos.setdefault(clave, 0)
    return datos


def _incrementar_metrica(clave):
    with _metricas_lock:
        datos = _cargar_metricas()
        datos[clave] = datos.get(clave, 0) + 1
        METRICAS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(METRICAS_PATH, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
        return datos[clave]

# --------------------------------------------------------------------------
# Carga ÚNICA al iniciar el servidor: API key, cliente OpenAI, repertorio,
# Corpus Gold y originales publicables (solo lectura).
# --------------------------------------------------------------------------
_api_key = gc.cargar_api_key()  # nunca se imprime ni se expone
_client = OpenAI(api_key=_api_key)
_repertorio, _n_usables = gc.cargar_repertorio_generativo()
_textos_corpus_gold = gc.cargar_corpus_gold_textos()
_originales_publicables = gc.cargar_originales_publicables()
try:
    PROBABILIDAD_CHAPA_ORIGINAL = float(os.getenv("PROBABILIDAD_CHAPA_ORIGINAL", "0.30"))
except ValueError:
    PROBABILIDAD_CHAPA_ORIGINAL = 0.30
PROBABILIDAD_CHAPA_ORIGINAL = max(0.0, min(1.0, PROBABILIDAD_CHAPA_ORIGINAL))
logger.info(
    "Motor listo: %s filas generativas, %s operaciones, %s originales publicables, mezcla original=%.0f%%.",
    _n_usables, len(_repertorio), len(_originales_publicables), PROBABILIDAD_CHAPA_ORIGINAL * 100,
)

# Latencia web (portado de main): la web pide un corte temprano con pocos
# candidatos en vez del TOP 5 del CLI, para responder más rápido.
OBJETIVO_CANDIDATOS_WEB = 2


class SolicitudChapa(BaseModel):
    nombre_o_apodo: str
    caracteristica: str
    costumbre: str
    objeto_que_siempre_usa: str
    sexo: Literal["hombre", "mujer", "no_indica"] = "no_indica"
    ultima_chapa: str = ""
    origen: Literal["primera", "otra_chapa"] = "primera"


class FeedbackSolicitud(BaseModel):
    valor: Literal["positivo", "negativo"]


class SolicitudVoz(BaseModel):
    # La chapa YA generada por /generar (texto pelado). El marco discursivo
    # ("Mi querido…") lo agrega voz.py; el frontend muestra la chapa pelada.
    # NO enviar aquí texto que no venga de /generar.
    texto: str


# --------------------------------------------------------------------------
# Selección del ganador final (v3): además del umbral del motor, se exige
# conexion_con_input >= 3 y se prioriza por score_estilo_original.
# --------------------------------------------------------------------------
UMBRAL_CONEXION_CON_INPUT_FINAL = 3


def _es_elegible_final(c):
    return c["conexion_con_input"] >= UMBRAL_CONEXION_CON_INPUT_FINAL


def _prioridad(c):
    return (
        -c.get("score_estilo_original", 0),
        -c["adn_melcocha"], -c["sorpresa_semantica"], -c["conexion_con_input"],
        -c["absurdo_controlado"], -c["originalidad_vs_corpus"],
    )


def _generar_resultado(solicitud):
    return gc.generar_para_perfil(
        _client, _repertorio, _textos_corpus_gold,
        solicitud.nombre_o_apodo, solicitud.caracteristica,
        solicitud.costumbre, solicitud.objeto_que_siempre_usa,
        sexo=solicitud.sexo, objetivo_candidatos=OBJETIVO_CANDIDATOS_WEB,
    )


def _norm_ascii(texto):
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9ñ ]+", " ", t)


_GRUPOS_RASGOS = {
    "pelo": {"pelo", "cabello", "rizado", "rulos", "ensortijado", "rubio", "negro", "peinado", "permanente", "choclo"},
    "calvicie": {"calvo", "calva", "pelado", "pelada", "calvicie"},
    "barba": {"barba", "barbon", "barbudo", "barbuda"},
    "dientes": {"diente", "dientes", "dentadura", "sonrisa"},
    "nariz": {"nariz", "narizon", "narizona"},
    "lentes": {"lentes", "gafas", "anteojos"},
    "estatura_baja": {"bajo", "baja", "chato", "chata", "pequeno", "pequena"},
    "estatura_alta": {"alto", "alta", "larguirucho", "larguirucha"},
    "delgadez": {"flaco", "flaca", "delgado", "delgada"},
    "edad_joven": {"joven", "muchacho", "muchacha"},
    "edad_mayor": {"viejo", "vieja", "anciano", "anciana", "mayor"},
}


def _rasgos_canonicos(texto):
    toks = set(_norm_ascii(texto).split())
    return {grupo for grupo, palabras in _GRUPOS_RASGOS.items() if toks & palabras}


def _compatibilidad_sexo(chapa, sexo):
    """Evita incompatibilidades humanas obvias; referentes neutros siguen disponibles."""
    if sexo == "no_indica":
        return 1.0
    t = _norm_ascii(chapa)
    femeninos = {"senora", "mama", "abuela", "abuelita", "barbie", "monalisa", "cenicienta", "juanita"}
    masculinos = {"senor", "abuelo", "abuelito", "hombre", "don", "conde", "cochero", "compadre"}
    toks = set(t.split())
    if sexo == "hombre" and toks & femeninos:
        return 0.0
    if sexo == "mujer" and toks & masculinos:
        return 0.0
    return 1.0


def _seleccionar_original(solicitud):
    """Selecciona un original compatible, con preferencia por el mismo rasgo físico."""
    objetivo = _rasgos_canonicos(solicitud.caracteristica)
    ultima = gc._normalizar(solicitud.ultima_chapa)
    candidatos = []
    pesos = []
    for r in _originales_publicables:
        chapa = (r.get("chapa_original") or "").strip()
        if not chapa or gc._normalizar(chapa) == ultima:
            continue
        comp = _compatibilidad_sexo(chapa, solicitud.sexo)
        if comp <= 0:
            continue
        rasgos_ref = _rasgos_canonicos(r.get("caracteristica_asociada") or "")
        coincidencias = len(objetivo & rasgos_ref)
        peso = 1.0 + (7.0 * coincidencias)
        if objetivo and rasgos_ref:
            peso += 0.75
        candidatos.append(chapa)
        pesos.append(peso)
    if not candidatos:
        return None
    return random.choices(candidatos, weights=pesos, k=1)[0]


def _debe_salir_original():
    return bool(_originales_publicables) and random.random() < PROBABILIDAD_CHAPA_ORIGINAL


def _elegir_ganador(resultados):
    """
    Combina los pools ya filtrados por seguridad+umbral del motor
    (que_cumplen_umbral) y elige el mejor que ADEMÁS cumpla
    conexion_con_input >= 3, según la prioridad. Si ninguno lo cumple,
    salvaguarda documentada al mejor que sí cumplía el umbral original.
    """
    que_cumplen = [c for r in resultados for c in r["que_cumplen_umbral"]]
    elegibles = [c for c in que_cumplen if _es_elegible_final(c)]
    if elegibles:
        return min(elegibles, key=_prioridad), False

    if que_cumplen:
        return min(que_cumplen, key=_prioridad), True

    totales = [c for r in resultados for c in r["candidatos_totales"]]
    if totales:
        validos, _ = gc.filtrar_seguridad(totales, _textos_corpus_gold)
        pool = validos or totales
        return max(pool, key=lambda c: c["adn_melcocha"]), True

    return None, False


@app.post("/generar")
def generar(solicitud: SolicitudChapa, request: Request):
    _chequear_limite(request, "generar")

    # Ruta A: una parte de las respuestas proviene literalmente del corpus
    # original. Preserva la voz real y ahorra una llamada al LLM.
    if _debe_salir_original():
        original = _seleccionar_original(solicitud)
        if original:
            _incrementar_metrica("generacion_exitosa")
            _incrementar_metrica("generacion_original")
            if solicitud.origen == "otra_chapa":
                _incrementar_metrica("clic_otra_chapa")
            logger.info("Chapa original seleccionada: %r", original)
            return {"chapa": original}

    # Ruta B: generación nueva, calibrada por el corpus original.
    try:
        resultados = [_generar_resultado(solicitud)]
        ganador, bajo_umbral_conexion = _elegir_ganador(resultados)

        if bajo_umbral_conexion:
            logger.warning("Ningún candidato cumplió conexion_con_input>=%s junto al umbral existente "
                            "tras el primer intento; generando de nuevo.", UMBRAL_CONEXION_CON_INPUT_FINAL)
            resultados.append(_generar_resultado(solicitud))
            ganador, bajo_umbral_conexion = _elegir_ganador(resultados)
    except ValueError as e:
        logger.warning("Solicitud sin señales utilizables tras filtros de seguridad: %s", e)
        raise HTTPException(
            status_code=422,
            detail="Prueba con rasgos, costumbres u objetos que no dependan de atributos sensibles.",
        )
    except openai_module.OpenAIError as e:
        logger.error("Error de OpenAI: %s", e)
        raise HTTPException(status_code=502, detail="Error generando la chapa. Intenta de nuevo.")
    except Exception:
        logger.exception("Error inesperado generando la chapa")
        raise HTTPException(status_code=500, detail="Error interno generando la chapa.")

    if ganador is None:
        raise HTTPException(status_code=502, detail="No se pudo generar ninguna chapa. Intenta de nuevo.")

    if bajo_umbral_conexion:
        logger.warning("Se devuelve el mejor candidato disponible aunque no alcanzó "
                        "conexion_con_input>=%s (conexion=%s).",
                        UMBRAL_CONEXION_CON_INPUT_FINAL, ganador["conexion_con_input"])

    logger.info(
        "Chapa=%r | intentos=%s rondas_totales=%s candidatos_totales=%s bajo_umbral_conexion=%s | "
        "señal=%s operacion=%s patron=%s | "
        "correccion_linguistica=%s conexion_con_input=%s sorpresa_semantica=%s "
        "absurdo_controlado=%s adn_melcocha=%s originalidad_vs_corpus=%s score_estilo_original=%s",
        ganador["chapa"], len(resultados), sum(r["rondas_usadas"] for r in resultados),
        sum(len(r["candidatos_totales"]) for r in resultados), bajo_umbral_conexion,
        ganador["senal_utilizada"], ganador["operacion"], ganador["patron_estructural"],
        ganador["correccion_linguistica"], ganador["conexion_con_input"], ganador["sorpresa_semantica"],
        ganador["absurdo_controlado"], ganador["adn_melcocha"], ganador["originalidad_vs_corpus"],
        ganador.get("score_estilo_original", 0),
    )

    _incrementar_metrica("generacion_exitosa")
    _incrementar_metrica("generacion_nueva")
    if solicitud.origen == "otra_chapa":
        _incrementar_metrica("clic_otra_chapa")

    return {"chapa": ganador["chapa"]}


@app.post("/feedback")
def feedback(solicitud: FeedbackSolicitud):
    clave = "feedback_positivo" if solicitud.valor == "positivo" else "feedback_negativo"
    _incrementar_metrica(clave)
    return {"ok": True}


@app.post("/voz")
def generar_voz(solicitud: SolicitudVoz, request: Request):
    _chequear_limite(request, "voz")
    try:
        audio = voz.sintetizar_chapa(solicitud.texto)
    except voz.VozNoConfigurada:
        raise HTTPException(status_code=503, detail="Voz no configurada.")
    except voz.VozError:
        logger.exception("Error generando la voz de Melcochita")
        raise HTTPException(status_code=502, detail="No se pudo generar la voz.")
    return Response(content=audio, media_type="audio/mpeg")


# Audios de las frases de carga (voz de Melcochita), servidos estáticos en
# /audio-carga -> carpeta frases-carga-melcochometro/. Antes del catch-all "/".
AUDIO_CARGA_DIR = PROJECT_ROOT / "frases-carga-melcochometro"
if AUDIO_CARGA_DIR.is_dir():
    app.mount("/audio-carga", StaticFiles(directory=AUDIO_CARGA_DIR), name="audio-carga")
else:
    logger.warning("No se encontró la carpeta de audios de carga: %s", AUDIO_CARGA_DIR)

# Rutas API primero; el frontend estático se monta al final en "/".
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
