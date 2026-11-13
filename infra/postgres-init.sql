-- Separate roles: migrations run as the owner; the API connects as a
-- non-superuser without BYPASSRLS so row-level security always applies.
CREATE ROLE axiom_app LOGIN PASSWORD 'axiom_app' NOSUPERUSER NOBYPASSRLS;
GRANT CONNECT ON DATABASE axiom TO axiom_app;
