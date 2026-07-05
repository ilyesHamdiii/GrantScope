# GrantScope Public Demo Deployment

## Scope

The `public-demo` branch is a locked portfolio deployment.

It serves synthetic NorthBridge evidence only.

## Safety Controls

- No Microsoft Graph client secret is supplied to the deployment.
- No Entra collector runs in the public environment.
- ZIP uploads are disabled in the interface and rejected by the API.
- Analysis, case generation, and workflow updates are rejected by the API.
- The only seeded data is `sample-data/demo-tenant.zip`.
- PDF, HTML, and Markdown case exports remain available for synthetic cases.

## Local Verification

Run:

docker compose -f docker-compose.public-demo.yml -p grantscope-public-demo up --build -d

Then open:

http://localhost:8088

## Render Deployment

1. Push the `public-demo` branch.
2. In Render, create a Blueprint from this repository.
3. Select `render.yaml`.
4. Confirm the service and database names.
5. Deploy.
6. Verify the synthetic-demo banner, seeded critical case, PDF export, and blocked write behavior.

## Important

This is a portfolio demo environment, not a production deployment.