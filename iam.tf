variable "jskwon_cloudwatch_agent" {
  description = "EC2에서 사용할 CloudWatch Agent용 IAM Role 이름"
  type        = string
  default     = "jskwon-cloudwatch-agent"
}

variable "enable_ssm" {
  description = "SSM으로 원격 관리/배포를 쓸지 여부"
  type        = bool
  default     = true
}

# EC2가 이 Role을 사용할 수 있도록 하는 신뢰 정책
data "aws_iam_policy_document" "ec2_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "jskwon_test_cwagent" {
  name               = var.jskwon_cloudwatch_agent
  assume_role_policy = data.aws_iam_policy_document.ec2_trust.json
  description        = "Permissions for CloudWatch Agent (and optional SSM) on EC2"
}

# Instance Profile (EC2에 실제로 연결되는 객체)
resource "aws_iam_instance_profile" "cwagent" {
  name = "${var.jskwon_cloudwatch_agent}-profile"
  role = aws_iam_role.jskwon_test_cwagent.name
}

# CloudWatch Agent 권한 (관리형 정책)
resource "aws_iam_role_policy_attachment" "cwagent_cw" {
  role       = aws_iam_role.jskwon_test_cwagent.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}

# (선택) SSM으로 에이전트/서버 원격 관리
resource "aws_iam_role_policy_attachment" "cwagent_ssm" {
  count      = var.enable_ssm ? 1 : 0
  role       = aws_iam_role.jskwon_test_cwagent.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

output "cwagent_instance_profile_name" {
  value       = aws_iam_instance_profile.cwagent.name
  description = "EC2에 연결할 Instance Profile 이름"
}
