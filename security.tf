# Bastion Host Security Group
resource "aws_security_group" "jskwon_bastion_sg" {
  name        = "jskwon-bastion-sg"
  description = "Security group for bastion host"
  vpc_id      = module.vpc.vpc_id

  # Allow SSH access
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.bastion_cidr]
    description = "Allow SSH access from specified IP."
  }
  # Allow HTTPS access
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = [var.bastion_cidr]
    description = "Allow HTTPS access from specified IP."
  }
  # Allow VSCode web access
  ingress {
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = [var.bastion_cidr]
    description = "Allow VSCode web access from specified IP."
  }
  # Allow all outbound traffic
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound traffic from the bastion host."
  }

  tags = {
    Name = "jskwon-bastion-sg"
  }
}