# FilingsDesk on Google Cloud: Cloud Run (API + ingestion job), Cloud SQL Postgres 16
# with pgvector, Artifact Registry, Secret Manager, and a least-privilege service account.
#
#   terraform init
#   terraform apply -target=google_artifact_registry_repository.images   # 1. registry
#   gcloud builds submit --config deploy/gcp/cloudbuild.yaml (repo root)                # 2. images
#   terraform apply                                                      # 3. the rest
#   gcloud run jobs execute filingsdesk-ingest --region europe-west2 --wait
#
# Redis is left out on purpose: the cache falls back to in-memory (ADR-0002), and
# Memorystore would need a VPC connector for a demo that doesn't need one.

terraform {
  required_providers {
    google = { source = "hashicorp/google", version = "~> 6.0" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
}

variable "project_id" { type = string }
variable "region" {
  type    = string
  default = "europe-west2" # London: data stays in the UK
}
variable "image_tag" {
  type    = string
  default = "latest"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  services = ["run.googleapis.com", "sqladmin.googleapis.com", "artifactregistry.googleapis.com",
  "secretmanager.googleapis.com", "cloudbuild.googleapis.com"]
  registry = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

resource "google_project_service" "apis" {
  for_each           = toset(local.services)
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "images" {
  repository_id = "filingsdesk"
  format        = "DOCKER"
  location      = var.region
  depends_on    = [google_project_service.apis]
}

# --- database -------------------------------------------------------------------

resource "google_sql_database_instance" "pg" {
  name                = "filingsdesk-pg"
  database_version    = "POSTGRES_16"
  region              = var.region
  deletion_protection = false # lab: `terraform destroy` must work
  settings {
    tier    = "db-f1-micro"
    edition = "ENTERPRISE"
  }
  depends_on = [google_project_service.apis]
}

resource "google_sql_database" "app" {
  name     = "filingsdesk"
  instance = google_sql_database_instance.pg.name
}

resource "random_password" "db" {
  length  = 24
  special = false
}

resource "google_sql_user" "app" {
  name     = "filingsdesk"
  instance = google_sql_database_instance.pg.name
  password = random_password.db.result
}

# The connection string lives in Secret Manager, never in env files or the image.
resource "google_secret_manager_secret" "database_url" {
  secret_id = "filingsdesk-database-url"
  replication {
    auto {}
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "database_url" {
  secret      = google_secret_manager_secret.database_url.id
  secret_data = "postgresql+psycopg://filingsdesk:${random_password.db.result}@/filingsdesk?host=/cloudsql/${google_sql_database_instance.pg.connection_name}"
}

# --- identity ---------------------------------------------------------------------

resource "google_service_account" "run" {
  account_id   = "filingsdesk-run"
  display_name = "FilingsDesk Cloud Run runtime"
}

resource "google_project_iam_member" "sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.run.email}"
}

resource "google_secret_manager_secret_iam_member" "read_db_url" {
  secret_id = google_secret_manager_secret.database_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.run.email}"
}

# --- compute ----------------------------------------------------------------------

resource "google_cloud_run_v2_service" "api" {
  name                = "filingsdesk-api"
  location            = var.region
  deletion_protection = false
  template {
    service_account = google_service_account.run.email
    scaling {
      min_instance_count = 0 # scale to zero: no traffic, no bill
      max_instance_count = 2
    }
    containers {
      image = "${local.registry}/api:${var.image_tag}"
      ports {
        container_port = 8000
      }
      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.database_url.secret_id
            version = "latest"
          }
        }
      }
      startup_probe {
        http_get {
          path = "/health"
        }
        initial_delay_seconds = 5
        failure_threshold     = 10
      }
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
    }
    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.pg.connection_name]
      }
    }
  }
  depends_on = [google_project_iam_member.sql_client, google_secret_manager_secret_iam_member.read_db_url]
}

# Public demo endpoint. A client deployment would sit behind IAP or an API gateway.
resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.api.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Migrations + ingestion as a one-off job, so API replicas never race on `alembic upgrade`.
resource "google_cloud_run_v2_job" "ingest" {
  name                = "filingsdesk-ingest"
  location            = var.region
  deletion_protection = false
  template {
    template {
      service_account = google_service_account.run.email
      max_retries     = 1
      containers {
        image   = "${local.registry}/ingestion:${var.image_tag}"
        command = ["sh", "-c", "alembic upgrade head && filingsdesk-ingest --fixtures"]
        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.database_url.secret_id
              version = "latest"
            }
          }
        }
        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
      }
      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.pg.connection_name]
        }
      }
    }
  }
  depends_on = [google_project_iam_member.sql_client, google_secret_manager_secret_iam_member.read_db_url]
}

output "api_url" { value = google_cloud_run_v2_service.api.uri }
output "registry" { value = local.registry }
