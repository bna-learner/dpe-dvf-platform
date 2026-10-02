terraform {
  backend "s3" {
    bucket       = "dpe-dvf-tfstate-f4e614"
    key          = "bootstrap/terraform.tfstate"
    region       = "eu-west-3"
    encrypt      = true
    use_lockfile = true
  }
}
