from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import requests
from requests import Response


logger = logging.getLogger(__name__)


class ExtractorError(Exception):
    """Errores específicos del agente extractor."""


@dataclass
class ExtractedData:
    url: str
    raw_html: str
    status_code: int


class ExtractorAgent:
    """
    Agente responsable únicamente de hacer peticiones HTTP y devolver HTML crudo.

    No debe realizar ningún tipo de limpieza ni transformación semántica de los datos.
    """

    def __init__(self, timeout_seconds: int = 15) -> None:
        self._timeout_seconds = timeout_seconds

    def _build_headers(self) -> dict[str, str]:
        # User-Agent simple para parecer un navegador moderno.
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0 Safari/537.36"
            ),
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        }

    def _request(self, url: str) -> Response:
        try:
            logger.info("ExtractorAgent: realizando petición HTTP a %s", url)
            response = requests.get(
                url,
                headers=self._build_headers(),
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            logger.info(
                "ExtractorAgent: respuesta recibida con status_code=%s",
                response.status_code,
            )
            return response
        except requests.RequestException as exc:
            logger.exception("ExtractorAgent: error de red al solicitar %s", url)
            raise ExtractorError(f"Error al solicitar la URL {url}") from exc

    def extract(self, url: str) -> ExtractedData:
        """
        Realiza la petición HTTP y devuelve únicamente HTML crudo.
        """
        response = self._request(url)
        raw_html: str = response.text
        return ExtractedData(
            url=url,
            raw_html=raw_html,
            status_code=response.status_code,
        )

    def safe_extract(self, url: str) -> Optional[ExtractedData]:
        """
        Variante tolerante a fallos que devuelve None si ocurre algún error.
        """
        try:
            return self.extract(url)
        except ExtractorError:
            logger.error("ExtractorAgent: fallo al extraer datos de %s", url)
            return None

