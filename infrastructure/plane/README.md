# Plane Infrastructure

Vendored copy of [Plane CE](https://github.com/makeplane/plane) v1.2.3, deployed
to a GCE VM via Terraform. Source lives in `vendor/plane/`.

## NB: Using Plane for Platform Management

**Initiatives** are the best construct for monthly management of the platform.
Create one initiative per month (e.g. "2026-04 Platform Sprint") and link the
relevant epics/work items to it. This gives a clean month-over-month view of
progress across all modules without polluting cycles or projects with
cross-cutting concerns.
