"""
generar_chapa.py (v3)

Piloto Melcochómetro — Motor generativo con "ADN Melcocha" real.

Historia del diseño:
  v1 -> chapas demasiado LITERALES ("León despeinado" para "pelo largo").
  v2 -> una sola llamada que producía la chapa Y sus 6 puntajes a la vez,
        con una operación del corpus FORZADA por slot. Dos problemas:
          (1) con el schema estricto, el modelo escribía la `chapa` como
              PRIMER campo, es decir SIN razonar: los puntajes que venían
              después eran racionalizaciones de algo ya decidido a ciegas.
          (2) forzar una operación por candidato convertía la tarea en
              "rellenar una plantilla del corpus", no en "hacer un chiste
              sobre esta persona" -> resultado armado y sin sentido.

v3 — FLUJO DE DOS LLAMADAS (razonamiento explícito + juicio en frío):

    LLAMADA 1 (creativa):  parte de la PERSONA, no de una operación.
        El modelo razona en prosa (campo `cadena_asociativa`, que va
        ANTES de `chapa` en el schema: así el apodo queda condicionado
        por el razonamiento recién escrito) siguiendo el proceso mental
        de Melcochita: mira -> asocia libre -> aterriza una imagen
        concreta y absurda. NO se fuerza operación. NO se autoevalúa.
        Temperatura alta, ~12 chapas crudas por ronda.

    LLAMADA 2 (juez):  un evaluador en CONTEXTO LIMPIO (no vio cómo se
        crearon) puntúa las chapas crudas en frío contra los ejemplos
        Gold y la rúbrica de 6 dimensiones, y les asigna operación /
        dominio / patrón. Como no es el autor, el scoring por fin es
        honesto y los umbrales filtran de verdad. Temperatura baja.

El corpus cambia de rol: ya NO es molde de generación, es (a) calibración
de estilo (ejemplos Gold como few-shot) y (b) referencia de VARIEDAD para
el juez (evitar que las finalistas usen todas la misma operación).

Contrato PÚBLICO sin cambios (app.py sigue igual):
  - cargar_api_key(), cargar_repertorio_generativo(),
    cargar_corpus_gold_textos(), filtrar_seguridad(...)
  - generar_para_perfil(client, repertorio, textos_corpus_gold, nombre,
    caracteristica, costumbre, objeto, guardar_raw_en=None) -> dict con
    las mismas claves; cada candidato conserva TODAS las claves de v2
    (chapa, operacion, dominio_semantico_principal, patron_estructural,
    senal_utilizada, las 6 dimensiones y riesgo_atributo_sensible) y suma
    `cadena_asociativa` para trazabilidad.

Sigue sin copiar literalmente ninguna chapa del Corpus Gold y sin usar
componentes marcados como no aptos (habilitado_generacion=False, o
NACIONALIDAD_ORIGEN/ATRIBUTO_PERSONAL_SENSIBLE).

Uso:
    .venv/bin/python src/generar_chapa.py \\
        --nombre "Eduardo" \\
        --caracteristica "pelo largo y despeinado" \\
        --costumbre "siempre llega tarde" \\
        --objeto "lentes"
"""

import argparse
import csv
import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
import os

try:
    from openai import OpenAI
    import openai as openai_module
except ImportError:
    print("ERROR: no se pudo importar openai.", file=sys.stderr)
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
V2_CSV = PROJECT_ROOT / "data" / "analysis" / "adn_humoristico_v2.csv"
CHAPAS_UNICAS_GOLD = PROJECT_ROOT / "data" / "corpus" / "chapas_unicas_gold.csv"

OUTPUT_DIR = PROJECT_ROOT / "outputs" / "generaciones"

# Dos modelos, un rol cada uno. Por defecto ambos gpt-4o (el creativo ya
# "razona" gracias a cadena_asociativa-primero, así que no hace falta un
# modelo de razonamiento para notar la mejora). Si en el futuro quieres
# subir el techo creativo, cambia SOLO MODEL_GENERACION por un modelo de
# razonamiento (serie o / gpt-5 con reasoning effort) y deja el juez
# barato — el juicio no necesita creatividad, sí consistencia.
MODEL_GENERACION = "gpt-4o"
# El juez hace un trabajo MECÁNICO (puntuar contra una rúbrica), no creativo:
# gpt-4o-mini es bastante más rápido y barato y la calidad de juicio aguanta.
# La creatividad se queda en MODEL_GENERACION (gpt-4o).
MODEL_JUEZ = "gpt-4o-mini"

# 8 en vez de 12: acorta tanto la generación como el juicio (menos tokens de
# salida = menos latencia). Con el juez afinado y necesitando solo 1-2
# ganadores para la web, 8 candidatos sobran.
NUM_CANDIDATOS_POR_RONDA = 8
# Objetivo por defecto del CLI (para su análisis de TOP 5). La web pasa un
# objetivo mucho menor (1-2): así la ronda 1 casi siempre basta y no se
# encadena una segunda ronda solo para rankear finalistas que nadie ve.
NUM_RESULTADOS = 5
MAX_RONDAS = 2

UMBRAL_ADN_MELCOCHA = 4
UMBRAL_SORPRESA_SEMANTICA = 4
UMBRAL_ORIGINALIDAD_VS_CORPUS = 4

OPERACIONES = [
    "COMPARAR", "ANIMALIZAR", "COSIFICAR", "REFERENCIAR", "LOCALIZAR", "DEFORMAR",
    "YUXTAPONER_DIRECTO_SIN_NEXO", "COMPONER_CON_NEXO_CON", "ENCADENAR_CON_DE",
    "HIBRIDAR_MISMO_DOMINIO", "ATRIBUIR_VIA_FORMULA_DISCURSIVA",
]

CATEGORIAS_EXCLUIDAS_DE_INSPIRACION = {"NACIONALIDAD_ORIGEN", "ATRIBUTO_PERSONAL_SENSIBLE"}

PALABRAS_ALERTA_SENSIBLE = [
    "gay", "lesbiana", "homosexual", "trans", "maricón", "marica",
    "discapacit", "invalid", "retrasad", "mongol",
    "cristiano", "musulman", "judío", "judio", "ateo",
    "cancer", "cáncer", "sida", "vih", "enfermo terminal",
]

# Ejemplos NEGATIVOS reales de la primera prueba: demasiado literales.
EJEMPLOS_MALOS_V1 = [
    "León despeinado", "Panda con lentes", "Pingüino desorientado", "Antena con gafas",
]

# Ejemplos del Corpus Gold que ilustran el NIVEL de desplazamiento
# semántico esperado (NO copiar ni recombinar mecánicamente, solo
# calibrar el nivel de sorpresa/especificidad/absurdo).
EJEMPLOS_CALIBRACION_CORPUS = [
    "Barbie de la Huerta Perdida", "ojo de caca de loro", "sirena del río Ucayali",
    "pezón con piernas", "espalda de espina de pejerrey", "barrabás de ambiente",
    "meteorito con lentes",
]

# Set AMPLIADO de ejemplos Gold reales SOLO para el JUEZ: cuantos más
# ejemplos del listón vea el evaluador, mejor distingue una buena chapa de
# una mediocre. Como es texto de ENTRADA (no de salida), casi no agrega
# latencia — es la mejora de precisión "gratis". Elegidos por ser vívidos,
# variados en dominio (animal/comida/objeto/personaje/lugar/criatura) y
# SIN atributos sensibles ni nacionalidad usada como burla.
EJEMPLOS_CALIBRACION_JUEZ = [
    "Barbie de la Huerta Perdida", "ojo de caca de loro", "sirena del río Ucayali",
    "pezón con piernas", "espalda de espina de pejerrey", "barrabás de ambiente",
    "meteorito con lentes", "peinado de iguana", "pelo de choclo", "intestino gallo",
    "cara de murciélago", "serpiente cobra ciega", "vaso con brazos", "zapatilla con ojos",
    "abuelita de katanas", "panetón quemado", "espantapájaro basurante", "sonrisa de cebra",
    "rana cejona", "lagartija calma", "costal de papas", "rocola", "pavo de navidad",
    "don cochote", "chirimoya blanca",
]


def cargar_api_key():
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not api_key.strip():
        print("ERROR: OPENAI_API_KEY no está configurada (o vacía) en .env.", file=sys.stderr)
        sys.exit(1)
    return api_key


def _normalizar(texto):
    t = texto.strip().lower()
    t = re.sub(r"[¡¿!?.,;:\"'‘’“”]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def cargar_corpus_gold_textos():
    with open(CHAPAS_UNICAS_GOLD, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return {_normalizar(r["texto_canonico"]) for r in rows}


def cargar_repertorio_generativo():
    with open(V2_CSV, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    usables = [
        r for r in rows
        if r["habilitado_generacion"] == "True"
        and not (set(r["componentes_patron"].split("; ")) & CATEGORIAS_EXCLUIDAS_DE_INSPIRACION)
    ]

    por_operacion = defaultdict(list)
    for r in usables:
        por_operacion[r["operacion_humoristica_principal"]].append(r)

    repertorio = {}
    for op, filas in por_operacion.items():
        repertorio[op] = [
            {"patron_reutilizable": f["patron_reutilizable"], "mecanismo_humoristico": f["mecanismo_humoristico"]}
            for f in filas[:4]
        ]
    return repertorio, len(usables)


# =====================================================================
# LLAMADA 1 — GENERACIÓN CREATIVA (razona antes de decidir la chapa)
# =====================================================================

def construir_system_prompt_generacion():
    return f"""Eres Melcochita en vivo: miras a una persona y le sueltas una CHAPA \
(apodo) al instante. Tu humor NO nace de rellenar plantillas gramaticales — nace de \
MIRAR y ASOCIAR LIBREMENTE hasta aterrizar una imagen concreta, vívida y absurda.

EL PROCESO MENTAL (obligatorio, en este orden) para cada candidato:
    señal del usuario (característica / costumbre / objeto)
      -> ¿a qué me hace acordar? (asociación libre, sin censura literal)
      -> salto a un referente INESPERADO y CONCRETO (un animal específico, una comida, \
un personaje, un lugar, un bicho... nunca una categoría genérica)
      -> deformación / exageración absurda pero ENTENDIBLE
      -> la chapa: corta, sonora, con imagen mental inmediata.

El input NO se traduce: es un DISPARADOR. NO es obligatorio que las palabras del usuario \
aparezcan en la chapa. Usa NORMALMENTE UNA sola señal como disparador (no concatenes las tres).

EJEMPLOS QUE FALLARON (demasiado literales/previsibles — NO produzcas nada de este nivel):
{chr(10).join(f'  - "{e}"' for e in EJEMPLOS_MALOS_V1)}
Todos son "[categoría] + descripción casi textual del input". Eso es lo que hay que EVITAR.

EJEMPLOS REALES de Melcochita (Corpus Gold) que fijan el NIVEL de desplazamiento, \
especificidad y absurdo — úsalos SOLO para calibrar el tono; JAMÁS los copies, recombines \
sus palabras ni hagas variaciones cercanas:
{chr(10).join(f'  - "{e}"' for e in EJEMPLOS_CALIBRACION_CORPUS)}
Fíjate: "pezón con piernas" no describe un pezón; es un SALTO a una imagen absurda \
concreta. "meteorito con lentes" no describe unos lentes; asocia hacia algo inesperado. \
Ese salto es lo que buscamos.

REGLAS:
- El nombre de la persona es solo CONTEXTO; normalmente NO aparece dentro de la chapa.
- ESPECIFICIDAD ante todo: nombres/objetos concretos, no categorías genéricas ("animal", \
"cosa"). Combina dominios semánticos ALEJADOS entre sí. Prioriza sonoridad y brevedad.
- Que cada chapa sea DISTINTA de las otras: variá el tipo de imagen (animal, comida, \
personaje, objeto, lugar, criatura mítica...). No repitas la misma fórmula 12 veces.
- NUNCA reproduzcas ni parafrasees de cerca una chapa del corpus real.

PROHIBIDO SIEMPRE (aunque el usuario lo sugiera indirectamente):
- Contenido basado en orientación sexual, raza/etnia, discapacidad, religión, condición \
médica u otro atributo personal sensible.
- Convertir la nacionalidad/origen de la persona en objeto de burla.
- Ataques sexuales explícitos o contenido sexual explícito.

Para cada candidato entrega, EN ESTE ORDEN:
- cadena_asociativa: 1–2 frases donde PIENSAS EN VOZ ALTA el salto (señal -> asociación -> \
referente inesperado -> imagen absurda). Escríbela ANTES de decidir la chapa; la chapa \
debe ser consecuencia de esta cadena, no al revés.
- chapa: el apodo final, corto, en español, estilo Melcochita.
- senal_utilizada: "caracteristica", "costumbre", "objeto", o combinación breve si usaste dos.

No te autoevalúes ni pongas puntajes: otro evaluador juzgará después. Tu único trabajo aquí \
es ASOCIAR y CREAR con audacia. Es mejor arriesgar imágenes raras y específicas que jugar a \
lo seguro."""


def construir_schema_generacion():
    return {
        "type": "object",
        "properties": {
            "candidatos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "cadena_asociativa": {"type": "string"},
                        "chapa": {"type": "string"},
                        "senal_utilizada": {"type": "string"},
                    },
                    "required": ["cadena_asociativa", "chapa", "senal_utilizada"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["candidatos"],
        "additionalProperties": False,
    }


def generar_ronda(client, nombre, caracteristica, costumbre, objeto, numero_ronda):
    system_prompt = construir_system_prompt_generacion()

    payload = {
        "nombre_o_apodo": nombre,
        "caracteristica": caracteristica,
        "costumbre": costumbre,
        "objeto_que_siempre_usa": objeto,
        "cuantas_chapas": NUM_CANDIDATOS_POR_RONDA,
        "ronda": numero_ronda,
    }
    if numero_ronda > 1:
        payload["nota"] = (
            "La ronda anterior no dio suficientes chapas a la altura del Corpus Gold. "
            "Sé MÁS audaz en el salto semántico: aléjate más del significado literal, "
            "busca referentes más inesperados y más específicos."
        )

    temperatura = 1.0 if numero_ronda == 1 else 1.2

    completion = client.chat.completions.create(
        model=MODEL_GENERACION,
        temperature=temperatura,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "chapas_crudas_v3", "strict": True, "schema": construir_schema_generacion()},
        },
    )
    parsed = json.loads(completion.choices[0].message.content)
    return parsed.get("candidatos", []), completion


# =====================================================================
# LLAMADA 2 — JUEZ (contexto limpio: puntúa en frío, no fue el autor)
# =====================================================================

def construir_system_prompt_juez(repertorio):
    lineas_repertorio = []
    for op, ejemplos in repertorio.items():
        lineas_repertorio.append(f"- {op}:")
        for e in ejemplos:
            lineas_repertorio.append(f"    patrón: {e['patron_reutilizable']}  (mecanismo: {e['mecanismo_humoristico']})")
    repertorio_texto = "\n".join(lineas_repertorio)

    return f"""Eres un EVALUADOR crítico y exigente del humor de Melcochita. NO escribiste \
estas chapas: las juzgas en frío. Tu trabajo es puntuarlas con honestidad y clasificarlas — \
no hacerlas quedar bien. Es normal y esperado que varias sean mediocres.

EJEMPLOS REALES del Corpus Gold (el LISTÓN que deben alcanzar; una chapa buena está a esta \
altura de sorpresa, especificidad y absurdo):
{chr(10).join(f'  - "{e}"' for e in EJEMPLOS_CALIBRACION_JUEZ)}

EJEMPLOS QUE FALLAN por LITERALES/previsibles (si una chapa se parece a esto, castígala \
fuerte en adn_melcocha y sorpresa_semantica):
{chr(10).join(f'  - "{e}"' for e in EJEMPLOS_MALOS_V1)}

REPERTORIO de operaciones humorísticas observadas en el corpus (úsalo para CLASIFICAR cada \
chapa en una operación y para juzgar VARIEDAD — no para exigir ninguna en particular):
{repertorio_texto}

Para CADA chapa recibida (respeta su `indice`) reporta:
- indice: el mismo número entero que trae la chapa en el input.
- operacion: la operación del repertorio que MEJOR describe cómo está construida (de la lista dada).
- dominio_semantico_principal: dominio conceptual central (ANIMAL, OBJETO, COMIDA, GEOGRAFIA, \
PERSONAJE_POPULAR, PERSONAJE_MITICO, FENOMENO, etc. — nunca NACIONALIDAD_ORIGEN ni \
ATRIBUTO_PERSONAL_SENSIBLE).
- patron_estructural: el patrón con categorías entre corchetes que efectivamente usa.
- correccion_linguistica (1-5): ¿es gramatical y suena natural en español?
- conexion_con_input (1-5): ¿hay relación reconocible con el disparador, aunque no sea literal?
- sorpresa_semantica (1-5): ¿el referente es inesperado, no obvio?
- absurdo_controlado (1-5): ¿el absurdo es entendible/gracioso, no ruido aleatorio?
- adn_melcocha (1-5): asociación inesperada + imagen mental inmediata + especificidad + \
combinación de dominios alejados + sonoridad + absurdo entendible + brevedad. Penaliza fuerte \
lo literal y lo que se podría haber escrito SIN conocer a Melcochita.
- originalidad_vs_corpus (1-5): ¿qué tan lejos está de ser copia o variación cercana de una \
chapa real del corpus (incluidos los ejemplos de calibración)?
- riesgo_atributo_sensible: booleano honesto (orientación sexual, raza/etnia, discapacidad, \
religión, condición médica, o nacionalidad/origen usada como burla).

Sé severo y usa TODO el rango 1-5. No infles puntajes."""


def construir_schema_juez():
    return {
        "type": "object",
        "properties": {
            "evaluaciones": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "indice": {"type": "integer"},
                        "operacion": {"type": "string", "enum": OPERACIONES},
                        "dominio_semantico_principal": {"type": "string"},
                        "patron_estructural": {"type": "string"},
                        "correccion_linguistica": {"type": "integer"},
                        "conexion_con_input": {"type": "integer"},
                        "sorpresa_semantica": {"type": "integer"},
                        "absurdo_controlado": {"type": "integer"},
                        "adn_melcocha": {"type": "integer"},
                        "originalidad_vs_corpus": {"type": "integer"},
                        "riesgo_atributo_sensible": {"type": "boolean"},
                    },
                    "required": [
                        "indice", "operacion", "dominio_semantico_principal", "patron_estructural",
                        "correccion_linguistica", "conexion_con_input", "sorpresa_semantica",
                        "absurdo_controlado", "adn_melcocha", "originalidad_vs_corpus",
                        "riesgo_atributo_sensible",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["evaluaciones"],
        "additionalProperties": False,
    }


# Valores por defecto seguros para una chapa que el juez no llegó a puntuar:
# puntajes 0 (no supera ningún umbral, no se selecciona) y sin marca de riesgo
# (los puntajes bajos ya la dejan fuera; el filtro de seguridad textual sigue
# aplicando aparte). Así todo candidato conserva SIEMPRE las claves del contrato.
_DEFAULTS_EVALUACION = {
    "operacion": OPERACIONES[0],
    "dominio_semantico_principal": "DESCONOCIDO",
    "patron_estructural": "",
    "correccion_linguistica": 0,
    "conexion_con_input": 0,
    "sorpresa_semantica": 0,
    "absurdo_controlado": 0,
    "adn_melcocha": 0,
    "originalidad_vs_corpus": 0,
    "riesgo_atributo_sensible": False,
}


def juzgar_candidatos(client, repertorio, chapas_crudas, caracteristica, costumbre, objeto):
    """
    Recibe la lista de chapas crudas (cada una con cadena_asociativa, chapa,
    senal_utilizada) y devuelve la MISMA lista, cada dict enriquecido con las
    6 dimensiones + operacion/dominio/patron + riesgo_atributo_sensible. El
    juez trabaja en contexto limpio (no vio el prompt de generación).
    Devuelve (candidatos_evaluados, completion) — completion puede ser None
    si no había chapas que juzgar.
    """
    if not chapas_crudas:
        return [], None

    system_prompt = construir_system_prompt_juez(repertorio)

    payload = {
        "disparadores_originales": {
            "caracteristica": caracteristica,
            "costumbre": costumbre,
            "objeto": objeto,
        },
        "chapas_a_evaluar": [
            {"indice": i, "chapa": c["chapa"], "cadena_asociativa": c.get("cadena_asociativa", "")}
            for i, c in enumerate(chapas_crudas)
        ],
    }

    completion = client.chat.completions.create(
        model=MODEL_JUEZ,
        temperature=0.2,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "evaluaciones_chapa_v3", "strict": True, "schema": construir_schema_juez()},
        },
    )
    parsed = json.loads(completion.choices[0].message.content)

    evals_por_indice = {}
    for e in parsed.get("evaluaciones", []):
        idx = e.get("indice")
        if isinstance(idx, int) and 0 <= idx < len(chapas_crudas):
            evals_por_indice[idx] = e

    candidatos = []
    for i, cruda in enumerate(chapas_crudas):
        evaluacion = evals_por_indice.get(i, {})
        combinado = {
            "chapa": cruda["chapa"],
            "senal_utilizada": cruda.get("senal_utilizada", ""),
            "cadena_asociativa": cruda.get("cadena_asociativa", ""),
        }
        for clave, defecto in _DEFAULTS_EVALUACION.items():
            valor = evaluacion.get(clave, defecto)
            combinado[clave] = valor if valor is not None else defecto
        candidatos.append(combinado)
    return candidatos, completion


# =====================================================================
# SEGURIDAD, UMBRAL Y SELECCIÓN (sin cambios de criterio vs v2)
# =====================================================================

def contiene_palabra_alerta(texto):
    """
    Coincidencia por PALABRA COMPLETA (límites de palabra), no subcadena:
    "papagayo" no debe disparar la alerta de "gay". Defensa adicional al
    autoreporte del modelo, no la única línea de defensa.
    """
    t = texto.lower()
    return [p for p in PALABRAS_ALERTA_SENSIBLE if re.search(rf"\b{re.escape(p)}\b", t)]


def filtrar_seguridad(candidatos, textos_corpus_gold):
    validos, descartados = [], []
    for c in candidatos:
        motivos = []
        if _normalizar(c["chapa"]) in textos_corpus_gold:
            motivos.append("coincide literalmente con una chapa real del Corpus Gold")
        if c.get("riesgo_atributo_sensible"):
            motivos.append("el juez marcó riesgo_atributo_sensible=true")
        alertas = contiene_palabra_alerta(c["chapa"])
        if alertas:
            motivos.append(f"contiene palabra(s) de alerta: {alertas}")
        if motivos:
            descartados.append((c, motivos))
        else:
            validos.append(c)
    return validos, descartados


def cumple_umbral(c):
    return (
        c["adn_melcocha"] >= UMBRAL_ADN_MELCOCHA
        and c["sorpresa_semantica"] >= UMBRAL_SORPRESA_SEMANTICA
        and c["originalidad_vs_corpus"] >= UMBRAL_ORIGINALIDAD_VS_CORPUS
    )


def seleccionar_top5(candidatos_que_cumplen):
    return sorted(
        candidatos_que_cumplen,
        key=lambda c: (-c["adn_melcocha"], -c["sorpresa_semantica"], -c["originalidad_vs_corpus"]),
    )[:NUM_RESULTADOS]


def generar_para_perfil(client, repertorio, textos_corpus_gold, nombre, caracteristica, costumbre, objeto, guardar_raw_en=None, objetivo_candidatos=NUM_RESULTADOS):
    """
    Ejecuta hasta MAX_RONDAS. Cada ronda = LLAMADA 1 (genera chapas crudas
    con razonamiento) + LLAMADA 2 (el juez las puntúa en frío). No relaja
    umbrales; corta apenas reúne `objetivo_candidatos` que los superen.

    `objetivo_candidatos` controla LATENCIA sin tocar los criterios: el CLI
    usa el default (NUM_RESULTADOS=5) porque muestra un TOP 5; la web pasa
    1-2, así la ronda 1 casi siempre basta y no se dispara una segunda ronda
    solo para rankear finalistas que el usuario nunca ve. Contrato de retorno
    idéntico a v2.
    """
    todos_candidatos = []
    raw_por_ronda = []
    usage_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    rondas_usadas = 0

    def _acumular_usage(completion):
        if completion is None:
            return
        usage = getattr(completion, "usage", None)
        if usage:
            usage_total["prompt_tokens"] += usage.prompt_tokens
            usage_total["completion_tokens"] += usage.completion_tokens
            usage_total["total_tokens"] += usage.total_tokens

    for ronda in range(1, MAX_RONDAS + 1):
        rondas_usadas = ronda
        try:
            chapas_crudas, comp_gen = generar_ronda(client, nombre, caracteristica, costumbre, objeto, ronda)
            candidatos_evaluados, comp_juez = juzgar_candidatos(
                client, repertorio, chapas_crudas, caracteristica, costumbre, objeto
            )
        except openai_module.OpenAIError as e:
            print(f"ERROR de la API de OpenAI (ronda {ronda}): {e}", file=sys.stderr)
            sys.exit(1)

        _acumular_usage(comp_gen)
        _acumular_usage(comp_juez)
        raw_por_ronda.append({
            "ronda": ronda,
            "generacion": comp_gen.model_dump() if comp_gen is not None else None,
            "juicio": comp_juez.model_dump() if comp_juez is not None else None,
        })

        todos_candidatos.extend(candidatos_evaluados)

        validos_seg, _ = filtrar_seguridad(todos_candidatos, textos_corpus_gold)
        que_cumplen = [c for c in validos_seg if cumple_umbral(c)]
        if len(que_cumplen) >= objetivo_candidatos:
            break  # objetivo alcanzado: no se necesita una ronda adicional

    validos_seguridad, descartados_seguridad = filtrar_seguridad(todos_candidatos, textos_corpus_gold)
    que_cumplen_umbral = [c for c in validos_seguridad if cumple_umbral(c)]
    no_cumplen_umbral = [c for c in validos_seguridad if not cumple_umbral(c)]
    seleccionados = seleccionar_top5(que_cumplen_umbral)

    if guardar_raw_en:
        guardar_raw_en.parent.mkdir(parents=True, exist_ok=True)
        with open(guardar_raw_en, "w", encoding="utf-8") as f:
            json.dump({"rondas": raw_por_ronda}, f, ensure_ascii=False, indent=2)

    return {
        "candidatos_totales": todos_candidatos,
        "descartados_seguridad": descartados_seguridad,
        "no_cumplen_umbral": no_cumplen_umbral,
        "que_cumplen_umbral": que_cumplen_umbral,
        "seleccionados": seleccionados,
        "rondas_usadas": rondas_usadas,
        "usage_total": usage_total,
    }


def imprimir_resultado_perfil(nombre_perfil, entrada, resultado):
    print("\n" + "=" * 100)
    print(f"PERFIL: {nombre_perfil}  —  {entrada}")
    print("=" * 100)
    print(f"Candidatos generados: {len(resultado['candidatos_totales'])} "
          f"en {resultado['rondas_usadas']} ronda(s) "
          f"({NUM_CANDIDATOS_POR_RONDA} por ronda)")
    print(f"Descartados por seguridad: {len(resultado['descartados_seguridad'])}")
    print(f"No alcanzaron el umbral (adn_melcocha/sorpresa/originalidad >= 4): "
          f"{len(resultado['no_cumplen_umbral'])}")
    print(f"Cumplieron el umbral: {len(resultado['que_cumplen_umbral'])}")

    if len(resultado["seleccionados"]) < NUM_RESULTADOS:
        print(f"\n*** AVISO: solo {len(resultado['seleccionados'])} candidatos superaron el umbral "
              f"tras {resultado['rondas_usadas']} ronda(s) (se esperaban {NUM_RESULTADOS}). "
              f"No se relajaron los criterios. ***")

    print(f"\nTOP {len(resultado['seleccionados'])} FINALISTAS:")
    for i, c in enumerate(resultado["seleccionados"], start=1):
        print(f"\n  [{i}] \"{c['chapa']}\"")
        print(f"      cadena_asociativa: {c.get('cadena_asociativa', '')}")
        print(f"      señal_utilizada: {c['senal_utilizada']}   operación: {c['operacion']}   "
              f"dominio: {c['dominio_semantico_principal']}")
        print(f"      patrón_estructural: {c['patron_estructural']}")
        print(f"      correccion_linguistica={c['correccion_linguistica']}  "
              f"conexion_con_input={c['conexion_con_input']}  "
              f"sorpresa_semantica={c['sorpresa_semantica']}")
        print(f"      absurdo_controlado={c['absurdo_controlado']}  "
              f"adn_melcocha={c['adn_melcocha']}  "
              f"originalidad_vs_corpus={c['originalidad_vs_corpus']}")


def analizar_repeticiones_globales(todos_los_finalistas):
    conteo_patrones = defaultdict(list)
    conteo_operaciones = defaultdict(list)
    for perfil, c in todos_los_finalistas:
        conteo_patrones[c["patron_estructural"]].append((perfil, c["chapa"]))
        conteo_operaciones[c["operacion"]].append((perfil, c["chapa"]))

    patrones_repetidos = {p: v for p, v in conteo_patrones.items() if len(v) > 1}
    operaciones_repetidas = {o: v for o, v in conteo_operaciones.items() if len(v) > 3}  # >3 de 20 ya es notable

    return patrones_repetidos, operaciones_repetidas, conteo_operaciones


def ejecutar_perfil_cli():
    parser = argparse.ArgumentParser(description="Genera chapas nuevas al estilo Melcochita (MVP, sin interfaz).")
    parser.add_argument("--nombre", required=True)
    parser.add_argument("--caracteristica", required=True)
    parser.add_argument("--costumbre", required=True)
    parser.add_argument("--objeto", required=True)
    args = parser.parse_args()

    repertorio, n_usables = cargar_repertorio_generativo()
    textos_corpus_gold = cargar_corpus_gold_textos()
    print(f"Repertorio (para el juez): {n_usables} filas habilitadas, {len(repertorio)} operaciones.", file=sys.stderr)

    api_key = cargar_api_key()
    client = OpenAI(api_key=api_key)

    resultado = generar_para_perfil(
        client, repertorio, textos_corpus_gold,
        args.nombre, args.caracteristica, args.costumbre, args.objeto,
        guardar_raw_en=OUTPUT_DIR / "ultima_generacion_raw.json",
    )

    entrada = f"caracteristica={args.caracteristica!r} costumbre={args.costumbre!r} objeto={args.objeto!r}"
    imprimir_resultado_perfil(args.nombre, entrada, resultado)

    u = resultado["usage_total"]
    print(f"\nModelos: generación={MODEL_GENERACION} juez={MODEL_JUEZ}  |  Tokens: prompt={u['prompt_tokens']} "
          f"completion={u['completion_tokens']} total={u['total_tokens']}")


if __name__ == "__main__":
    ejecutar_perfil_cli()
