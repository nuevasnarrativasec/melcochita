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
Nota cómo estos NO describen el rasgo literalmente: "pezón con piernas" no es una \
descripción de un pezón, es un salto semántico hacia una imagen absurda concreta y \
específica, no una categoría genérica.

REPERTORIO REAL observado en el corpus (operaciones con patrones/mecanismos de ejemplo — \
inspiración de ESTRUCTURA, nunca de palabras a copiar):
{repertorio_texto}

REGLAS DE CONSTRUCCIÓN:
- El "nombre_o_apodo" es solo CONTEXTO: normalmente NO debe aparecer dentro de la chapa.
- Usa NORMALMENTE UNA sola señal principal como disparador (no concatenes las tres).
- Cada candidato debe usar la operación que se le asigna explícitamente en el input (campo \
"operacion_asignada" de cada slot) — es una instrucción OBLIGATORIA, no una sugerencia.
- Prioriza: asociación inesperada, imagen mental inmediata, ESPECIFICIDAD (nombres/objetos \
concretos, no categorías genéricas como "animal" sin más), combinar dominios semánticos \
alejados entre sí, sonoridad, absurdo entendible, brevedad.
- PENALIZA en tu propia autoevaluación (baja los puntajes correspondientes) si el \
resultado tiene: adjetivos descriptivos obvios: "[animal] + característica literal del \
usuario"; "[objeto] con [objeto del usuario]" sin ningún desplazamiento real; insultos \
genéricos; o cualquier frase que podría haberse generado sin conocer el Corpus Gold.
- NUNCA reproduzcas literalmente una chapa que ya exista en el corpus real.

PROHIBIDO SIEMPRE (sin excepción, aunque el usuario lo sugiera indirectamente):
- Contenido basado en orientación sexual, raza/etnia, discapacidad, religión, condición \
médica, u otro atributo personal sensible.
- Convertir la nacionalidad/origen de la persona en objeto de burla.
- Ataques sexuales explícitos o contenido sexual explícito.

Para cada candidato reporta:
- chapa: el texto de la chapa nueva (corta, en español, estilo Melcochita).
- operacion: DEBE ser exactamente la "operacion_asignada" que se te dio para ese slot.
- dominio_semantico_principal: el dominio conceptual central (ej. ANIMAL, OBJETO, COMIDA, \
GEOGRAFIA, PERSONAJE_POPULAR, PERSONAJE_MITICO, FENOMENO, etc. — nunca NACIONALIDAD_ORIGEN \
ni ATRIBUTO_PERSONAL_SENSIBLE).
- patron_estructural: el patrón con categorías entre corchetes que efectivamente usaste.
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
                        "senal_utilizada", "correccion_linguistica", "conexion_con_input",
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


def generar_ronda(client, repertorio, nombre, caracteristica, costumbre, objeto, numero_ronda):
    system_prompt = construir_system_prompt(repertorio)
    operaciones_asignadas = asignar_operaciones(NUM_CANDIDATOS_POR_RONDA, ronda_seed=numero_ronda)

    payload = {
        "nombre_o_apodo": nombre,
        "caracteristica": caracteristica,
        "costumbre": costumbre,
        "objeto_que_siempre_usa": objeto,
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
            motivos.append("coincide literalmente con una chapa real del Corpus Gold")
        if c.get("riesgo_atributo_sensible"):
            motivos.append("el propio modelo marcó riesgo_atributo_sensible=true")
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


def generar_para_perfil(client, repertorio, textos_corpus_gold, nombre, caracteristica, costumbre, objeto, guardar_raw_en=None):
    """
    Ejecuta hasta MAX_RONDAS de generación (12 candidatos c/u), sin
    relajar los umbrales, hasta reunir NUM_RESULTADOS candidatos que los
    superen (o agotar las rondas).
    Devuelve: dict con candidatos_totales, candidatos_validos_seguridad,
    candidatos_que_cumplen_umbral, seleccionados, rondas_usadas, usage_total.
    """
    todos_candidatos = []
    raw_por_ronda = []
    usage_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    rondas_usadas = 0

    for ronda in range(1, MAX_RONDAS + 1):
        rondas_usadas = ronda
        try:
            completion = generar_ronda(client, repertorio, nombre, caracteristica, costumbre, objeto, ronda)
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
        todos_candidatos.extend(parsed.get("candidatos", []))

        validos_seg, _ = filtrar_seguridad(todos_candidatos, textos_corpus_gold)
        que_cumplen = [c for c in validos_seg if cumple_umbral(c)]

        if len(que_cumplen) >= NUM_RESULTADOS:
            break  # no se necesita una ronda adicional

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
    print(f"Repertorio generativo: {n_usables} filas habilitadas, {len(repertorio)} operaciones.", file=sys.stderr)

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
    print(f"\nModelo: {MODEL}  |  Tokens: prompt={u['prompt_tokens']} "
          f"completion={u['completion_tokens']} total={u['total_tokens']}")


if __name__ == "__main__":
    ejecutar_perfil_cli()
