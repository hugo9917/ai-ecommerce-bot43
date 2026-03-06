from __future__ import annotations

import logging
import os
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

from .quality import Product, QualityOutput

# Cargar .env desde la raíz del proyecto y, por si acaso, desde el directorio actual
_project_root = Path(__file__).resolve().parent.parent
_env_path = _project_root / ".env"
load_dotenv(dotenv_path=str(_env_path))
load_dotenv()  # fallback: directorio de trabajo actual
logger = logging.getLogger(__name__)


class DBManagerError(Exception):
    """Errores específicos del agente estructurador / DB manager."""


def _product_to_row(product: Product) -> Dict[str, Any]:
    """Mapea un Product al esquema de la tabla camperas (columnas en español)."""
    return {
        "nombre": product.name,
        "precio": product.price,
        "moneda": product.currency or "ARS",
        "categoria": product.category,
        "url_producto": product.product_url,
        "tienda": product.tienda,
    }


class DBManagerAgent:
    """
    Agente estructurador.

    Recibe data limpia, prepara el esquema final y realiza upsert en Supabase
    (tabla camperas) vía API REST. Usa url_producto como clave para evitar duplicados.
    """

    # Nota: en tu Supabase la tabla quedó creada como `Camperas` (con mayúscula).
    # PostgREST distingue mayúsculas/minúsculas si la tabla fue creada con comillas.
    TABLE_NAME = "Camperas"
    UPSERT_CONFLICT_COLUMN = "url_producto"

    def __init__(self) -> None:
        self._url = os.environ.get("SUPABASE_URL")
        self._key = os.environ.get("SUPABASE_KEY")
        if not self._url or not self._key:
            logger.warning(
                "DBManagerAgent: SUPABASE_URL o SUPABASE_KEY no definidos. "
                "El upsert a Supabase se omitirá. Definilos en .env o en el entorno."
            )
        else:
            # Normalizar URL (quitar barra final para construir bien el path)
            self._url = self._url.rstrip("/")

    def _supabase_upsert(
        self,
        rows: List[Dict[str, Any]],
        table_name: Optional[str] = None,
    ) -> requests.Response:
        """Envía el upsert a Supabase vía REST (PostgREST). Conflict en url_producto."""
        target_table = table_name or self.TABLE_NAME
        # on_conflict por query param (Supabase/PostgREST) para usar url_producto como clave
        endpoint = (
            f"{self._url}/rest/v1/{target_table}"
            f"?on_conflict={self.UPSERT_CONFLICT_COLUMN}"
        )
        headers = {
            "apikey": self._key,
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        }
        resp = requests.post(endpoint, json=rows, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp

    def prepare_payload(self, quality_output: QualityOutput) -> Dict[str, Any]:
        """
        Convierte la salida del QualityAgent en un JSON listo para inserción y uso interno.
        """
        try:
            products_as_dicts = [asdict(p) for p in quality_output.products]
            payload: Dict[str, Any] = {
                "source_url": quality_output.source_url,
                "num_products": len(products_as_dicts),
                "products": products_as_dicts,
            }
            logger.info(
                "DBManagerAgent: payload preparado con %d productos para %s",
                payload["num_products"],
                quality_output.source_url,
            )
            return payload
        except Exception as exc:
            logger.exception("DBManagerAgent: error al preparar el payload final")
            raise DBManagerError("Error al estructurar datos para la base de datos") from exc

    def run(self, quality_output: QualityOutput) -> Dict[str, Any]:
        """
        Prepara el payload y realiza upsert en la tabla camperas de Supabase.
        Usa url_producto como clave para evitar duplicados. Devuelve el payload en todo caso.
        """
        payload = self.prepare_payload(quality_output)

        if not self._url or not self._key:
            logger.warning("DBManagerAgent: cliente Supabase no inicializado, se omite el upsert.")
            return payload

        rows: List[Dict[str, Any]] = [
            _product_to_row(product) for product in quality_output.products
        ]
        if not rows:
            logger.info("DBManagerAgent: no hay filas para insertar en Supabase.")
            return payload

        try:
            self._supabase_upsert(rows)
            logger.info(
                "DBManagerAgent: upsert en Supabase correcto. %d filas en tabla '%s'.",
                len(rows),
                self.TABLE_NAME,
            )
        except requests.RequestException as exc:
            status_code: Optional[int] = None
            response_body: Optional[str] = None
            if hasattr(exc, "response") and exc.response is not None:
                status_code = exc.response.status_code
                try:
                    response_body = exc.response.text
                except Exception:
                    response_body = None

            # Si ya existe por unique constraint, lo tratamos como no fatal.
            if status_code == 409:
                logger.warning(
                    "DBManagerAgent: conflicto 409 (posibles duplicados por unique). "
                    "Se ignora para mantener idempotencia. Respuesta=%s",
                    response_body,
                )
                return payload

            logger.error(
                "DBManagerAgent: upsert falló en Supabase (tabla='%s', status=%s). Respuesta=%s",
                self.TABLE_NAME,
                status_code,
                response_body,
            )

            # Si PostgREST sugiere el nombre exacto (por ejemplo `public.Camperas`),
            # reintentamos una vez con ese identificador.
            if status_code == 404 and response_body:
                m = re.search(r"table 'public\.([A-Za-z0-9_]+)'", response_body)
                suggested_table = m.group(1) if m else None
                if suggested_table and suggested_table != self.TABLE_NAME:
                    try:
                        logger.info(
                            "DBManagerAgent: reintentando upsert con tabla sugerida por Supabase: '%s'",
                            suggested_table,
                        )
                        self._supabase_upsert(rows, table_name=suggested_table)
                        logger.info(
                            "DBManagerAgent: upsert en Supabase correcto. %d filas en tabla '%s'.",
                            len(rows),
                            suggested_table,
                        )
                        return payload
                    except requests.RequestException as exc2:
                        logger.error(
                            "DBManagerAgent: retry falló (tabla='%s'). Error=%s",
                            suggested_table,
                            exc2,
                        )

            # No cortamos el pipeline: devolvemos payload para que puedas seguir viendo la data.
            return payload

        return payload
