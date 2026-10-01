# Informe de Actividad: Pipeline DevOps Completo

**Proyecto:** devops-pipeline-demo
**Repositorio:** https://github.com/aalexanderdev/repoapp

## 1. Objetivo

Construir e integrar un pipeline completo de CI/CD que cubra: contenerización,
infraestructura como código, automatización de build/test/despliegue,
seguridad (SAST/DAST), orquestación en Kubernetes con auto-escalado,
monitoreo con Prometheus/Grafana y prácticas de FinOps.

## 2. Pasos realizados

### 2.1 Configuración del repositorio

- Se creó el repositorio `devops-pipeline-demo` con la siguiente estructura:
  `app/`, `docker/`, `terraform/`, `k8s/`, `monitoring/`,
  `.github/workflows/`, `docs/`.
- Se añadió `.gitignore` para excluir artefactos sensibles o generados
  (`terraform.tfvars`, `*.tfstate`, `.venv/`, `__pycache__/`).
- Convención de commits usada: `tipo: descripción corta` (ej.
  `feat: agrega Dockerfile multi-stage`, `fix: corrige probe de liveness`,
  `docs: actualiza README`), con commits frecuentes por cada componente
  entregado (app, Docker, Terraform, K8s, CI/CD, monitoreo, docs).

### 2.2 Aplicación de ejemplo

Se implementó una API Flask mínima (`app/main.py`) con endpoints `/`,
`/health` y `/metrics` (este último expone métricas en formato Prometheus
usando la librería `prometheus-client`), junto con tests unitarios
(`app/tests/test_app.py`) que cubren los tres endpoints.

### 2.3 Docker

Se construyó un `Dockerfile` multi-stage (`docker/Dockerfile`):

- **Etapa `builder`**: basada en `python:3.12-slim`, instala dependencias en
  un prefix aislado (`--prefix=/install`), incluyendo el compilador `gcc`
  solo en esta etapa.
- **Etapa `runtime`**: parte de una imagen `python:3.12-slim` limpia, copia
  únicamente `/install` y el código fuente, crea un usuario no root (`app`),
  define un `HEALTHCHECK` y ejecuta la app con `gunicorn` (no el servidor de
  desarrollo de Flask).

Resultado: la imagen final no incluye herramientas de compilación ni caché de
`pip`, reduciendo tamaño y superficie de ataque.

### 2.4 Terraform

Infraestructura definida como código en `terraform/`, dividida en dos
módulos reutilizables:

- **`modules/network`**: VPC, subredes públicas y privadas en múltiples AZ,
  Internet Gateway, NAT Gateway y tablas de ruteo.
- **`modules/eks`**: cluster EKS, roles IAM para el plano de control y para
  los nodos, y un node group con `scaling_config` (min/max/desired) que
  permite autoescalar la capa de cómputo. En entornos no productivos se
  soporta `capacity_type = "SPOT"` o instancias compatibles con AWS Free Tier
  (`t3.micro`/`t2.micro` en `us-east-2`) para reducir costos (FinOps aplicado
  también a nivel de infraestructura).

Todas las variables están centralizadas en `variables.tf` (raíz) con valores
por defecto sensatos y un archivo `terraform.tfvars.example` documentado; los
outputs (`outputs.tf`) exponen el nombre del cluster, su endpoint y el
comando para configurar `kubectl`.

### 2.5 Pipeline CI/CD (GitHub Actions)

Archivo `.github/workflows/ci-cd.yaml`, con los siguientes jobs encadenados
mediante `needs`:

1. **build-test**: instala dependencias, corre `flake8` y `pytest` con
   cobertura.
2. **sast**: análisis estático con `bandit` (Python) y `CodeQL`
   (GitHub-nativo), con reportes subidos como artifacts.
3. **docker-build-push**: build multi-stage con Buildx y caché de GitHub
   Actions, push a GHCR, y escaneo de vulnerabilidades de la imagen con
   Trivy (resultados subidos a la pestaña *Security* del repo vía SARIF).
4. **terraform**: `terraform init/validate/plan/apply` contra AWS (región `us-east-2`),
   usando backend remoto en S3 con bloqueo en DynamoDB mediante los secretos
   `secrets.AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `TF_STATE_BUCKET` y
   `TF_LOCK_TABLE`.
5. **deploy**: actualiza `kubeconfig` y aplica los manifiestos de `k8s/`,
   luego actualiza la imagen del Deployment y espera el `rollout`.
6. **dast**: análisis dinámico con OWASP ZAP (`zap-baseline`) contra la URL
   pública de la aplicación ya desplegada, con reporte HTML como artifact.

El pipeline solo ejecuta los jobs de infraestructura/despliegue en push a
`main`; los Pull Requests solo disparan build, test y SAST, para dar
feedback rápido sin tocar infraestructura real.

### 2.6 Kubernetes

Manifiestos en `k8s/`:

- `00-namespace.yaml`: namespace dedicado `demo-app`.
- `01-deployment.yaml`: 2 réplicas, `requests`/`limits` de CPU y memoria,
  `readinessProbe`/`livenessProbe` sobre `/health`, `securityContext` no root
  y filesystem de solo lectura, y anotaciones `prometheus.io/*` para
  scraping.
- `02-service.yaml`: `ClusterIP` que expone el puerto 80 hacia el 8080 del
  pod.
- `03-ingress.yaml`: Ingress con clase `nginx`, TLS vía `cert-manager` y
  redirección HTTPS forzada.
- `04-hpa.yaml`: `HorizontalPodAutoscaler` (API `autoscaling/v2`) que escala
  entre 2 y 8 réplicas según CPU (70%) y memoria (80%), con `behavior`
  configurado para escalar hacia arriba rápido y hacia abajo con un período
  de estabilización (evita oscilaciones y ahorra costos).
- `05-resource-quota.yaml`: `ResourceQuota` y `LimitRange` a nivel de
  namespace, para acotar el consumo máximo posible.
- `06-finops-scheduler.yaml`: `CronJob`s que escalan el Deployment a 0
  réplicas fuera de horario laboral (entornos de desarrollo) y lo reactivan
  por la mañana, con su propio `ServiceAccount`/`Role`/`RoleBinding` con
  permisos mínimos (solo `deployments/scale`).

### 2.7 Monitoreo (Prometheus + Grafana)

- Se documentó la instalación del stack `kube-prometheus-stack` vía Helm,
  con valores propios en `monitoring/kube-prometheus-stack-values.yaml`
  (retención de métricas, límites de recursos del propio stack de
  monitoreo, y configuración para cargar dashboards personalizados).
- `service-monitor.yaml`: le indica a Prometheus que scrapee el endpoint
  `/metrics` de `demo-app-svc` cada 15 segundos.
- `grafana-dashboard-demo-app.json`: dashboard con 4 paneles — requests por
  segundo por endpoint, latencia p95, uso de CPU por pod y número de
  réplicas actuales del HPA.
- `prometheus-rules.yaml`: alertas para tasa de error 5xx elevada, pods
  caídos, y una alerta de FinOps que avisa si el HPA queda al máximo de
  réplicas de forma sostenida (posible sobrecosto o anomalía de tráfico).

### 2.8 FinOps

Medidas aplicadas en distintas capas:

- **Infraestructura**: node group de EKS en `us-east-2` con `min/max/desired size`,
  utilizando instancias compatibles con AWS Free Tier (`t3.micro`/`t2.micro`) y soporte
  para instancias Spot en entornos no productivos.
- **Aplicación**: HPA con ventana de estabilización para evitar escalados
  innecesarios; `ResourceQuota`/`LimitRange` para prevenir sobre-provisión.
- **Operación**: `CronJob`s de apagado/encendido automático fuera de horario
  laboral en `dev` (escala a 0 a las 21:00 y restablece a las 07:00).
- **Observabilidad**: alertas específicas en Prometheus (`FinOpsHighPodCount`,
  `FinOpsMemoryLeakRisk`) para detectar anomalías de gasto o saturación.

### 2.9 Documentación

Se escribió un `README.md` exhaustivo con: descripción del proyecto, estructura
del repositorio, instrucciones para correr localmente (Python y Docker), tabla
de secretos requeridos en GitHub Actions para garantizar replicabilidad sin
asistencia humana, instrucciones para desplegar en un entorno de pruebas
(Terraform en `us-east-2` + kubectl + Helm), pasos de validación de
despliegue/autoescalado/monitoreo, sección dedicada a la estrategia integral de
FinOps (costos en infraestructura, aplicación, operación y observabilidad), y una
sección de evidencias preparada para documentar capturas y logs de ejecución.

## 3. Buenas prácticas de seguridad aplicadas

- Ninguna credencial ni secreto está hardcodeado; todo se referencia vía
  `secrets.*` de GitHub Actions o variables de entorno.
- `terraform.tfvars` y los archivos de estado (`*.tfstate`) están excluidos
  del control de versiones.
- Contenedor corriendo como usuario no root, con `allowPrivilegeEscalation:
  false` y filesystem raíz de solo lectura.
- Tres capas de análisis de seguridad automatizado: SAST de código (Bandit +
  CodeQL), escaneo de imagen (Trivy) y DAST de la aplicación desplegada
  (OWASP ZAP).
- Permisos mínimos (RBAC) para el `ServiceAccount` usado por los CronJobs de
  FinOps, limitado únicamente a `deployments/scale`.

## 4. Resultado / Estado de la entrega

- [x] Repositorio con la estructura completa.
- [x] Dockerfile multi-stage optimizado.
- [x] Terraform modularizado (red + cluster Kubernetes) con variables.
- [x] Pipeline CI/CD con build, test, build/push de imagen, Terraform,
      despliegue a Kubernetes, SAST y DAST.
- [x] Manifiestos de Kubernetes: Deployment, Service, Ingress, HPA.
- [x] Configuración de Prometheus + Grafana con dashboard y alertas.
- [x] README con instrucciones de uso y validación.
- [x] Evidencias reales: capturas del pipeline CI/CD en verde (Run #16) y del
      dashboard de Grafana con tráfico real en `docs/evidencias/`, junto con
      reportes descargables de SAST, DAST y escaneo de imagen.

## 5. Enlaces
 
- Repositorio: https://github.com/aalexanderdev/repoapp
- Link de Google Drive con este informe y evidencias: https://docs.google.com/document/d/1juL3D9j6JXuB3G4sEd5jSOxFpBFv8_PbzbqEeVzDbIo/edit?usp=sharing
