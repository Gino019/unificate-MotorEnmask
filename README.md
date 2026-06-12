# Multi-DB Masking & Performance Overhead Monitor

Este archivo sirve como el **Contexto Maestro** para la IA del IDE. Por favor, lee y respeta estas directrices, arquitectura y objetivos en cada respuesta y generación de código.

---

## 🎯 Objetivo del Proyecto
El sistema es una plataforma de **SecOps / DBA Tools** que fusiona un **motor de enmascaramiento dinámico de datos** con un **monitor de rendimiento e infraestructura**. 

La propuesta de valor principal no es solo ocultar datos, sino **medir y graficar cuantitativamente el "impuesto de rendimiento" (overhead)** que la seguridad introduce al realizar consultas en tiempo real sobre diferentes motores de bases de datos.



- **Seguridad y Acceso:** El sistema está protegido por un Login de autenticación.
- **Catálogo de Algoritmos de Enmascaramiento:** El sistema compara el rendimiento de: 1) Redacción Simple (X), 2) Hashing (SHA-256), 3) Encriptación Simétrica (AES/Fernet) y 4) Cifrado FPE.
---

## 🛠️ Stack Tecnológico
- **Backend:** Python 3.11+ con **FastAPI** (asíncrono, de alto rendimiento).
- **Frontend:** HTML5, **Tailwind CSS** (vía CDN) y **Chart.js** (para las gráficas en tiempo real).
- **Motores de Bases de Datos Soportados (7 en total):**
  - **Relacionales (SQL):** PostgreSQL (`psycopg2-binary`), MySQL (`pymysql`), SQL Server (`pymssql`), SQLite (`sqlite3`).
  - **No Relacionales (NoSQL):** MongoDB (`pymongo` - Documentos), Redis (`redis` - Clave/Valor en memoria), Neo4j (`neo4j` - Grafos).
---

## 🚀 Métricas Clave (El "Norte" del Proyecto)
Cualquier funcionalidad o vista que desarrollemos debe apuntar a alimentar estas tres métricas:

1. **Delta de Latencia (ms):** Tiempo exacto de la Consulta Cruda (BD) vs. Tiempo con la capa de Enmascaramiento aplicada.
2. **Consumo de CPU por Seguridad:** Identificar qué porcentaje del procesamiento se debe a la ejecución de algoritmos de enmascaramiento en el backend versus la consulta en la BD.
3. **Eficiencia de Algoritmos (Matriz de Impacto):** Comparativa de rendimiento entre técnicas simples (ej. cambiar letras por 'X') y complejas (ej. Cifrado que Preserva el Formato - FPE) a través de los 4 motores de BD.

---

## 📐 Principios de Arquitectura para la IA
Cuando escribas código para este proyecto, sigue estas reglas estrictas:
- **Patrón Factory / Estrategia:** El acceso a las bases de datos debe estar centralizado en un `database_manager.py` que abstraiga la conexión a los 4 motores, devolviendo siempre un formato estandarizado (lista de diccionarios).
- **Medición Precisa:** Utiliza `time.perf_counter_ns()` para capturar los deltas de tiempo antes y después de cada proceso (Query vs Enmascaramiento).
- **Modularidad:** Mantén la lógica de conexión a BD, los algoritmos de enmascaramiento y los endpoints de FastAPI en módulos separados y limpios.
- **Idioma:** El código, variables y comentarios deben seguir buenas prácticas de la industria, pero los logs expuestos, la documentación y la interfaz de usuario deben estar en **Español**.

---
*Última actualización de contexto: Junio 2026*