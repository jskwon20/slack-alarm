############################################################
# variables.tf
############################################################
variable "instance_id" {
  description = "알람을 걸 EC2 InstanceId"
  type        = string
}

variable "cpu_threshold" {
  description = "CPU 임계값(%)"
  type        = number
  default     = 60
}

variable "period_seconds" {
  description = "CloudWatch 메트릭 주기(초)"
  type        = number
  default     = 60
}

variable "evaluation_periods" {
  description = "평가 구간 개수(연속 N회 기준 충족 시 경보)"
  type        = number
  default     = 5
}

variable "slack_webhook_url" {
  description = "Slack Incoming Webhook URL"
  type        = string
  sensitive   = true
}

variable "display_tz" {
  description = "Slack 표시 타임존"
  type        = string
  default     = "Asia/Seoul"
}

variable "show_utc" {
  description = "UTC 시간도 함께 표기할지 여부"
  type        = bool
  default     = false
}

############################################################
# main.tf
############################################################
provider "aws" {
  region = "ap-northeast-2"
}

# 1) SNS 주제
resource "aws_sns_topic" "cw_alarms" {
  name = "cw-alarms-to-slack"
}

# 2) Lambda 실행 역할 + 기본 로그 권한
data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_exec" {
  name               = "cw-to-slack-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# 3) Lambda 코드 패키징 (로컬 파일을 ZIP으로)
#   - 같은 디렉토리에 lambda_function.py 파일이 있어야 합니다.
data "archive_file" "zip" {
  type        = "zip"
  source_file = "${path.module}/lambda_function.py"
  output_path = "${path.module}/build/cw_to_slack.zip"
}

resource "aws_lambda_function" "cw_to_slack" {
  function_name    = "cw-to-slack"
  role             = aws_iam_role.lambda_exec.arn
  runtime          = "python3.13"
  handler          = "lambda_function.lambda_handler"
  filename         = data.archive_file.zip.output_path
  source_code_hash = data.archive_file.zip.output_base64sha256
  timeout          = 10
  memory_size      = 128

  environment {
    variables = {
      SLACK_WEBHOOK_URL = var.slack_webhook_url
      DISPLAY_TZ        = var.display_tz
      SHOW_UTC          = tostring(var.show_utc)
      SLACK_USERNAME    = "CloudWatch 경보"
      SLACK_ICON_EMOJI  = ":rotating_light:"
    }
  }
}

# 4) SNS → Lambda 구독
resource "aws_sns_topic_subscription" "to_lambda" {
  topic_arn = aws_sns_topic.cw_alarms.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.cw_to_slack.arn
}

# SNS가 이 람다를 호출할 수 있도록 권한 부여
resource "aws_lambda_permission" "allow_sns_invoke" {
  statement_id  = "AllowExecutionFromSNS"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.cw_to_slack.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.cw_alarms.arn
}

# 5) CloudWatch 경보 (EC2 CPU)
resource "aws_cloudwatch_metric_alarm" "cpu_high" {
  alarm_name          = "cpu-high-${var.instance_id}"
  alarm_description   = "EC2 CPUUtilization >= ${var.cpu_threshold}%"
  namespace           = "AWS/EC2"
  metric_name         = "CPUUtilization"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = var.cpu_threshold
  statistic           = "Average"
  period              = var.period_seconds
  evaluation_periods  = var.evaluation_periods
  datapoints_to_alarm = var.evaluation_periods
  treat_missing_data  = "notBreaching"

  dimensions = {
    InstanceId = var.instance_id
  }

  alarm_actions = [aws_sns_topic.cw_alarms.arn]
  ok_actions    = [aws_sns_topic.cw_alarms.arn]
}

output "sns_topic_arn" {
  value = aws_sns_topic.cw_alarms.arn
}

output "lambda_function_name" {
  value = aws_lambda_function.cw_to_slack.function_name
}

output "alarm_name" {
  value = aws_cloudwatch_metric_alarm.cpu_high.alarm_name
}
