terraform init
terraform apply -auto-approve \
  -var 'instance_id=i-0123456789abcdef0' \
  -var 'slack_webhook_url=https://hooks.slack.com/services/XXX/YYY/ZZZ' \
  -var 'cpu_threshold=60'