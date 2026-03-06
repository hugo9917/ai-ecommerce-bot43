from __future__ import annotations

import json
import logging
from typing import Optional

from agents.db_manager import DBManagerAgent
from agents.extractor import ExtractedData, ExtractorAgent
from agents.quality import QualityAgent, QualityOutput


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )


def run_pipeline(test_url: str) -> Optional[dict]:
    logger = logging.getLogger(__name__)

    extractor = ExtractorAgent()
    quality_agent = QualityAgent()
    db_manager = DBManagerAgent()

    logger.info("Iniciando pipeline ETL para la URL: %s", test_url)

    extracted: Optional[ExtractedData] = extractor.safe_extract(test_url)
    if extracted is None:
        logger.error("Pipeline abortado: no se pudo extraer HTML de la URL de prueba.")
        return None

    quality_output: QualityOutput = quality_agent.run(extracted)
    payload: dict = db_manager.run(quality_output)

    logger.info(
        "Pipeline completado. Productos listos para DB: %d",
        payload.get("num_products", 0),
    )

    return payload


def main() -> None:
    """
    Punto de entrada principal.

    Utiliza una URL de prueba de una tienda de ropa para ejecutar el flujo
    completo entre los tres agentes.
    """
    configure_logging()

    urls_to_scrape = [
        "https://www.macowens.com.ar/coleccion/abrigos/camperas.html",
        "https://www.equus.com.ar/categorias/abrigos---camperas",
    ]

    logger = logging.getLogger(__name__)
    for url in urls_to_scrape:
        try:
            payload = run_pipeline(url)
            if payload is not None:
                print(json.dumps(payload, indent=4, ensure_ascii=False))
        except Exception:
            logger.exception("Error procesando la URL %s. Continuando con la siguiente.", url)


if __name__ == "__main__":
    main()

