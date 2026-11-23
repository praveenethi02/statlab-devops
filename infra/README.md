# StatLab on Azure

The public HTTPS frontend serves the web assets and proxies same-origin API requests to the internal backend Container App. The backend validates the public origin, runs schema migrations under a database lock, and connects over verified TLS to Azure Database for PostgreSQL Flexible Server on a delegated subnet. The browser needs only the frontend URL. Each application has a separate image and revision history. PostgreSQL retains the existing dataset and analysis JSON representation.

## Set up Jenkins once

Use a trusted Jenkins multibranch job and a dedicated Linux agent labelled `statlab-linux` with Git, Python 3.13 and venv, Node/npm, Docker Engine and Compose v2, Terraform 1.6+, ansible-core, OpenSSL and Azure CLI with the containerapp extension. The release uses the Azure agent's system-assigned managed identity. Run untrusted contributions on an isolated agent without access to deployment credentials or this identity.

Configure the following job environment variables.

| Variable | Value |
| --- | --- |
| `ARM_SUBSCRIPTION_ID`, `ARM_TENANT_ID` | Target Azure subscription and tenant |
| `TF_VAR_prefix`, `TF_VAR_location` | Unique 3–16 character lowercase alphanumeric prefix starting with a letter, and an Azure region supporting the selected services |
| `TF_VAR_registry_name`, `TF_VAR_registry_resource_group` | Existing Azure Container Registry and its resource group in the target subscription |
| `STATE_RESOURCE_GROUP`, `STATE_STORAGE_ACCOUNT`, `STATE_CONTAINER` | Existing private Azure Blob container for Terraform state, accessible by the agent |

Add Jenkins Secret Text credentials `statlab-db-password` and `statlab-app-secret`. Use a stable, strong PostgreSQL password satisfying Azure's password policy and a separately generated random signing key. The initial setup uses the PostgreSQL server owner for schema creation and API traffic. State and saved plans contain sensitive values. Restrict the state container and job to deployment operators.

The agent needs permission to provision the resource group and its contents, read and push images to ACR, grant the pull identity its ACR role, and read/write the state container (Storage Blob Data Contributor). Enable ACR ARM-audience authentication and use an ACR configured for classic registry RBAC (`AcrPush` and `AcrPull`). Register Microsoft.App, Microsoft.DBforPostgreSQL, Microsoft.Network and Microsoft.ManagedIdentity in the subscription. Provider registration may require additional subscription permissions.

## Run the pipeline

A regular build runs the Python suite, JavaScript syntax check, Terraform validation and Ansible syntax check. It builds the two application images and starts them with a disposable PostgreSQL instance. The smoke test signs in, saves a dataset and checks its persisted analysis through Nginx.

Selecting **DEPLOY_AZURE** on **main** publishes those tested images to the configured registry, applies the Terraform plan, and runs the Ansible release playbook. Terraform creates the infrastructure and bootstraps both apps with the tested images. On later releases Ansible updates changed images, waits for the new revisions, and checks the public frontend and API. Use the `frontend_url` Terraform output for the site address. Region capacity, policy and subscription quota are checked during an actual deployment.

## Database operations

The Docker setup keeps PostgreSQL in the `postgres-data` volume. Azure maintains independent managed database backups with seven-day retention. For logical backups use `pg_dump` and restore with `pg_restore` into a fresh database. Azure database administration requires connectivity to the private network.

A fresh PostgreSQL deployment starts with an empty database. Preserve any records from an earlier live installation before replacing it, and verify migrated records before directing users to the new service. Keep database backups and environment secrets out of Git.
