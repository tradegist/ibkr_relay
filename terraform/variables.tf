variable "do_token" {
  description = "DigitalOcean API token"
  type        = string
  sensitive   = true
}

variable "droplet_size" {
  description = "Droplet size slug (e.g. s-1vcpu-512mb)"
  type        = string
  default     = "s-1vcpu-512mb"
}

variable "droplet_region" {
  description = "DigitalOcean region for the droplet"
  type        = string
  default     = "nyc3"
}

variable "site_domain" {
  description = "Domain for HTTPS API (must have DNS A record pointing to droplet)"
  type        = string
}
