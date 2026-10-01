provider "aws" {
  region = var.region

  default_tags {
    tags = {
      projet        = "dpe-dvf-platform"
      environnement = var.environnement
      gere_par      = "terraform"
    }
  }
}
