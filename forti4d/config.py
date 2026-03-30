"""
config.py
Configuración central del toolkit de análisis estático Fortran.

Los valores por defecto pueden sobreescribirse con variables de entorno:
  FORT_SRC  — ruta al directorio con el código fuente Fortran a analizar
  FORT_OUT  — directorio donde se escriben todos los reportes y archivos de salida

Ejemplo de uso individual:
  FORT_SRC=/ruta/al/proyecto FORT_OUT=results/ python3 inventario.py

Cuando se usa pipeline.py, estos valores se propagan automáticamente:
  python3 pipeline.py --project /ruta/al/proyecto --output results/
"""

import os
from pathlib import Path

# Directorio con el código fuente Fortran a analizar
CARPETA_CODIGO = Path(os.environ.get("FORT_SRC", "tests/fixtures/"))

# Directorio raíz donde se escriben todos los archivos de salida
RUTA_RESULTADOS = Path(os.environ.get("FORT_OUT", "results/"))
