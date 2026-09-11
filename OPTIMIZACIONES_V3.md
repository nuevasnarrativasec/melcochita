# Melcochómetro v3 — optimizaciones de cercanía al corpus original

## Señales observadas

Sobre 67 chapas originales únicas:

- mediana: **3 palabras**;
- 52/67 tienen **3 palabras o menos**;
- los mecanismos más frecuentes son:
  - YUXTAPOSICION_BREVE: 18;
  - ENCADENAMIENTO_DE: 12;
  - REFERENCIA_CULTURAL_DESPLAZADA: 11;
  - HIBRIDACION_CON: 7;
  - FORMULA_LE_DICEN: 5.

La consecuencia práctica es que no basta con pedir “humor Melcocha”: hay que premiar
**economía verbal + patrón frecuente + imagen visual + conexión física**.

## Implementado

1. Mezcla probabilística de chapas originales y nuevas (30/70 configurable).
2. Selección ponderada de originales por coincidencia de rasgos físicos documentados.
3. Campo hombre/mujer/no indica, usado solo para concordancia y compatibilidad.
4. Priorización de la característica física frente a costumbre/objeto en generación nueva.
5. `score_estilo_original` determinista 0-100.
6. Clasificación de cada candidata nueva en uno de los mecanismos realmente observados.
7. Priorización final por score de estilo, seguida de ADN, sorpresa, conexión y originalidad.
8. No repetición inmediata de la última chapa original mostrada.

## Próximas optimizaciones recomendadas

- **Feedback por origen**: medir 👍/👎 separando original vs. nueva (sin guardar datos personales).
  Esto permitiría ajustar el 30/70 con evidencia.
- **Aprendizaje de preferencias por mecanismo**: contar qué mecanismos obtienen más 👍 y usar esos
  datos como un multiplicador suave del prior, sin entrenar un modelo nuevo.
- **Embeddings de rasgos físicos**: cuando haya suficiente corpus anotado, reemplazar el match por
  palabras por similitud semántica (p.ej. “cabello crespo” ≈ “pelo rizado”).
- **Banco de referentes**: extraer dominios concretos frecuentes (animales, objetos, personajes,
  lugares, comida) y medir combinaciones; ayuda a evitar resultados genéricos.
- **Test A/B de longitud**: 2-3 palabras vs. 4-5. El corpus sugiere que 2-3 debería ganar, pero el
  feedback real debería confirmarlo.
