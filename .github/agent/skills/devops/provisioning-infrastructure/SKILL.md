---
name: Provisioning Infrastructure
description: Manage cloud resources using Infrastructure as Code (IaC) with Terraform or Pulumi to ensure reproducibility and prevent configuration drift.
---

# Provisioning Infrastructure

## Goal
Define the entire production environment in code, allowing it to be spun up, torn down, or replicated with a single command, ensuring "Environment Parity" between dev, staging, and prod.

## When to Use
- Setting up a new project's cloud resources (AWS/GCP/Azure).
- Adding a new service (e.g., Redis, S3 bucket).
- Changing infrastructure configuration (scaling, networking).

## Instructions

### 1. State Management
Never store state locally. Use a remote backend (S3 + DynamoDB for locking).
```hcl
terraform {
  backend "s3" {
    bucket         = "my-app-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}
```

### 2. Modularity
Don't write one giant `main.tf`. Split resources into logical modules.
- `modules/networking` (VPC, Subnets)
- `modules/database` (RDS, Redis)
- `modules/compute` (ECS, Lambda, EC2)

### 3. Least Privilege (IAM)
Define distinct IAM roles for each service.
- The `web-server` role should write to S3, but not delete from it.
- The `worker` role needs SQS access, but not public internet ingress.

### 4. Variables & Secrets
- Use `variables.tf` for everything that changes between environments (instance size, region).
- NEVER commit `terraform.tfvars` if it contains secrets. Use environment variables (`TF_VAR_db_password`) in CI/CD.

## Constraints

### ✅ Do
- **DO**: Run `terraform plan` and have it reviewed before every `terraform apply`.
- **DO**: Tag every resource with `Environment`, `Owner`, and `Service`.
- **DO**: Use "snake_case" for resource names.

### ❌ Don't
- **DON'T**: Manually change settings in the Cloud Console (ClickOps). It causes drift.
- **DON'T**: Hardcode secrets or account IDs in `.tf` files.
- **DON'T**: Use the `default` VPC; always create a custom one.

## Output Format
- `terraform/` directory with `main.tf`, `variables.tf`, `outputs.tf`.
- `terraform plan` output file.

## Dependencies
- `shared/environment-config/SKILL.md`
