from __future__ import annotations

import logging
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .extractor import ExtractedData


logger = logging.getLogger(__name__)

# Selectores para el listado de productos (Mac Owens). Ajustar si la página cambia.
MACOWENS_CONTAINER_CSS_CLASS = "product-item"
MACOWENS_TITLE_CSS_CLASS = "product-item-link"
MACOWENS_PRICE_CSS_CLASS = "price"

# Equus (VTEX): el contenido viene embebido en JSON __STATE__ dentro del HTML.
EQUUS_BASE_URL = "https://www.equus.com.ar"
MAX_PRICE_INCLUSIVE = 100_000


class QualityError(Exception):
    """Errores específicos del agente de data quality."""


@dataclass
class Product:
    name: str
    price: Optional[int]
    currency: Optional[str]
    category: Optional[str]
    product_url: Optional[str]
    tienda: str


@dataclass
class QualityOutput:
    source_url: str
    products: List[Product]


class QualityAgent:
    """
    Agente de data quality.

    Recibe data sucia (por ejemplo HTML crudo) y se encarga de:
    - Parsear y estructurar productos (a implementar según cada sitio).
    - Limpiar strings.
    - Formatear precios a enteros.
    - Manejar nulos.
    - Normalizar categorías.
    """

    CATEGORY_NORMALIZATION_MAP: Dict[str, str] = {
        "anorak": "Campera",
        "campera": "Campera",
        "jacket": "Campera",
        "chaqueta": "Campera",
    }

    def run(self, extracted: ExtractedData) -> QualityOutput:
        """
        Parsea el HTML con BeautifulSoup, extrae productos, limpia precios
        y aplica reglas de negocio (ej. descartar precio > 100000).
        """
        try:
            html_content = extracted.raw_html
            if not html_content:
                logger.warning(
                    "QualityAgent: HTML vacío recibido desde la URL %s",
                    extracted.url,
                )
                return QualityOutput(source_url=extracted.url, products=[])

            raw_products = self._route_and_parse(html_content, extracted.url)
            cleaned_products: List[Product] = []

            for raw_product in raw_products:
                price_raw = raw_product.get("price")
                price_int = self._parse_price_to_int(price_raw)
                if price_int is not None and price_int > MAX_PRICE_INCLUSIVE:
                    logger.debug(
                        "QualityAgent: producto descartado por precio > %s: %s",
                        MAX_PRICE_INCLUSIVE,
                        raw_product.get("name"),
                    )
                    continue

                raw_product["price"] = price_int
                cleaned = self._clean_product(raw_product, extracted.url)

                # Filtrado final: solo productos con nombre no vacío y precio no nulo.
                if not cleaned.name or not cleaned.name.strip():
                    logger.debug(
                        "QualityAgent: producto descartado por nombre vacío. URL=%s",
                        cleaned.product_url,
                    )
                    continue
                if cleaned.price is None:
                    logger.debug(
                        "QualityAgent: producto descartado por precio nulo. Nombre=%s",
                        cleaned.name,
                    )
                    continue

                cleaned_products.append(cleaned)

            logger.info(
                "QualityAgent: %d productos limpios generados desde %s",
                len(cleaned_products),
                extracted.url,
            )

            return QualityOutput(source_url=extracted.url, products=cleaned_products)
        except Exception as exc:
            logger.exception("QualityAgent: error al procesar datos desde %s", extracted.url)
            raise QualityError("Error en el agente de data quality") from exc

    def _route_and_parse(self, html_content: str, base_url: str) -> List[Dict[str, Any]]:
        url_lower = (base_url or "").lower()
        if "macowens" in url_lower:
            return self._parse_macowens(html_content, base_url)
        if "equus" in url_lower:
            return self._parse_equus(html_content, base_url)

        logger.warning("QualityAgent: no hay parser para la URL %s", base_url)
        return []

    def _parse_macowens(self, html_content: str, base_url: str) -> List[Dict[str, Any]]:
        """
        Parser específico para Mac Owens (Magento).
        """
        soup = BeautifulSoup(html_content, "html.parser")
        containers = soup.select(f".{MACOWENS_CONTAINER_CSS_CLASS}")
        raw_products: List[Dict[str, Any]] = []

        for container in containers:
            title_el = container.select_one(f".{MACOWENS_TITLE_CSS_CLASS}")
            price_el = container.select_one(f".{MACOWENS_PRICE_CSS_CLASS}")
            link_el = container.select_one("a[href]")

            title = title_el.get_text(strip=True) if title_el else ""
            price_raw = price_el.get_text(strip=True) if price_el else ""
            href = ""
            if link_el and link_el.get("href"):
                href = urljoin(base_url, link_el["href"])

            raw_products.append({
                "name": title,
                "price": price_raw,
                "currency": "ARS",
                "category": "Campera",
                "url": href or base_url,
                "tienda": "Macowens",
            })

        return raw_products

    def _parse_equus(self, html_content: str, base_url: str) -> List[Dict[str, Any]]:
        """
        Parser específico para Equus (VTEX).

        En VTEX (store framework), el HTML inicial puede no traer tarjetas de producto.
        La lista de productos viene en un bloque JSON `__STATE__` dentro del HTML.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        state_script = soup.select_one('template[data-varname="__STATE__"] script')
        if not state_script:
            logger.warning("QualityAgent: no se encontró __STATE__ en Equus (%s)", base_url)
            return []

        try:
            state = json.loads(state_script.get_text())
        except json.JSONDecodeError:
            logger.exception("QualityAgent: __STATE__ inválido en Equus (%s)", base_url)
            return []

        # Encontrar el objeto productSearch que corresponde a esta URL (query).
        url_key = "categorias/abrigos---camperas"
        candidates: List[tuple[str, int]] = []
        for k, v in state.items():
            if not isinstance(v, dict):
                continue
            products = v.get("products")
            if isinstance(products, list) and products:
                # Preferimos el query de esta página si está presente
                score = len(products)
                if url_key in k:
                    score += 10_000
                candidates.append((k, score))

        if not candidates:
            logger.warning("QualityAgent: no se encontró productSearch con productos en Equus (%s)", base_url)
            return []

        candidates.sort(key=lambda x: x[1], reverse=True)
        best_key = candidates[0][0]
        best_obj = state.get(best_key, {})
        products_refs = best_obj.get("products") if isinstance(best_obj, dict) else None
        if not isinstance(products_refs, list):
            return []

        raw_products: List[Dict[str, Any]] = []
        for ref in products_refs:
            if not isinstance(ref, dict):
                continue
            product_id = ref.get("id")
            if not product_id or product_id not in state:
                continue
            prod = state.get(product_id)
            if not isinstance(prod, dict):
                continue

            name = str(prod.get("productName") or "").strip()
            link = str(prod.get("link") or "").strip()
            product_url = urljoin(EQUUS_BASE_URL, link) if link else base_url

            # Resolver precio via priceRange -> sellingPrice -> lowPrice
            price_int: Optional[int] = None
            pr = prod.get("priceRange")
            if isinstance(pr, dict) and pr.get("id") and pr.get("id") in state:
                pr_obj = state.get(pr["id"])
                if isinstance(pr_obj, dict):
                    sp = pr_obj.get("sellingPrice")
                    if isinstance(sp, dict) and sp.get("id") in state:
                        sp_obj = state.get(sp["id"])
                        if isinstance(sp_obj, dict):
                            low_price = sp_obj.get("lowPrice")
                            price_int = self._parse_price_to_int(low_price)

            raw_products.append(
                {
                    "name": name,
                    "price": price_int,
                    "currency": "ARS",
                    "category": "Campera",
                    "url": product_url,
                    "tienda": "Equus",
                }
            )

        return raw_products

    def _clean_product(self, raw: Dict[str, Any], fallback_url: str) -> Product:
        """
        Aplica reglas de limpieza sobre un producto crudo.
        """
        raw_name = str(raw.get("name") or "").strip()
        raw_price = raw.get("price")
        raw_currency = str(raw.get("currency") or "").strip()
        raw_category = str(raw.get("category") or "").strip()
        raw_url = str(raw.get("url") or "").strip() or fallback_url
        raw_tienda = str(raw.get("tienda") or "").strip() or "Desconocida"

        name = self._clean_name(raw_name)
        price_int = self._parse_price_to_int(raw_price)
        currency = raw_currency or "ARS"
        category = self._normalize_category(raw_category)
        product_url = raw_url

        return Product(
            name=name,
            price=price_int,
            currency=currency,
            category=category,
            product_url=product_url,
            tienda=raw_tienda,
        )

    def _clean_name(self, value: str) -> str:
        value = value.strip()
        # Colapsar espacios múltiples
        value = re.sub(r"\s+", " ", value)
        return value

    def _parse_price_to_int(self, value: Any) -> Optional[int]:
        """
        Convierte diferentes representaciones de precio a un entero (por ejemplo en centavos).
        """
        if value is None:
            return None

        if isinstance(value, (int, float)):
            return int(value)

        text = str(value)
        # Quitar símbolos de moneda y espacios
        text = text.replace("$", "").replace("€", "").replace("£", "")
        text = text.replace("ARS", "").replace("USD", "").replace("EUR", "")
        text = text.strip()

        # Si después de limpiar el string queda vacío, no es un error, sólo lo ignoramos.
        if not text:
            logger.debug("QualityAgent: Precio vacío encontrado, ignorando producto")
            return None

        # Reemplazar separadores de miles y manejar comas/puntos
        text = text.replace(".", "").replace(" ", "")
        text = text.replace(",", ".")

        try:
            numeric = float(text)
            return int(round(numeric))
        except ValueError:
            logger.warning("QualityAgent: no se pudo parsear el precio '%s'", value)
            return None

    def _normalize_category(self, value: str) -> Optional[str]:
        if not value:
            return None

        key = value.strip().lower()
        normalized = self.CATEGORY_NORMALIZATION_MAP.get(key)
        if normalized:
            return normalized

        # Si no está en el mapa, devolvemos capitalizado.
        return value.strip().title()

