# Future Microsoft Graph Connector Plan

## Goal

Add optional read-only Microsoft Graph collection without replacing the export-first investigation workflow.

## Principles

- Read-only collection only
- No tenant credentials stored in PostgreSQL
- Clear evidence coverage and missing-data reporting
- Export-first mode remains available for offline demonstration and investigation
- Live Graph records map into the same canonical GrantScope evidence model

## Planned collection areas

~~~text
Applications
Service principals
Application owners
Service-principal owners
Credential metadata
OAuth delegated permission grants
App-role assignments
Directory audit events
User and service-principal sign-ins where available
~~~

## Data flow

~~~text
Microsoft Graph
    ->
Read-only collection adapter
    ->
GrantScope canonical evidence bundle
    ->
Existing normalization layer
    ->
Existing detection engine
~~~

## Safety boundary

The connector will not create applications, grant consent, add credentials, assign roles, disable principals, revoke grants, or change tenant configuration.