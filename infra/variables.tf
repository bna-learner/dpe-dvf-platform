variable "region" {
  description = "Région AWS de déploiement."
  type        = string
  default     = "eu-west-3"
}

variable "environnement" {
  description = "Nom de l'environnement : dev ou prod."
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "prod"], var.environnement)
    error_message = "L'environnement doit valoir dev ou prod."
  }
}

variable "github_proprietaire" {
  description = "Propriétaire du dépôt GitHub autorisé à endosser le rôle d'ingestion."
  type        = string
  default     = "bna-learner"
}

variable "github_proprietaire_id" {
  description = "Identifiant numérique du propriétaire (sujet OIDC immuable)."
  type        = string
  default     = "258072802"
}

variable "github_depot" {
  description = "Nom du dépôt GitHub."
  type        = string
  default     = "dpe-dvf-platform"
}

variable "github_depot_id" {
  description = "Identifiant numérique du dépôt (sujet OIDC immuable)."
  type        = string
  default     = "1379681259"
}
