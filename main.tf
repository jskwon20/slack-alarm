# VPC 구성
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = local.project
  cidr = var.vpc_cidr

  azs             = ["ap-northeast-2a", "ap-northeast-2c"]
  public_subnets  = [for k, v in ["ap-northeast-2a", "ap-northeast-2c"] : cidrsubnet(var.vpc_cidr, 8, k)]
  private_subnets = [for k, v in ["ap-northeast-2a", "ap-northeast-2c"] : cidrsubnet(var.vpc_cidr, 8, k + 10)]

  enable_nat_gateway        = true
  single_nat_gateway        = true
  create_igw                = true
  enable_dns_hostnames      = true
  enable_dns_support        = true
  map_public_ip_on_launch   = true
}
