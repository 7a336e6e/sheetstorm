# Configuration

## Environment Variables

Copy `.env.example` to `.env` and configure. The `start.sh` script auto-generates cryptographic keys on first run.

| Variable                  | Required | Default                           | Description                           |
|---------------------------|----------|-----------------------------------|---------------------------------------|
| `SECRET_KEY`              | Yes      | —                                 | Flask secret key (auto-generated)     |
| `JWT_SECRET_KEY`          | Yes      | —                                 | JWT signing key (auto-generated)      |
| `FERNET_KEY`              | Yes      | —                                 | Fernet encryption key (auto-generated)|
| `DATABASE_URL`            | Yes      | `postgresql://sheetstorm:changeme@localhost:5432/sheetstorm` | PostgreSQL connection |
| `REDIS_URL`               | Yes      | `redis://localhost:6379/0`        | Redis connection                      |
| `FLASK_ENV`               | No       | `production`                      | `development` or `production`         |
| `POSTGRES_USER`           | No       | `sheetstorm`                      | PostgreSQL user                       |
| `POSTGRES_PASSWORD`       | No       | `changeme`                        | PostgreSQL password                   |
| `POSTGRES_DB`             | No       | `sheetstorm`                      | PostgreSQL database name              |
| `ADMIN_EMAIL`             | No       | `admin@sheetstorm.local`          | Default admin user email              |
| `ADMIN_PASSWORD`          | No       | `ChangeMe123!`                    | Default admin user password           |
| `OPENAI_API_KEY`          | No       | —                                 | OpenAI API key for AI reports         |
| `GOOGLE_AI_API_KEY`       | No       | —                                 | Google Gemini API key                 |
| `S3_ENDPOINT`             | No       | —                                 | S3-compatible endpoint URL            |
| `S3_ACCESS_KEY`           | No       | —                                 | S3 access key                         |
| `S3_SECRET_KEY`           | No       | —                                 | S3 secret key                         |
| `S3_BUCKET`               | No       | `sheetstorm-artifacts`            | S3 bucket name                        |
| `S3_REGION`               | No       | `us-east-1`                       | S3 region                             |
| `SLACK_WEBHOOK_URL`       | No       | —                                 | Slack webhook for notifications       |
| `SUPABASE_URL`            | No       | —                                 | Supabase URL for SSO                  |
| `SUPABASE_ANON_KEY`       | No       | —                                 | Supabase anonymous key                |
| `NEXT_PUBLIC_API_URL`     | No       | `http://127.0.0.1:5000/api/v1`   | Backend API URL for frontend          |
| `NEXT_PUBLIC_WS_URL`      | No       | `http://127.0.0.1:5000`          | WebSocket URL for frontend            |

## Database Schema

23 tables with UUID primary keys, automatic `updated_at` triggers, and auto-incrementing incident numbers per organization.

**Key Tables**: `users`, `roles`, `user_roles`, `organizations`, `incidents`, `incident_assignments`, `timeline_events`, `compromised_hosts`, `compromised_accounts`, `network_indicators`, `host_based_indicators`, `malware_tools`, `attack_graph_nodes`, `attack_graph_edges`, `artifacts`, `chain_of_custody`, `tasks`, `task_comments`, `reports`, `notifications`, `audit_logs`, `integrations`, `teams`, `team_members`.

**Extensions**: `uuid-ossp` (UUID generation), `pgcrypto` (cryptographic functions).
