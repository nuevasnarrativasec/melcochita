# Curaduría del corpus — v3

El archivo `data/corpus/chapas_originales_curadas.csv` conserva las **67 chapas únicas** del
material original, junto con las etiquetas editoriales creadas en la versión anterior.

En v3 esas etiquetas ya no significan que edad, apariencia, humor negro o tono áspero se
eliminen automáticamente. Se conservan como metadata de análisis.

## Qué se preserva

- Todas las chapas permanecen en el corpus histórico.
- El motor puede aprender estructura, ritmo y mecanismos de las originales publicables.
- El generador puede devolver directamente una original como parte de la mezcla aleatoria.

## Límite de salida

Las entradas cuya comicidad depende directamente de un atributo protegido (por ejemplo,
orientación sexual o nacionalidad/origen) o de misoginia explícita se conservan en el archivo,
pero no forman parte del pool que se sortea ni del material usado para crear nuevas burlas.

El campo `sexo` del formulario se usa únicamente para concordancia y compatibilidad del referente.
