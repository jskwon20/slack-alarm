variable "vpc_cidr" {
  description = "VPC 대역대"
  type        = string
  default     = "10.0.0.0/16"
}

variable "bastion_cidr" {
  description = "Bastion host CIDR"
  type        = string
}