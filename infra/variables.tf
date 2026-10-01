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
