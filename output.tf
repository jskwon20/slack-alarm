output "ssh_connection" {
  value       = "ssh -i jskwon-test-key ubuntu@${aws_instance.jskwon_bastion_ec2.public_ip}"
  description = "SSH 연결 명령어"
}