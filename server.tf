resource "tls_private_key" "jskwon_key" {
  algorithm = "RSA"
  rsa_bits  = 2048
}

# 로컬에 키 파일 저장
resource "local_file" "private_key" {
  content  = tls_private_key.jskwon_key.private_key_pem
  filename = "${path.module}/jskwon-test-key"
  file_permission = "0600"
}

# AWS 키 페어 등록
resource "aws_key_pair" "jskwon" {
  key_name   = "jskwon-test-key"
  public_key = tls_private_key.jskwon_key.public_key_openssh
}

# EC2 인스턴스 생성 (에러 수정판)
resource "aws_instance" "jskwon_bastion_ec2" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = "t3.small"
  subnet_id                   = module.vpc.public_subnets[0]
  key_name                    = aws_key_pair.jskwon.key_name
  associate_public_ip_address = true
  vpc_security_group_ids      = [aws_security_group.jskwon_bastion_sg.id]
  iam_instance_profile        = aws_iam_instance_profile.cwagent.name

  tags = { Name = "jskwon-bastion-ec2" }

  depends_on = [
    aws_key_pair.jskwon,
    module.vpc
  ]

  provisioner "remote-exec" {
  inline = [
    # 패키지 인덱스 갱신
    "sudo apt-get update -y",

    # --- CloudWatch Agent 설치 ---
    "curl -fsSL -o /tmp/amazon-cloudwatch-agent.deb https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb",
    "sudo dpkg -i /tmp/amazon-cloudwatch-agent.deb || sudo apt-get -f install -y",
    "sudo systemctl enable amazon-cloudwatch-agent || true",
    "sudo systemctl start amazon-cloudwatch-agent || true",

    # --- SSM Agent: snap/apt 모두 대응 (heredoc 사용) ---
    <<-EOT
bash -lc '
  set -euxo pipefail
  if command -v snap >/dev/null 2>&1 && snap list amazon-ssm-agent >/dev/null 2>&1; then
    sudo snap start amazon-ssm-agent || true
    sudo systemctl enable --now snap.amazon-ssm-agent.amazon-ssm-agent.service || true
  else
    sudo snap install amazon-ssm-agent --classic || sudo apt-get install -y amazon-ssm-agent || true
    sudo systemctl enable --now amazon-ssm-agent || true
  fi
'
EOT
  ]

  connection {
    type        = "ssh"
    user        = "ubuntu"
    host        = self.public_ip
    private_key = tls_private_key.jskwon_key.private_key_pem
    timeout     = "5m"
  }
}
}
