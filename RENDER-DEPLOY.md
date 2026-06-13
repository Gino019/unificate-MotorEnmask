# Guia completa — Desplegar SecOps Universal en Render

Esta guia te lleva de **cero a produccion** sin instalar Docker en tu PC.
Render construye y ejecuta el proyecto en sus servidores a partir de tu repositorio en GitHub.

---

## Tabla de contenidos

1. [Que vas a desplegar](#1-que-vas-a-desplegar)
2. [Requisitos previos](#2-requisitos-previos)
3. [Que funciona y que no](#3-que-funciona-y-que-no)
4. [Paso 1 — Verificar el proyecto en GitHub](#4-paso-1--verificar-el-proyecto-en-github)
5. [Paso 2 — Crear cuenta en Render](#5-paso-2--crear-cuenta-en-render)
6. [Paso 3 — Desplegar con Blueprint](#6-paso-3--desplegar-con-blueprint)
7. [Paso 4 — Esperar el build](#7-paso-4--esperar-el-build)
8. [Paso 5 — Abrir y probar la aplicacion](#8-paso-5--abrir-y-probar-la-aplicacion)
9. [Variables de entorno](#9-variables-de-entorno)
10. [Conectar una base de datos externa (opcional)](#10-conectar-una-base-de-datos-externa-opcional)
11. [Actualizar la app despues del primer deploy](#11-actualizar-la-app-despues-del-primer-deploy)
12. [Limitaciones del plan gratuito](#12-limitaciones-del-plan-gratuito)
13. [Solucion de problemas](#13-solucion-de-problemas)
14. [Preguntas frecuentes](#14-preguntas-frecuentes)

---

## 1. Que vas a desplegar

Render creara **3 servicios web** a partir del archivo `render.yaml`:

```
                    ┌─────────────────────────────────────┐
  Tu navegador ───► │  secops-api                         │
                    │  Panel + Login + API principal      │
                    │  https://secops-api-xxx.onrender.com│
                    └──────────┬──────────────┬───────────┘
                               │              │
                    ┌──────────▼──┐  ┌────────▼──────────┐
                    │ secops-     │  │ secops-monitor    │
                    │ masking     │  │ Metricas          │
                    │ Enmascara-  │  │ de rendimiento    │
                    │ miento      │  │                   │
                    └─────────────┘  └───────────────────┘
```

| Servicio Render   | Archivo Python        | URL publica              |
|-------------------|-----------------------|--------------------------|
| `secops-api`      | `main.py`             | **Esta es la que abres** |
| `secops-masking`  | `masking_service.py`  | Solo uso interno         |
| `secops-monitor`  | `monitor_service.py`  | Solo uso interno         |

Render conecta automaticamente la API con Masking y Monitor mediante las variables `MASKING_SERVICE_URL` y `MONITOR_SERVICE_URL`.

---

## 2. Requisitos previos

Antes de empezar necesitas:

| Requisito | Donde conseguirlo |
|-----------|-------------------|
| Cuenta de **GitHub** | [github.com](https://github.com) |
| Cuenta de **Render** | [render.com](https://render.com) |
| Proyecto subido a GitHub | Ver paso 1 |
| Navegador web | Chrome, Edge, Firefox, etc. |

**No necesitas:**
- Docker Desktop
- Servidor propio (VPS)
- Tarjeta de credito (plan gratuito)

---

## 3. Que funciona y que no

### Funciona en Render

- Login y registro de usuarios (email + contrasena)
- Panel web completo (`/login` y `/`)
- Enmascaramiento dinamico de datos
- Metricas de overhead (tiempo BD vs masking)
- Gobernanza SDM (proteger / restaurar tablas)
- Conexion a bases de datos **externas** que tu configures

### No incluido en Render (respecto a Docker local)

Las 7 bases de datos de prueba del `docker-compose.yml` **no se despliegan** en Render:

- PostgreSQL, MySQL, SQL Server, MongoDB, Redis, Neo4j

Para probar motores concretos puedes:
- Usar **SQLite** desde el panel (archivo local en tu PC)
- Crear BDs gratuitas en la nube (Neon, Atlas, etc.) — ver seccion 10

---

## 4. Paso 1 — Verificar el proyecto en GitHub

Tu repositorio debe contener estos archivos clave:

```
Multi-DB Masking & Performance Overhead Monitor/
├── render.yaml          ← Blueprint de Render (obligatorio)
├── Dockerfile           ← Render construye con esto
├── requirements.txt
├── main.py
├── masking_service.py
├── monitor_service.py
├── static/
│   ├── login.html
│   └── index.html
└── ...
```

### Si ya tienes el repo en GitHub

Tu repo actual: `https://github.com/Gino019/unificate-MotorEnmask`

Verifica que `render.yaml` este en la rama `main`. Si hiciste cambios locales:

```powershell
cd "c:\Users\W10\Desktop\Multi-DB Masking & Performance Overhead Monitor"
git status
git add .
git commit -m "Actualizar config Render"
git push origin main
```

### Si aun NO tienes repo en GitHub

1. Entra a [github.com/new](https://github.com/new)
2. Nombre sugerido: `secops-monitor`
3. Dejalo **Public** o **Private** (Render funciona con ambos)
4. **No** marques "Add README" si ya tienes codigo local
5. En PowerShell:

```powershell
cd "c:\Users\W10\Desktop\Multi-DB Masking & Performance Overhead Monitor"
git init
git add .
git commit -m "Primer commit - SecOps Universal"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/TU-REPO.git
git push -u origin main
```

> **Importante:** el archivo `.env` NO se sube a GitHub (esta en `.gitignore`). Los secretos los configura Render automaticamente o desde su panel.

---

## 5. Paso 2 — Crear cuenta en Render

1. Abre [render.com](https://render.com)
2. Clic en **Get Started for Free**
3. Elige **Sign in with GitHub**
4. Autoriza a Render para acceder a tus repositorios
5. Completa el registro si te lo pide

---

## 6. Paso 3 — Desplegar con Blueprint

Un **Blueprint** lee el archivo `render.yaml` y crea todos los servicios de una vez.

### 6.1 Crear el Blueprint

1. En el dashboard de Render, clic en **New +** (arriba a la derecha)
2. Selecciona **Blueprint**
3. En "Connect a repository", busca tu repo:
   - `Gino019/unificate-MotorEnmask` (o el nombre que hayas usado)
4. Si no aparece, clic en **Configure account** y da acceso al repo

### 6.2 Revisar servicios detectados

Render mostrara algo como:

```
Blueprint detected: render.yaml

Services to create:
  - secops-monitor   (Web Service, Docker, Free)
  - secops-masking   (Web Service, Docker, Free)
  - secops-api       (Web Service, Docker, Free)
```

Revisa que sean **3 servicios**. No cambies nada salvo que sepas lo que haces.

### 6.3 Aplicar

1. Clic en **Apply**
2. Render creara los 3 servicios y empezara el build

---

## 7. Paso 4 — Esperar el build

La primera vez tarda **entre 5 y 15 minutos** (Render descarga dependencias, compila drivers de BD, etc.).

### Como seguir el progreso

1. En el dashboard veras los 3 servicios
2. Clic en cada uno → pestana **Logs**
3. Estados posibles:

| Estado      | Significado                          |
|-------------|--------------------------------------|
| `Building`  | Construyendo la imagen Docker        |
| `Deploying` | Arrancando el contenedor             |
| `Live`      | **Listo** — funciona                 |
| `Failed`    | Error — revisa Logs (seccion 13)     |

### Orden recomendado

Es normal que `secops-monitor` y `secops-masking` queden **Live** antes que `secops-api`.
La API depende de las URLs de los otros dos servicios.

---

## 8. Paso 5 — Abrir y probar la aplicacion

### 8.1 Obtener la URL

1. Clic en el servicio **`secops-api`**
2. Arriba veras la URL, por ejemplo:
   ```
   https://secops-api-xxxx.onrender.com
   ```
3. Copiala

### 8.2 Primera visita (plan gratuito)

Si el servicio estuvo inactivo, la **primera carga puede tardar 30–60 segundos**.
Veras una pantalla de "Loading" de Render. Espera sin recargar.

### 8.3 Login

Abre en el navegador:

```
https://secops-api-xxxx.onrender.com/login
```

**Credenciales por defecto:**

| Campo      | Valor                 |
|------------|-----------------------|
| Email      | `admin@secops.local`  |
| Contrasena | `Admin1234!`          |

Tambien puedes crear una cuenta nueva con **Registrate aqui**.

### 8.4 Probar el flujo completo

1. **Login** → debes entrar al panel principal
2. **Conexiones** → conecta una BD (SQLite con archivo local funciona)
3. **Consulta + masking** → ejecuta un test con reglas de enmascaramiento
4. **Metricas** → revisa que aparezcan tiempos de BD vs masking

Si todo eso funciona, el deploy fue exitoso.

---

## 9. Variables de entorno

Render las configura automaticamente desde `render.yaml`. Puedes verlas en cada servicio → **Environment**.

### secops-api

| Variable               | Descripcion                                      |
|------------------------|--------------------------------------------------|
| `SECRET_KEY`           | Generada automaticamente por Render              |
| `ADMIN_EMAIL`          | Email del admin inicial                            |
| `ADMIN_PASSWORD`       | Contrasena del admin (cambiala en produccion)    |
| `ADMIN_NAME`           | Nombre mostrado del admin                        |
| `MASKING_SERVICE_URL`  | URL del servicio masking (auto)                  |
| `MONITOR_SERVICE_URL`  | URL del servicio monitor (auto)                  |
| `DATA_DIR`             | `/app/data` — datos locales del contenedor       |
| `RENDER`               | `true` — Render la pone sola                     |

### secops-masking y secops-monitor

| Variable    | Descripcion        |
|-------------|----------------------|
| `DATA_DIR`  | `/app/data`          |

### Cambiar la contrasena del admin

1. Render → **secops-api** → **Environment**
2. Edita `ADMIN_PASSWORD` → pon una contrasena fuerte
3. **Save Changes**
4. Render redeploya solo (espera 1–2 min)

---

## 10. Conectar una base de datos externa (opcional)

Como Render no incluye las 7 BDs de prueba, puedes usar servicios cloud gratuitos:

### PostgreSQL gratis — Neon

1. Crea cuenta en [neon.tech](https://neon.tech)
2. Crea un proyecto → copia el **connection string**
3. En el panel SecOps → Nueva conexion → motor **postgres**
4. Rellena host, usuario, contrasena y base de datos con los datos de Neon

### MongoDB gratis — Atlas

1. Crea cuenta en [mongodb.com/atlas](https://www.mongodb.com/atlas)
2. Crea un cluster free (M0)
3. Usuario + contrasena + IP `0.0.0.0/0` (acceso desde Render)
4. En SecOps → motor **mongodb** → URI de conexion

### SQLite (mas simple para probar)

1. Ten un archivo `.db` en tu PC
2. En el panel → motor **sqlite** → ruta del archivo
3. Funciona porque la app en Render accede al archivo que subas/conectes segun tu configuracion de conexion

---

## 11. Actualizar la app despues del primer deploy

Cada cambio en el codigo se publica asi:

```powershell
cd "c:\Users\W10\Desktop\Multi-DB Masking & Performance Overhead Monitor"
git add .
git commit -m "Descripcion del cambio"
git push origin main
```

Render redeploya automaticamente si **Auto-Deploy** esta activo (viene activado por defecto).

Para redeploy manual:
1. Servicio en Render → **Manual Deploy** → **Deploy latest commit**

---

## 12. Limitaciones del plan gratuito

| Limitacion              | Detalle                                              |
|-------------------------|------------------------------------------------------|
| **Spin-down**           | Tras ~15 min sin visitas, el servicio duerme         |
| **Cold start**          | Primera visita tras dormir: 30–60 s de espera        |
| **750 h/mes**           | Limite de horas entre todos los servicios free       |
| **Datos efimeros**      | Usuarios SQLite y metricas pueden perderse al redeploy |
| **3 servicios**         | Cada uno consume horas del plan gratuito             |
| **Sin BDs incluidas**   | Debes usar externas o SQLite                         |
| **RAM limitada**        | Builds pesados pueden fallar ocasionalmente          |

Para un proyecto de demo, clase o portfolio, el plan free suele ser suficiente.

---

## 13. Solucion de problemas

### El build falla (estado Failed)

1. Servicio → **Logs** → busca la linea roja de error
2. Errores comunes:
   - `pip install` fallo → revisa `requirements.txt`
   - Timeout en build → reintenta **Manual Deploy**
   - Dockerfile no encontrado → verifica que `Dockerfile` este en la raiz del repo

### secops-api Live pero login no funciona

1. Revisa Logs de `secops-api`
2. Verifica en Environment que existan:
   - `MASKING_SERVICE_URL=https://secops-masking-xxx.onrender.com`
   - `MONITOR_SERVICE_URL=https://secops-monitor-xxx.onrender.com`
3. Confirma que masking y monitor tambien esten **Live**

### Error 502 / Bad Gateway al ejecutar tests

- Masking o Monitor estan dormidos o caidos
- Abre primero las URLs de masking/monitor en el navegador para despertarlos
- Vuelve al panel y reintenta

### "Application failed to respond"

- El servicio esta arrancando (cold start)
- Espera 60 segundos y recarga

### No puedo conectar a PostgreSQL / MySQL

- Render **no** incluye esas BDs
- Debes usar un servicio externo (Neon, Atlas, etc.) o SQLite

### Perdi usuarios despues de un redeploy

- Normal en plan free: SQLite vive dentro del contenedor
- Solucion: cambiar contrasena admin en Environment y volver a registrarte
- Para produccion real necesitarias Postgres gestionado (plan de pago en Render)

### Git push rechazado

```powershell
git pull origin main --rebase
git push origin main
```

---

## 14. Preguntas frecuentes

**¿Necesito Docker en mi PC?**
No. Render construye el Dockerfile en sus servidores.

**¿Puedo usar un dominio propio?**
Si. En secops-api → **Settings** → **Custom Domain** (plan free permite dominios custom).

**¿Es seguro dejar Admin1234!?**
No en produccion. Cambia `ADMIN_PASSWORD` en Environment de inmediato.

**¿Puedo desplegar solo la API sin masking/monitor?**
No recomendado. El panel necesita los 3 servicios para funcionar completo.

**¿Cuanto cuesta si quiero que no duerma?**
Render cobra ~7 USD/mes por servicio web sin spin-down. Serian ~21 USD/mes por los 3.

**¿Puedo volver a Docker local despues?**
Si. Usa `docker compose up` o `.\deploy.ps1` cuando tengas Docker Desktop.

---

## Checklist final

Marca cada paso cuando lo completes:

- [ ] Proyecto en GitHub con `render.yaml` en `main`
- [ ] Cuenta Render creada con GitHub
- [ ] Blueprint aplicado — 3 servicios creados
- [ ] Los 3 servicios en estado **Live**
- [ ] Login en `/login` funciona
- [ ] Panel carga despues de autenticarte
- [ ] (Opcional) Contrasena admin cambiada en Environment

---

**URL de tu repo:** https://github.com/Gino019/unificate-MotorEnmask

Cuando termines el deploy, tu app estara en una URL como:
`https://secops-api-xxxx.onrender.com/login`

Si algo falla en algun paso, copia el error de la pestana **Logs** de Render y revisalo con la seccion 13.
