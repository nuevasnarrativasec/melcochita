"""
app.py

Piloto Melcochómetro — MVP WEB mínimo.

    navegador -> FastAPI -> generar_chapa.py (motor ya validado) -> OpenAI -> resultado

Reutiliza DIRECTAMENTE generar_chapa.generar_para_perfil() — mismos
filtros de seguridad, scoring de 6 dimensiones, umbral, segunda ronda
automática y selección por adn_melcocha ya validados en la prueba de
estrés. No se modifica esa lógica.

Sin base de datos. Sin n8n/Typebot. No se toca el Corpus Gold ni
data/analysis/adn_humoristico_v2.csv (solo se leen, vía las funciones ya
existentes).

OPENAI_API_KEY se carga una sola vez al iniciar el servidor, desde .env
(reutilizando generar_chapa.cargar_api_key()), y NUNCA se envía al
frontend: solo se usa server-side para llamar a la API de OpenAI. La
respuesta de /generar contiene únicamente la chapa ganadora; el scoring
completo se registra solo en el log del servidor.

Uso:
    .venv/bin/uvicorn app:app --reload
"""

import json
import logging
import sys
import threading
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
import generar_chapa as gc  # motor ya validado, NO se modifica

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from openai import OpenAI
import openai as openai_module

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("melcochometro")

PROJECT_ROOT = Path(__file__).resolve().parent
WEB_DIR = PROJECT_ROOT / "web"

app = FastAPI(title="Melcochómetro MVP")

# --------------------------------------------------------------------------
# Métricas ANÓNIMAS de uso (test con usuarios reales): solo contadores
# agregados server-side. NUNCA se guarda nombre, inputs del formulario,
# chapa generada, IP, ni ningún identificador de persona. Sin cookies de
# seguimiento — no hay forma de saber qué evento pertenece a qué visita.
# --------------------------------------------------------------------------
METRICAS_PATH = PROJECT_ROOT / "outputs" / "metricas_anonimas.json"
_metricas_lock = threading.Lock()
_CLAVES_METRICAS = ["generacion_exitosa", "clic_otra_chapa", "feedback_positivo", "feedback_negativo"]


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
# Carga ÚNICA al iniciar el servidor (no en cada request): API key,
# cliente de OpenAI, y el repertorio generativo / Corpus Gold (solo
# lectura, para el chequeo de no-copia literal).
# --------------------------------------------------------------------------
_api_key = gc.cargar_api_key()  # nunca se imprime ni se expone
_client = OpenAI(api_key=_api_key)
_repertorio, _n_usables = gc.cargar_repertorio_generativo()
_textos_corpus_gold = gc.cargar_corpus_gold_textos()
logger.info("Motor generativo listo: %s filas habilitadas, %s operaciones.", _n_usables, len(_repertorio))


class SolicitudChapa(BaseModel):
    nombre_o_apodo: str
    caracteristica: str
    costumbre: str
    objeto_que_siempre_usa: str
    # Solo para saber si contar el evento "clic_otra_chapa" (métrica
    # anónima, no identifica a nadie). No cambia en nada la generación.
    origen: Literal["primera", "otra_chapa"] = "primera"


class FeedbackSolicitud(BaseModel):
    # Nunca se envía ni se guarda la chapa, ni ningún dato del formulario:
    # solo el voto, para el contador anónimo.
    valor: Literal["positivo", "negativo"]


# --------------------------------------------------------------------------
# AJUSTE (selección del ganador final mostrado al usuario, NO toca el
# motor): además del umbral ya existente (adn_melcocha/sorpresa_semantica/
# originalidad_vs_corpus >= 4, calculado por generar_chapa.cumple_umbral),
# el resultado FINAL debe también tener conexion_con_input >= 3, para que
# la persona reconozca alguna relación con el dato que dio sobre su
# amigo ("absurdo reconocible", no "absurdo puro"). No se exige 4 o 5
# para no volver las chapas demasiado literales.
# --------------------------------------------------------------------------
UMBRAL_CONEXION_CON_INPUT_FINAL = 3


def _es_elegible_final(c):
    # c ya viene de resultado["que_cumplen_umbral"]: ya cumple
    # adn_melcocha/sorpresa_semantica/originalidad_vs_corpus >= 4 y ya
    # pasó el filtro de seguridad (ambos calculados por el motor, sin
    # tocar esa lógica). Aquí solo se agrega la exigencia de conexión.
    return c["conexion_con_input"] >= UMBRAL_CONEXION_CON_INPUT_FINAL


def _prioridad(c):
    # 1) adn_melcocha  2) sorpresa_semantica  3) conexion_con_input
    # 4) absurdo_controlado  5) originalidad_vs_corpus
    return (
        -c["adn_melcocha"], -c["sorpresa_semantica"], -c["conexion_con_input"],
        -c["absurdo_controlado"], -c["originalidad_vs_corpus"],
    )


# La web muestra UNA sola chapa, así que no necesita el TOP 5 del motor.
# Con objetivo=2 el motor corta apenas tiene 2 candidatos sobre el umbral
# (deja un pequeño margen para exigir además conexion_con_input>=3), y la
# ronda 1 casi siempre basta: 2 llamadas en vez de 4-8.
OBJETIVO_CANDIDATOS_WEB = 2


def _generar_resultado(solicitud):
    return gc.generar_para_perfil(
        _client, _repertorio, _textos_corpus_gold,
        solicitud.nombre_o_apodo, solicitud.caracteristica,
        solicitud.costumbre, solicitud.objeto_que_siempre_usa,
        objetivo_candidatos=OBJETIVO_CANDIDATOS_WEB,
    )


def _elegir_ganador(resultados):
    """
    resultados: lista de uno o dos dicts devueltos por
    generar_chapa.generar_para_perfil() (sin modificar esa función).
    Combina sus pools ya filtrados por seguridad+umbral existente
    (que_cumplen_umbral) y elige el mejor que ADEMÁS cumpla
    conexion_con_input >= 3, según la prioridad pedida. Si ninguno lo
    cumple, usa como salvaguarda documentada el mejor que sí cumplía el
    umbral original (se marca bajo_umbral_conexion=True para el log).
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
def generar(solicitud: SolicitudChapa):
    try:
        # UNA sola invocación al motor (que ya intenta hasta 2 rondas internas
        # por su propio criterio). Antes, si ningún candidato alcanzaba
        # conexion_con_input>=3 se rehacía TODA la generación — hasta duplicar
        # las llamadas. Ahora, por latencia, se elige el mejor disponible:
        # _elegir_ganador ya cae con elegancia al mejor que cumple el umbral
        # (marcando bajo_umbral_conexion=True para el log) en vez de regenerar.
        resultados = [_generar_resultado(solicitud)]
        ganador, bajo_umbral_conexion = _elegir_ganador(resultados)
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

    # Log COMPLETO solo en el servidor — nunca se envía al frontend.
    logger.info(
        "Chapa=%r | intentos=%s rondas_totales=%s candidatos_totales=%s bajo_umbral_conexion=%s | "
        "señal=%s operacion=%s patron=%s | "
        "correccion_linguistica=%s conexion_con_input=%s sorpresa_semantica=%s "
        "absurdo_controlado=%s adn_melcocha=%s originalidad_vs_corpus=%s",
        ganador["chapa"], len(resultados), sum(r["rondas_usadas"] for r in resultados),
        sum(len(r["candidatos_totales"]) for r in resultados), bajo_umbral_conexion,
        ganador["senal_utilizada"], ganador["operacion"], ganador["patron_estructural"],
        ganador["correccion_linguistica"], ganador["conexion_con_input"], ganador["sorpresa_semantica"],
        ganador["absurdo_controlado"], ganador["adn_melcocha"], ganador["originalidad_vs_corpus"],
    )

    # Métrica anónima: solo un contador +1, nada identificable.
    _incrementar_metrica("generacion_exitosa")
    if solicitud.origen == "otra_chapa":
        _incrementar_metrica("clic_otra_chapa")

    return {"chapa": ganador["chapa"]}


@app.post("/feedback")
def feedback(solicitud: FeedbackSolicitud):
    clave = "feedback_positivo" if solicitud.valor == "positivo" else "feedback_negativo"
    _incrementar_metrica(clave)
    return {"ok": True}


# Rutas API primero; el frontend estático se monta al final en "/".
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
