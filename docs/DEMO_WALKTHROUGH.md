# GrantScope Demo Walkthrough

## Recommended 2-3 minute demonstration

### 1. Open the workbench

~~~text
http://localhost:5173
~~~

Explain that GrantScope is an export-first Entra OAuth and service-principal investigation workbench.

### 2. Import the demo evidence bundle

~~~text
sample-data\demo-tenant.zip
~~~

Click:

~~~text
Import and investigate
~~~

The bundle includes applications, service principals, owners, credentials, delegated grants, app-role assignments, directory audits, and sign-in evidence.

### 3. Show the triage queue

Highlight:

- One critical case
- Two high-severity cases
- No high/critical alert for NorthBridge Meetings

This demonstrates that GrantScope does not simply flag every application.

### 4. Open Provisioning Bridge

Explain the correlation sequence:

~~~text
High-impact Application.ReadWrite.All assignment
    ->
Credential addition
    ->
Service-principal use within 60 minutes
~~~

Highlight:

- Timeline
- Correlation IDs
- Credential lifetime
- Owner state
- Permission blast radius
- First-use sign-in context

### 5. Show the benign-validation checklist

Explain that GrantScope does not claim the app is malicious. It provides evidence and asks an analyst to validate change records, owners, deployment context, source IP, and credential rotation.

### 6. Update workflow

Set:

~~~text
Status: Under review
Disposition: Suspicious
Assignment: Cloud Identity Review Queue
~~~

Add a short analyst note.

### 7. Export PDF

Use the Export PDF action and explain that the report is intended for escalation and human review.