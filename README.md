# 🛒 AI E-Commerce Shopping Assistant & ETL Pipeline

Un motor de búsqueda conversacional de extremo a extremo. Este proyecto extrae, limpia y almacena datos de e-commerce en tiempo real, permitiendo a los usuarios consultar el catálogo mediante lenguaje natural a través de un bot de WhatsApp impulsado por LLMs.

## 🏗️ Arquitectura del Proyecto

El sistema está dividido en dos grandes bloques: un **Pipeline ETL** basado en agentes (Python) y una **Interfaz Conversacional** (Node.js).

### 1. Pipeline ETL (Python)
Diseñado con una arquitectura multi-agente para garantizar la escalabilidad y la calidad del dato:
* **ExtractorAgent:** Realiza peticiones HTTP y bypassea estructuras complejas (ej. extracción de JSON incrustado en `__STATE__` para sitios VTEX).
* **QualityAgent:** Limpia strings, normaliza precios a enteros y descarta registros nulos o sin stock aplicando reglas de negocio estrictas.
* **DBManagerAgent:** Gestiona la conexión a PostgreSQL (Supabase) realizando operaciones de `upsert` idempotentes para evitar duplicados.

### 2. Interfaz Conversacional (Node.js)
* **WhatsApp Bot:** Implementado con `whatsapp-web.js` para interacción directa con el usuario.
* **NLP Engine:** Integración con Google Gemini (2.5 Flash) para traducir el lenguaje natural del usuario ("Busco algo por menos de 80 lucas") en parámetros de búsqueda estructurados (`precio_max`, `tienda`).
* **Querying:** Consultas dinámicas a Supabase filtrando el catálogo en milisegundos.

## 💻 Tecnologías Utilizadas
* **Data Engineering:** Python, BeautifulSoup, Requests, Pandas.
* **Base de Datos:** PostgreSQL (Supabase).
* **Backend:** Node.js.
* **IA:** Google Gemini API.

## 🚀 Próximos Pasos (Roadmap)
- [ ] Implementar extracción universal basada en `sitemap.xml` y `JSON-LD (Schema.org)`.
- [ ] Orquestación en la nube (GitHub Actions) para actualización batch diaria.
- [ ] Agente LLM de clasificación para normalizar colores y categorías automáticamente.