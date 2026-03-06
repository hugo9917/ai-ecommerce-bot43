# Bot WPP - Pipeline ETL de E-commerce

Este proyecto implementa un pipeline ETL en Python organizado como un sistema multi-agente para extraer productos de e-commerce, limpiar los datos y estructurarlos para su posterior inserción en una base de datos (por ejemplo PostgreSQL o Supabase).

## Estructura de agentes

- `agents/extractor.py`: agente extractor. Solo realiza peticiones HTTP y devuelve HTML o JSON crudo.
- `agents/quality.py`: agente de data quality. Limpia y normaliza datos a partir de la data cruda.
- `agents/db_manager.py`: agente estructurador. Prepara el payload final (JSON) listo para ser insertado en la base de datos.

El archivo `main.py` orquesta el flujo llamando a los agentes en orden.

## Requisitos

```bash
pip install -r requirements.txt
```

## Ejecución

```bash
python main.py
```

