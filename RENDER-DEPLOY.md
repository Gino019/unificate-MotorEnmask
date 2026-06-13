# Desplegar en Render (sin Docker en tu PC)

Render construye y ejecuta el proyecto **en sus servidores**. Solo necesitas una cuenta de GitHub y una de Render.

## Que se despliega

| Servicio en Render | Funcion |
|---|---|
| `secops-api` | Panel web, login, API principal |
| `secops-masking` | Enmascaramiento de datos |
| `secops-monitor` | Metricas de rendimiento |

**Importante:** las 7 bases de datos de prueba (Postgres, MySQL, etc.) **no** van incluidas en Render. El login, registro, enmascaramiento y metricas si funcionan. Para probar BDs externas, conecta servicios gratuitos como [Neon](https://neon.tech) (Postgres) o [MongoDB Atlas](https://www.mongodb.com/atlas).

---

## Paso 1 — Subir el proyecto a GitHub

Si aun no tienes el repo en GitHub:

1. Crea una cuenta en [github.com](https://github.com)
2. Crea un repositorio nuevo (ej: `secops-monitor`)
3. En PowerShell, dentro de la carpeta del proyecto:

```powershell
cd "c:\Users\W10\Desktop\Multi-DB Masking & Performance Overhead Monitor"
git init
git add .
git commit -m "Preparar deploy en Render"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/secops-monitor.git
git push -u origin main
```

> No subas el archivo `.env` (contiene secretos). Ya esta en `.gitignore`.

---

## Paso 2 — Crear cuenta en Render

1. Entra a [render.com](https://render.com)
2. Registrate con tu cuenta de **GitHub**
3. Autoriza a Render para ver tus repositorios

---

## Paso 3 — Desplegar con Blueprint

1. En Render, clic en **New +** → **Blueprint**
2. Conecta el repositorio de GitHub donde subiste el proyecto
3. Render detectara el archivo `render.yaml` automaticamente
4. Revisa los 3 servicios que va a crear
5. Clic en **Apply**

Render empezara a construir las 3 imagenes (tarda **5–15 minutos** la primera vez).

---

## Paso 4 — Abrir la aplicacion

1. Cuando los 3 servicios muestren estado **Live** (verde)
2. Abre la URL de **`secops-api`**, algo como:
   `https://secops-api-xxxx.onrender.com`
3. Ve a `/login`:
   `https://secops-api-xxxx.onrender.com/login`

**Credenciales por defecto:**
- Email: `admin@secops.local`
- Contrasena: `Admin1234!`

---

## Limitaciones del plan gratuito

| Tema | Que esperar |
|---|---|
| **Arranque lento** | Tras 15 min sin uso, el servicio "duerme". La primera visita tarda ~30–60 s |
| **Datos de usuarios** | Se guardan en SQLite dentro del contenedor; pueden perderse al redeploy |
| **3 servicios** | Cada uno cuenta para el limite de horas gratis de Render |
| **BDs de prueba** | No incluidas; usa SQLite desde el panel o BDs cloud externas |

---

## Cambiar la contrasena del admin

1. En Render → servicio **secops-api** → **Environment**
2. Edita `ADMIN_PASSWORD` con una contrasena fuerte
3. Guarda → Render redeploya automaticamente

---

## Comandos utiles en Render

- **Logs:** servicio → pestana *Logs* (para ver errores)
- **Redeploy:** servicio → *Manual Deploy* → *Deploy latest commit*
- **Variables:** servicio → *Environment*

---

## Si algo falla

1. Revisa que los 3 servicios esten en **Live**
2. En **secops-api** → Logs, busca errores de conexion con masking/monitor
3. Verifica que `MASKING_SERVICE_URL` y `MONITOR_SERVICE_URL` aparezcan en Environment (Render las genera solo)

---

## Actualizar la app

Cada `git push` a `main` puede redeployar automaticamente si activas **Auto-Deploy** en cada servicio.

```powershell
git add .
git commit -m "Mi cambio"
git push
```
