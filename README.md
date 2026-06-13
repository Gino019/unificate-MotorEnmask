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

## Despliegue en Render (sin Docker en tu PC)

Si no puedes instalar Docker Desktop, usa **Render**. Construye el proyecto en la nube desde GitHub.

Guia completa: **[RENDER-DEPLOY.md](./RENDER-DEPLOY.md)**

Resumen:
1. Sube el proyecto a GitHub
2. Crea cuenta en [render.com](https://render.com)
3. **New → Blueprint** → conecta el repo
4. Abre la URL de `secops-api`

---

### Requisitos
- Docker Desktop (Windows/macOS) o Docker Engine + Compose Plugin (Linux)
- Al menos **8 GB RAM** libres (SQL Server y Neo4j consumen memoria)

### Pasos

```bash
# 1. Clonar el repositorio y entrar al directorio del proyecto
cd "Multi-DB Masking & Performance Overhead Monitor"

# 2. Crear el archivo de entorno a partir de la plantilla
cp .env.example .env          # Linux/macOS
copy .env.example .env          # Windows CMD
Copy-Item .env.example .env     # Windows PowerShell

# 3. Editar .env — cambiar SECRET_KEY, ADMIN_PASSWORD y contraseñas de BD
#    Generar SECRET_KEY: python -c "import secrets; print(secrets.token_hex(32))"

# 4. Levantar todo el stack
docker compose up -d --build

# 5. Verificar que los servicios estén sanos
docker compose ps
```

### Acceso

| Servicio | URL |
|---|---|
| **Panel web (login local)** | http://localhost:8000/login |
| API Gateway | http://localhost:8000 |
| Masking Service | http://localhost:8001 |
| Monitor Service | http://localhost:8002 |
| Neo4j Browser | http://localhost:7474 |

**Credenciales por defecto** (configurables en `.env`):
- Email: `admin@secops.local`
- Contraseña: `Admin1234!`

### Autenticación
El acceso es **solo con email + contraseña** (bcrypt). Los usuarios pueden registrarse desde `/login`.

### Datos persistentes
Los volúmenes Docker guardan:
- `secops_data` → usuarios de plataforma + clave Fernet SDM
- `monitor_data` → métricas de rendimiento
- `pg_data`, `mysql_data`, `mssql_data`, `mongo_data`, `redis_data`, `neo4j_data` → bases de datos de prueba

### Comandos útiles

```bash
docker compose logs -f api          # Ver logs del gateway
docker compose down                 # Detener servicios
docker compose down -v              # Detener y borrar volúmenes (¡pierde datos!)
```

---
*Última actualización de contexto: Junio 2026*