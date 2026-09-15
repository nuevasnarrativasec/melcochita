"""
generar_chapa.py (v2)

Piloto Melcochómetro — Motor generativo con "ADN Melcocha" real.

La primera versión producía construcciones correctas pero DEMASIADO
LITERALES (ej. "León despeinado" para "pelo largo y despeinado"): el
input se traducía casi textualmente. Esta versión trata el input del
usuario como un DISPARADOR SEMÁNTICO, no como una descripción a calcar:

    rasgo -> asociación semántica -> referente inesperado ->
    desplazamiento absurdo -> patrón compatible del corpus -> chapa

Cambios sobre v1:
  - 12 candidatos internos por ronda (antes 5), con operación asignada y
    forzada por candidato para garantizar diversidad real.
  - Scoring de 6 dimensiones separadas (ya no un solo "calidad_estimada"):
    correccion_linguistica, conexion_con_input, sorpresa_semantica,
    absurdo_controlado, adn_melcocha, originalidad_vs_corpus.
  - Para pasar al TOP 5 se exige adn_melcocha>=4 AND sorpresa_semantica>=4
    AND originalidad_vs_corpus>=4 (umbral duro, no promedio).
  - Si la primera ronda no produce 5 candidatos que superen el umbral, se
    hace UNA segunda ronda (más candidatos, no criterios más laxos) y se
    combinan ambas rondas antes de seleccionar.
  - Selección final: top 5 por adn_melcocha (desempate por
    sorpresa_semantica, luego originalidad_vs_corpus) entre los que
    superan el umbral — NO por promedio de las 6 dimensiones.

Sigue sin copiar literalmente ninguna chapa del Corpus Gold y sin usar
componentes marcados como no aptos para generación (habilitado_generacion
=False, o NACIONALIDAD_ORIGEN/ATRIBUTO_PERSONAL_SENSIBLE).

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
import unicodedata
import difflib
from collections import defaultdict
from functools import lru_cache
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
CHAPAS_ORIGINALES_CURADAS = PROJECT_ROOT / "data" / "corpus" / "chapas_originales_curadas.csv"
REGLAS_EXCLUSION = PROJECT_ROOT / "data" / "safety" / "reglas_exclusion.csv"

OUTPUT_DIR = PROJECT_ROOT / "outputs" / "generaciones"

# Modelo de calidad (no el económico usado para extracción): generación
# creativa con reglas de seguridad estrictas; se prioriza calidad sobre
# costo para este piloto.
MODEL = "gpt-4o"

NUM_CANDIDATOS_POR_RONDA = 12
NUM_RESULTADOS = 5
MAX_RONDAS = 2

UMBRAL_ADN_MELCOCHA = 4
UMBRAL_SORPRESA_SEMANTICA = 4
UMBRAL_ORIGINALIDAD_VS_CORPUS = 4
UMBRAL_SIMILITUD_REFERENCIA = 0.90

# Estadísticas observadas en las 67 chapas originales únicas. Se usan como
# prior estilístico: el corpus es extremadamente breve y concentra unos pocos
# mecanismos recurrentes.
MEDIANA_PALABRAS_ORIGINALES = 3
MAX_PALABRAS_ESTILO_FUERTE = 5
FRECUENCIA_MECANISMOS_ORIGINALES = {
    "YUXTAPOSICION_BREVE": 18,
    "ENCADENAMIENTO_DE": 12,
    "REFERENCIA_CULTURAL_DESPLAZADA": 11,
    "HIBRIDACION_CON": 7,
    "FORMULA_LE_DICEN": 5,
    "ETIQUETA_MINIMA": 4,
    "COMPOSICION_ABSURDA": 3,
    "REFERENCIA_CULTURAL_DEFORMADA": 3,
    "LOCALIZACION_ABSURDA": 2,
    "DEFORMACION_LEXICA": 1,
    "EQUIVALENCIA_COLECTIVA": 1,
}
MECANISMOS_CORPUS = list(FRECUENCIA_MECANISMOS_ORIGINALES)

OPERACIONES = [
    "COMPARAR", "ANIMALIZAR", "COSIFICAR", "REFERENCIAR", "LOCALIZAR", "DEFORMAR",
    "YUXTAPONER_DIRECTO_SIN_NEXO", "COMPONER_CON_NEXO_CON", "ENCADENAR_CON_DE",
    "HIBRIDAR_MISMO_DOMINIO", "ATRIBUIR_VIA_FORMULA_DISCURSIVA",
]

CATEGORIAS_EXCLUIDAS_DE_INSPIRACION = {"NACIONALIDAD_ORIGEN", "ATRIBUTO_PERSONAL_SENSIBLE"}

PALABRAS_ALERTA_SENSIBLE = [
    # Solo categorías protegidas/sensibles que no deben convertirse en
    # motivo de burla. El corpus histórico puede conservarlas, pero no se
    # usan para generar nuevas chapas.
    "gay", "lesbiana", "homosexual", "bisexual", "trans", "maricón", "marica",
    "discapacit", "invalid", "retrasad", "mongol", "autista",
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
    "vaso con brazos", "zapatilla con ojos", "sonrisa de cebra",
    "meteorito con lentes",
]


def cargar_api_key():
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not api_key.strip():
        print("ERROR: OPENAI_API_KEY no está configurada (o vacía) en .env.", file=sys.stderr)
        sys.exit(1)
    return api_key


# Marco que el modelo a veces antepone al remate ("A Melcochita le dicen X",
# "A X le decían Y", "Le dicen Z"). La chapa debe quedar PELADA: solo el remate.
_MARCO_CHAPA = re.compile(
    r"^\s*(?:a\s+.+?\s+)?le\s+(?:dic\w*|dec\w*|llam\w*|dij\w*|conoc\w*)\s+",
    re.IGNORECASE,
)


def _limpiar_chapa(texto):
    """Quita marcos tipo 'A Melcochita le dicen ...' y deja solo el remate.

    La chapa se muestra pelada; el marco discursivo ('Mi querido...') lo pone
    voz.py. Si el marco fuera todo el texto, se conserva el original para no
    devolver algo vacío.
    """
    if not texto:
        return texto
    t = texto.strip()
    m = _MARCO_CHAPA.match(t)
    if not m:
        return t  # ya venía pelada: no la tocamos
    nuevo = t[m.end():].strip()
    if not nuevo:
        return t  # el marco era todo el texto: conservamos el original
    return nuevo[0].upper() + nuevo[1:]


def _normalizar(texto):
    t = (texto or "").strip().lower()
    t = re.sub(r"[¡¿!?.,;:\"'‘’“”]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _normalizar_ascii(texto):
    """Normalización auxiliar para reglas de seguridad y comparación tolerante."""
    t = _normalizar(texto)
    t = unicodedata.normalize("NFKD", t)
    return "".join(c for c in t if not unicodedata.combining(c))


@lru_cache(maxsize=1)
def cargar_originales_curadas():
    if not CHAPAS_ORIGINALES_CURADAS.exists():
        return []
    with open(CHAPAS_ORIGINALES_CURADAS, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=1)
def cargar_reglas_exclusion():
    if not REGLAS_EXCLUSION.exists():
        return []
    with open(REGLAS_EXCLUSION, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def detectar_reglas_exclusion(texto, ambito="salida"):
    """
    Aplica únicamente reglas relativas a atributos protegidos/sensibles.
    Otras categorías editoriales del diccionario histórico (edad, cuerpo,
    violencia no gráfica, etc.) permanecen documentadas pero no bloquean
    automáticamente esta versión del generador.
    """
    categorias_activas = {
        "ORIENTACION_SEXUAL", "IDENTIDAD_GENERO", "ORIENTACION_SEXUAL_CODIFICADA",
        "NACIONALIDAD_ORIGEN", "DISCAPACIDAD", "RELIGION_IDENTIDAD",
        "SALUD_CONDICION_MEDICA",
    }
    t = _normalizar_ascii(texto)
    hallazgos = []
    for regla in cargar_reglas_exclusion():
        if regla.get("accion") != "BLOQUEAR" or regla.get("categoria") not in categorias_activas:
            continue
        ambito_regla = (regla.get("ambito") or "todos").strip().lower()
        if ambito_regla not in {"todos", ambito}:
            continue
        patron = regla.get("patron", "")
        if not patron:
            continue
        if regla.get("tipo") == "literal":
            coincide = patron.lower() in t
        else:
            coincide = bool(re.search(patron, t, flags=re.IGNORECASE))
        if coincide:
            hallazgos.append({
                "id": regla.get("id", ""),
                "categoria": regla.get("categoria", ""),
                "razon": regla.get("razon", ""),
            })
    return hallazgos


def sanitizar_senales(caracteristica, costumbre, objeto):
    """
    Nunca usa como disparador una señal que coincide con categorías bloqueadas.
    Esto evita casos donde la salida parece inocua, pero la lógica de burla
    depende de una característica sensible (p.ej. orientación sexual).
    """
    senales = {
        "caracteristica": caracteristica or "",
        "costumbre": costumbre or "",
        "objeto": objeto or "",
    }
    descartadas = {}
    for clave, valor in list(senales.items()):
        hallazgos = detectar_reglas_exclusion(valor, ambito="entrada")
        if hallazgos:
            descartadas[clave] = hallazgos
            senales[clave] = ""
    return senales, descartadas


def _riesgo_protegido_original(registro):
    categoria = (registro.get("categoria_riesgo") or "").upper()
    bloqueos = (
        "ORIENTACION_SEXUAL", "NACIONALIDAD_ORIGEN", "DISCAPACIDAD",
        "RELIGION", "SALUD_CONDICION_MEDICA", "IDENTIDAD_GENERO",
        "SEXUALIZACION_MISOGINIA",
    )
    return any(b in categoria for b in bloqueos)


def cargar_originales_publicables():
    """
    Pool de originales que sí pueden aparecer directamente en el generador.
    Se preserva TODO el corpus en CSV; aquí solo se excluyen entradas cuya
    comicidad depende de un atributo protegido o de misoginia explícita.
    """
    return [r for r in cargar_originales_curadas() if not _riesgo_protegido_original(r)]


def cargar_calibracion_originales(max_ejemplos=24):
    """
    Usa una muestra amplia de originales publicables para calibrar ritmo,
    mecanismos y densidad visual. Ya no excluye automáticamente edad,
    apariencia, humor negro o tono áspero: forman parte del corpus cómico.
    """
    base = cargar_originales_publicables()
    ejemplos = []
    mecanismos_vistos = set()
    for r in base:
        mecanismo = r.get("mecanismo_observado", "")
        if mecanismo and mecanismo not in mecanismos_vistos:
            ejemplos.append(r.get("chapa_original", ""))
            mecanismos_vistos.add(mecanismo)
        if len(ejemplos) >= max_ejemplos:
            break
    if len(ejemplos) < max_ejemplos:
        for r in base:
            chapa = r.get("chapa_original", "")
            if chapa and chapa not in ejemplos:
                ejemplos.append(chapa)
            if len(ejemplos) >= max_ejemplos:
                break

    logicas = []
    vistas = set()
    for r in base:
        clave = (r.get("mecanismo_observado", ""), r.get("patron_abstracto", ""))
        if clave in vistas:
            continue
        vistas.add(clave)
        logicas.append(
            f"{r.get('mecanismo_observado', '')}: {r.get('patron_abstracto', '')} — "
            f"{r.get('logica_observada', '')}"
        )
    return ejemplos, logicas


def cargar_corpus_gold_textos():
    """
    Corpus de NO-COPIA: une el Gold previo con TODAS las chapas originales
    curadas, incluidas las bloqueadas. Así ninguna original puede reaparecer
    literalmente, aunque se conserve como material histórico.
    """
    with open(CHAPAS_UNICAS_GOLD, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    textos = {_normalizar(r["texto_canonico"]) for r in rows}
    textos.update(
        _normalizar(r.get("chapa_original", ""))
        for r in cargar_originales_curadas()
        if r.get("chapa_original")
    )
    return {t for t in textos if t}


def es_variacion_cercana_referencia(texto, textos_referencia):
    """
    Defensa contra copias casi literales. Es deliberadamente conservadora:
    solo dispara con similitud muy alta; la originalidad semántica sigue
    evaluándose además por el modelo.
    """
    candidato = _normalizar_ascii(texto)
    if len(candidato) < 8:
        return None
    for ref in textos_referencia:
        refn = _normalizar_ascii(ref)
        if len(refn) < 8:
            continue
        similitud = difflib.SequenceMatcher(None, candidato, refn).ratio()
        if similitud >= UMBRAL_SIMILITUD_REFERENCIA:
            return {"referencia": ref, "similitud": round(similitud, 3)}
    return None


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


def asignar_operaciones(n, ronda_seed):
    """
    Fuerza diversidad real: reparte las 11 operaciones entre los n
    candidatos (cada una al menos una vez si n>=11, sin repetir hasta
    agotar el ciclo), en orden aleatorio distinto por ronda.
    """
    rnd = random.Random(ronda_seed)
    ciclos = []
    ops = OPERACIONES[:]
    while len(ciclos) < n:
        rnd.shuffle(ops)
        ciclos.extend(ops)
    return ciclos[:n]


def construir_system_prompt(repertorio):
    ejemplos_originales, logicas_originales = cargar_calibracion_originales()
    lineas_repertorio = []
    for op, ejemplos in repertorio.items():
        lineas_repertorio.append(f"- {op}:")
        for e in ejemplos:
            lineas_repertorio.append(f"    patrón: {e['patron_reutilizable']}  (mecanismo: {e['mecanismo_humoristico']})")
    repertorio_texto = "\n".join(lineas_repertorio)

    return f"""Eres el motor generativo del "Melcochómetro": generas chapas NUEVAS al \
estilo del humorista peruano Melcochita.

CAMBIO CONCEPTUAL CLAVE: el input del usuario (característica, costumbre, objeto) es un \
DISPARADOR SEMÁNTICO, NO una descripción a traducir literalmente. NO es obligatorio que \
las palabras del usuario aparezcan en la chapa. El proceso mental que debes seguir para \
cada candidato es:

    rasgo del usuario -> asociación semántica -> referente INESPERADO ->
    desplazamiento absurdo -> patrón compatible del repertorio -> chapa

EJEMPLOS QUE FALLARON en la primera prueba (demasiado literales/previsibles — NO repitas \
este nivel de literalidad):
{chr(10).join(f'  - "{e}"' for e in EJEMPLOS_MALOS_V1)}
Todos ellos son solo "[categoría] + descripción casi textual del input". Eso es \
insuficiente.

EJEMPLOS REALES del Corpus Gold que ilustran el NIVEL de desplazamiento semántico, \
especificidad y absurdo que buscamos (úsalos SOLO para calibrar el nivel de sorpresa — \
JAMÁS los copies, recombines sus palabras, ni generes variaciones cercanas de ellos):
{chr(10).join(f'  - "{e}"' for e in EJEMPLOS_CALIBRACION_CORPUS)}

CHAPAS ORIGINALES aportadas como referencia adicional. Se conserva su comicidad y se usa una \
muestra amplia del corpus publicable para calibrar ritmo, imagen mental y nivel de desplazamiento. \
Úsalas solo como referencia estructural; NO copies ni hagas variaciones cercanas:
{chr(10).join(f'  - "{e}"' for e in ejemplos_originales)}

LÓGICAS ABSTRACTAS observadas en las chapas originales publicables:
{chr(10).join(f'  - {e}' for e in logicas_originales)}

La lógica buscada NO es copiar vocabulario sino reproducir el movimiento mental: partir \
de una señal, alejarse de lo literal y aterrizar en una imagen concreta, breve e inesperada.

REPERTORIO REAL observado en el corpus (operaciones con patrones/mecanismos de ejemplo — \
inspiración de ESTRUCTURA, nunca de palabras a copiar):
{repertorio_texto}

REGLAS DE CONSTRUCCIÓN:
- El "nombre_o_apodo" es solo CONTEXTO: normalmente NO debe aparecer dentro de la chapa.
- La chapa es SOLO el remate PELADO (p. ej. "jaula abandonada", "cuatro tuercas"): entrega únicamente el remate, SIN introducción. NUNCA lo enmarques con fórmulas como "A ... le dicen", "Le dicen", "Le decían", "Lo/La conocen como".
- NUNCA menciones a "Melcochita" dentro de la chapa: Melcochita es quien la dice, jamás el objeto de la burla. La chapa es SIEMPRE sobre la víctima (el usuario), no sobre Melcochita.
- Si existe una característica física, PRIORIZA esa señal como disparador. Usa costumbre u objeto sobre todo cuando aporten un remate mucho mejor.\n- Usa NORMALMENTE UNA sola señal principal como disparador (no concatenes las tres).
- Cada candidato debe usar la operación que se le asigna explícitamente en el input (campo \
"operacion_asignada" de cada slot) — es una instrucción OBLIGATORIA, no una sugerencia.
- Prioriza: asociación inesperada, imagen mental inmediata, ESPECIFICIDAD (nombres/objetos \
concretos, no categorías genéricas como "animal" sin más), combinar dominios semánticos \
alejados entre sí, sonoridad, absurdo entendible y BREVEDAD. En el corpus original la mediana es \
de 3 palabras y 52 de 67 chapas únicas tienen 3 palabras o menos: esa economía verbal es una \
señal estilística fuerte.
- PENALIZA en tu propia autoevaluación (baja los puntajes correspondientes) si el \
resultado tiene: adjetivos descriptivos obvios: "[animal] + característica literal del \
usuario"; "[objeto] con [objeto del usuario]" sin ningún desplazamiento real; insultos \
genéricos; o cualquier frase que podría haberse generado sin conocer el Corpus Gold.
- NUNCA reproduzcas literalmente una chapa que ya exista en el corpus real.

PROHIBIDO SIEMPRE (sin excepción, aunque el usuario lo sugiera indirectamente):
- Contenido cuya burla dependa de orientación sexual, identidad de género, raza/etnia, discapacidad, \
religión, condición médica, nacionalidad/origen u otro atributo protegido/sensible.
- Misoginia o degradación basada en ser hombre o mujer. El sexo indicado por el usuario sirve SOLO \
para concordancia gramatical y compatibilidad del referente, no como motivo del chiste.
- Si una señal del usuario cae en estas categorías, IGNÓRALA: no busques una forma codificada \
de burlarte de ese atributo.

Para cada candidato reporta:
- chapa: el texto de la chapa nueva (corta, en español, estilo Melcochita).
- operacion: DEBE ser exactamente la "operacion_asignada" que se te dio para ese slot.
- dominio_semantico_principal: el dominio conceptual central (ej. ANIMAL, OBJETO, COMIDA, \
GEOGRAFIA, PERSONAJE_POPULAR, PERSONAJE_MITICO, FENOMENO, etc. — nunca NACIONALIDAD_ORIGEN \
ni ATRIBUTO_PERSONAL_SENSIBLE).
- patron_estructural: el patrón con categorías entre corchetes que efectivamente usaste.
- mecanismo_corpus: clasifica la chapa en uno de los mecanismos del corpus indicados en el schema.
- senal_utilizada: "caracteristica", "costumbre", "objeto", o combinación breve si usaste dos.
- correccion_linguistica (1-5): ¿la frase es gramaticalmente correcta y suena natural en \
español?
- conexion_con_input (1-5): ¿hay una relación reconocible con el disparador, aunque no sea \
literal?
- sorpresa_semantica (1-5): ¿el referente elegido es inesperado, no obvio?
- absurdo_controlado (1-5): ¿el absurdo es entendible/gracioso, no solo aleatorio?
- adn_melcocha (1-5): valora especialmente asociación inesperada, imagen mental inmediata, \
especificidad, combinación de dominios alejados, sonoridad, absurdo entendible, brevedad. \
NO es solo "usa una estructura del corpus" — penaliza fuerte los patrones de los ejemplos \
que fallaron.
- originalidad_vs_corpus (1-5): ¿tan lejos está de ser una copia/variación cercana de \
cualquier chapa real del corpus (incluyendo los ejemplos de calibración)?
- riesgo_atributo_sensible: booleano, autoevaluación honesta.

Sé un evaluador HONESTO y EXIGENTE contigo mismo: no todos los candidatos deben salir con \
puntajes altos. Es normal y esperado que varios candidatos no superen el nivel del Corpus \
Gold."""


def construir_schema():
    return {
        "type": "object",
        "properties": {
            "candidatos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "chapa": {"type": "string"},
                        "operacion": {"type": "string", "enum": OPERACIONES},
                        "dominio_semantico_principal": {"type": "string"},
                        "patron_estructural": {"type": "string"},
                        "mecanismo_corpus": {"type": "string", "enum": MECANISMOS_CORPUS},
                        "senal_utilizada": {"type": "string"},
                        "correccion_linguistica": {"type": "integer"},
                        "conexion_con_input": {"type": "integer"},
                        "sorpresa_semantica": {"type": "integer"},
                        "absurdo_controlado": {"type": "integer"},
                        "adn_melcocha": {"type": "integer"},
                        "originalidad_vs_corpus": {"type": "integer"},
                        "riesgo_atributo_sensible": {"type": "boolean"},
                    },
                    "required": [
                        "chapa", "operacion", "dominio_semantico_principal", "patron_estructural",
                        "mecanismo_corpus", "senal_utilizada", "correccion_linguistica", "conexion_con_input",
                        "sorpresa_semantica", "absurdo_controlado", "adn_melcocha",
                        "originalidad_vs_corpus", "riesgo_atributo_sensible",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["candidatos"],
        "additionalProperties": False,
    }


def generar_ronda(client, repertorio, nombre, caracteristica, costumbre, objeto, numero_ronda, sexo="no_indica"):
    system_prompt = construir_system_prompt(repertorio)
    operaciones_asignadas = asignar_operaciones(NUM_CANDIDATOS_POR_RONDA, ronda_seed=numero_ronda)

    payload = {
        "nombre_o_apodo": nombre,
        "caracteristica": caracteristica,
        "costumbre": costumbre,
        "objeto_que_siempre_usa": objeto,
        "sexo": sexo,
        "instruccion_sexo": "Usar solo para concordancia gramatical/compatibilidad; nunca como motivo de burla.",
        "ronda": numero_ronda,
        "slots": [{"indice": i + 1, "operacion_asignada": op} for i, op in enumerate(operaciones_asignadas)],
    }
    if numero_ronda > 1:
        payload["nota"] = (
            "Ronda anterior no produjo suficientes candidatos con adn_melcocha>=4, "
            "sorpresa_semantica>=4 y originalidad_vs_corpus>=4. Sé más audaz en el "
            "desplazamiento semántico: aléjate más del significado literal del input."
        )

    temperatura = 1.0 if numero_ronda == 1 else 1.2

    completion = client.chat.completions.create(
        model=MODEL,
        temperature=temperatura,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "candidatos_chapa_v2", "strict": True, "schema": construir_schema()},
        },
    )
    return completion


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
            motivos.append("coincide literalmente con una chapa del corpus de referencia (Gold + originales)")
        if c.get("riesgo_atributo_sensible"):
            motivos.append("el propio modelo marcó riesgo_atributo_sensible=true")

        alertas = contiene_palabra_alerta(c["chapa"])
        if alertas:
            motivos.append(f"contiene palabra(s) de alerta heredadas: {alertas}")

        if re.search(r"\bmelcochita\b", c["chapa"], flags=re.IGNORECASE):
            motivos.append("menciona a Melcochita (la chapa debe ser sobre la victima, no sobre Melcochita)")

        reglas = detectar_reglas_exclusion(c["chapa"], ambito="salida")
        if reglas:
            motivos.append(
                "activa regla(s) del diccionario de exclusión: "
                + ", ".join(f"{r['id']}:{r['categoria']}" for r in reglas)
            )

        cercana = es_variacion_cercana_referencia(c["chapa"], textos_corpus_gold)
        if cercana:
            motivos.append(
                f"variación demasiado cercana a una chapa de referencia "
                f"(similitud={cercana['similitud']})"
            )

        if motivos:
            descartados.append((c, motivos))
        else:
            validos.append(c)
    return validos, descartados


def calcular_score_estilo_original(c, caracteristica_disponible=True):
    """Score determinista 0-100 inspirado en propiedades medibles del corpus.

    No reemplaza la evaluación creativa del modelo: la complementa. Pondera
    economía verbal, frecuencia real del mecanismo y uso del rasgo físico
    cuando el usuario lo proporcionó.
    """
    palabras = re.findall(r"\b\w+\b", c.get("chapa", ""), flags=re.UNICODE)
    n = len(palabras)
    if n <= 3:
        brevedad = 40
    elif n <= 5:
        brevedad = 32
    elif n <= 7:
        brevedad = 18
    else:
        brevedad = 5

    mecanismo = c.get("mecanismo_corpus", "")
    freq = FRECUENCIA_MECANISMOS_ORIGINALES.get(mecanismo, 0)
    maxfreq = max(FRECUENCIA_MECANISMOS_ORIGINALES.values())
    estructura = round(35 * (freq / maxfreq)) if maxfreq else 0

    usa_caracteristica = "caracteristica" in (c.get("senal_utilizada") or "").lower()
    fisico = 20 if (caracteristica_disponible and usa_caracteristica) else (8 if not caracteristica_disponible else 0)

    # Bonus pequeño por conexión fuerte sin volver la chapa literal.
    conexion = min(int(c.get("conexion_con_input", 0)), 5)
    bonus = conexion
    return min(100, brevedad + estructura + fisico + bonus)


def cumple_umbral(c):
    return (
        c["adn_melcocha"] >= UMBRAL_ADN_MELCOCHA
        and c["sorpresa_semantica"] >= UMBRAL_SORPRESA_SEMANTICA
        and c["originalidad_vs_corpus"] >= UMBRAL_ORIGINALIDAD_VS_CORPUS
    )


def seleccionar_top5(candidatos_que_cumplen):
    return sorted(
        candidatos_que_cumplen,
        key=lambda c: (-c.get("score_estilo_original", 0), -c["adn_melcocha"], -c["sorpresa_semantica"], -c["originalidad_vs_corpus"]),
    )[:NUM_RESULTADOS]


def generar_para_perfil(client, repertorio, textos_corpus_gold, nombre, caracteristica, costumbre, objeto, sexo="no_indica", guardar_raw_en=None, objetivo_candidatos=NUM_RESULTADOS):
    """
    Ejecuta hasta MAX_RONDAS de generación (12 candidatos c/u), sin
    relajar los umbrales, hasta reunir `objetivo_candidatos` candidatos que
    los superen (o agotar las rondas).

    `objetivo_candidatos` controla LATENCIA sin tocar los criterios (portado
    de la optimización de main): el CLI usa el default (NUM_RESULTADOS=5)
    porque muestra un TOP 5; la web puede pasar un número menor para cortar
    antes y responder más rápido. La selección final (seleccionar_top5) y
    los umbrales no cambian.
    Devuelve: dict con candidatos_totales, candidatos_validos_seguridad,
    candidatos_que_cumplen_umbral, seleccionados, rondas_usadas, usage_total.
    """
    senales_limpias, senales_descartadas = sanitizar_senales(caracteristica, costumbre, objeto)
    caracteristica = senales_limpias["caracteristica"]
    costumbre = senales_limpias["costumbre"]
    objeto = senales_limpias["objeto"]

    if not any(v.strip() for v in (caracteristica, costumbre, objeto)):
        raise ValueError(
            "Las señales disponibles se descartaron por seguridad. "
            "Usa rasgos, costumbres u objetos que no dependan de atributos sensibles."
        )

    todos_candidatos = []
    raw_por_ronda = []
    usage_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    rondas_usadas = 0

    for ronda in range(1, MAX_RONDAS + 1):
        rondas_usadas = ronda
        try:
            completion = generar_ronda(client, repertorio, nombre, caracteristica, costumbre, objeto, ronda, sexo=sexo)
        except openai_module.OpenAIError as e:
            print(f"ERROR de la API de OpenAI (ronda {ronda}): {e}", file=sys.stderr)
            sys.exit(1)

        raw_por_ronda.append(completion.model_dump())
        usage = getattr(completion, "usage", None)
        if usage:
            usage_total["prompt_tokens"] += usage.prompt_tokens
            usage_total["completion_tokens"] += usage.completion_tokens
            usage_total["total_tokens"] += usage.total_tokens

        parsed = json.loads(completion.choices[0].message.content)
        nuevos = parsed.get("candidatos", [])
        for c in nuevos:
            c["chapa"] = _limpiar_chapa(c.get("chapa", ""))
            c["score_estilo_original"] = calcular_score_estilo_original(c, caracteristica_disponible=bool(caracteristica.strip()))
        todos_candidatos.extend(nuevos)

        validos_seg, _ = filtrar_seguridad(todos_candidatos, textos_corpus_gold)
        que_cumplen = [c for c in validos_seg if cumple_umbral(c)]

        if len(que_cumplen) >= objetivo_candidatos:
            break  # ya hay suficientes; corte temprano para bajar latencia

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
        "senales_descartadas_seguridad": list(senales_descartadas.keys()),
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
    parser.add_argument("--sexo", choices=["hombre", "mujer", "no_indica"], default="no_indica")
    args = parser.parse_args()

    repertorio, n_usables = cargar_repertorio_generativo()
    textos_corpus_gold = cargar_corpus_gold_textos()
    print(f"Repertorio generativo: {n_usables} filas habilitadas, {len(repertorio)} operaciones.", file=sys.stderr)

    api_key = cargar_api_key()
    client = OpenAI(api_key=api_key)

    resultado = generar_para_perfil(
        client, repertorio, textos_corpus_gold,
        args.nombre, args.caracteristica, args.costumbre, args.objeto, sexo=args.sexo,
        guardar_raw_en=OUTPUT_DIR / "ultima_generacion_raw.json",
    )

    entrada = f"caracteristica={args.caracteristica!r} costumbre={args.costumbre!r} objeto={args.objeto!r}"
    imprimir_resultado_perfil(args.nombre, entrada, resultado)

    u = resultado["usage_total"]
    print(f"\nModelo: {MODEL}  |  Tokens: prompt={u['prompt_tokens']} "
          f"completion={u['completion_tokens']} total={u['total_tokens']}")


if __name__ == "__main__":
    ejecutar_perfil_cli()
