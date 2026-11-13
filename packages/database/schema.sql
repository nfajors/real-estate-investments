BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE organizations (
    id UUID NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    slug VARCHAR(120) NOT NULL, 
    plan VARCHAR(40) NOT NULL, 
    stripe_customer_id VARCHAR(120), 
    settings JSONB NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_organizations_slug ON organizations (slug);

CREATE TABLE users (
    id UUID NOT NULL, 
    email VARCHAR(320) NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    password_hash VARCHAR(300) NOT NULL, 
    is_active BOOLEAN NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE TABLE audit_logs (
    id UUID NOT NULL, 
    org_id UUID NOT NULL, 
    user_id UUID, 
    action VARCHAR(80) NOT NULL, 
    entity_type VARCHAR(40) NOT NULL, 
    entity_id VARCHAR(64), 
    property_id UUID, 
    details JSONB NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE, 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_audit_logs_org_id ON audit_logs (org_id);

CREATE INDEX ix_audit_logs_property_id ON audit_logs (property_id);

CREATE INDEX ix_audit_org_created ON audit_logs (org_id, created_at);

CREATE TABLE invitations (
    id UUID NOT NULL, 
    org_id UUID NOT NULL, 
    email VARCHAR(320) NOT NULL, 
    role VARCHAR(20) NOT NULL, 
    token_hash VARCHAR(128) NOT NULL, 
    invited_by UUID, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    accepted_at TIMESTAMP WITH TIME ZONE, 
    revoked_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(invited_by) REFERENCES users (id) ON DELETE SET NULL, 
    FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE, 
    UNIQUE (token_hash)
);

CREATE INDEX ix_invitations_org_id ON invitations (org_id);

CREATE TABLE organization_members (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    org_id UUID NOT NULL, 
    role VARCHAR(20) NOT NULL, 
    invited_at TIMESTAMP WITH TIME ZONE, 
    joined_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE, 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    CONSTRAINT uq_member_user_org UNIQUE (user_id, org_id)
);

CREATE INDEX ix_organization_members_org_id ON organization_members (org_id);

CREATE INDEX ix_organization_members_user_id ON organization_members (user_id);

CREATE TABLE properties (
    id UUID NOT NULL, 
    org_id UUID NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    property_type VARCHAR(40) NOT NULL, 
    address VARCHAR(300), 
    city VARCHAR(120), 
    state VARCHAR(60), 
    zip_code VARCHAR(20), 
    status VARCHAR(20) NOT NULL, 
    purchase_price FLOAT, 
    acquisition_date DATE, 
    hold_period_years INTEGER NOT NULL, 
    units INTEGER, 
    rentable_sf FLOAT, 
    year_built INTEGER, 
    description TEXT, 
    attributes JSONB NOT NULL, 
    valuation_inputs JSONB NOT NULL, 
    is_demo BOOLEAN NOT NULL, 
    owner_id UUID, 
    created_by UUID, 
    updated_by UUID, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL, 
    FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE, 
    FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE SET NULL, 
    FOREIGN KEY(updated_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_properties_org_id ON properties (org_id);

CREATE INDEX ix_properties_org_status ON properties (org_id, status);

CREATE INDEX ix_properties_org_type ON properties (org_id, property_type);

CREATE TABLE refresh_tokens (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    token_hash VARCHAR(128) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    revoked_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    UNIQUE (token_hash)
);

CREATE INDEX ix_refresh_tokens_user_id ON refresh_tokens (user_id);

CREATE TABLE chat_messages (
    id UUID NOT NULL, 
    org_id UUID NOT NULL, 
    property_id UUID NOT NULL, 
    user_id UUID, 
    role VARCHAR(20) NOT NULL, 
    content TEXT NOT NULL, 
    model VARCHAR(80), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE, 
    FOREIGN KEY(property_id) REFERENCES properties (id) ON DELETE CASCADE, 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_chat_messages_org_id ON chat_messages (org_id);

CREATE INDEX ix_chat_messages_property_id ON chat_messages (property_id);

CREATE TABLE documents (
    id UUID NOT NULL, 
    org_id UUID NOT NULL, 
    property_id UUID NOT NULL, 
    name VARCHAR(300) NOT NULL, 
    type VARCHAR(40) NOT NULL, 
    mime_type VARCHAR(120) NOT NULL, 
    size_bytes INTEGER NOT NULL, 
    sha256 VARCHAR(64) NOT NULL, 
    file_url VARCHAR(500) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    page_count INTEGER, 
    extractor VARCHAR(80), 
    error TEXT, 
    uploaded_by UUID, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE, 
    FOREIGN KEY(property_id) REFERENCES properties (id) ON DELETE CASCADE, 
    FOREIGN KEY(uploaded_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_documents_org_id ON documents (org_id);

CREATE INDEX ix_documents_property_id ON documents (property_id);

CREATE TABLE financing_structures (
    id UUID NOT NULL, 
    org_id UUID NOT NULL, 
    property_id UUID NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    type VARCHAR(40) NOT NULL, 
    rate_type VARCHAR(20) NOT NULL, 
    loan_amount FLOAT, 
    ltv FLOAT, 
    interest_rate FLOAT NOT NULL, 
    index_rate FLOAT NOT NULL, 
    spread FLOAT NOT NULL, 
    term_years INTEGER NOT NULL, 
    amortization_years INTEGER NOT NULL, 
    io_period FLOAT NOT NULL, 
    fees JSONB NOT NULL, 
    covenants JSONB NOT NULL, 
    preferred_equity JSONB, 
    is_active BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE, 
    FOREIGN KEY(property_id) REFERENCES properties (id) ON DELETE CASCADE
);

CREATE INDEX ix_financing_structures_org_id ON financing_structures (org_id);

CREATE INDEX ix_financing_structures_property_id ON financing_structures (property_id);

CREATE TABLE scenarios (
    id UUID NOT NULL, 
    org_id UUID NOT NULL, 
    property_id UUID NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    description TEXT, 
    is_base BOOLEAN NOT NULL, 
    assumptions_json JSONB NOT NULL, 
    created_by UUID, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL, 
    FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE, 
    FOREIGN KEY(property_id) REFERENCES properties (id) ON DELETE CASCADE
);

CREATE INDEX ix_scenarios_org_id ON scenarios (org_id);

CREATE INDEX ix_scenarios_property_id ON scenarios (property_id);

CREATE TABLE document_pages (
    id UUID NOT NULL, 
    org_id UUID NOT NULL, 
    document_id UUID NOT NULL, 
    page_number INTEGER NOT NULL, 
    label VARCHAR(200), 
    text TEXT NOT NULL, 
    width FLOAT, 
    height FLOAT, 
    cells JSONB, 
    PRIMARY KEY (id), 
    FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE, 
    FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE, 
    CONSTRAINT uq_page_doc_number UNIQUE (document_id, page_number)
);

CREATE INDEX ix_document_pages_document_id ON document_pages (document_id);

CREATE INDEX ix_document_pages_org_id ON document_pages (org_id);

CREATE TABLE extracted_data (
    id UUID NOT NULL, 
    org_id UUID NOT NULL, 
    document_id UUID NOT NULL, 
    property_id UUID NOT NULL, 
    field_path VARCHAR(120) NOT NULL, 
    label VARCHAR(200), 
    value JSONB NOT NULL, 
    original_value JSONB NOT NULL, 
    unit VARCHAR(40), 
    confidence FLOAT NOT NULL, 
    source_page INTEGER, 
    source_ref VARCHAR(120), 
    source_excerpt TEXT, 
    source_bbox JSONB, 
    citation_verified BOOLEAN NOT NULL, 
    extractor VARCHAR(80) NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    verified_by UUID, 
    verified_at TIMESTAMP WITH TIME ZONE, 
    version INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(document_id) REFERENCES documents (id) ON DELETE CASCADE, 
    FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE, 
    FOREIGN KEY(property_id) REFERENCES properties (id) ON DELETE CASCADE, 
    FOREIGN KEY(verified_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE INDEX ix_extracted_data_document_id ON extracted_data (document_id);

CREATE INDEX ix_extracted_data_org_id ON extracted_data (org_id);

CREATE INDEX ix_extracted_data_property_id ON extracted_data (property_id);

CREATE INDEX ix_extracted_property_field ON extracted_data (property_id, field_path);

CREATE TABLE underwriting_results (
    id UUID NOT NULL, 
    org_id UUID NOT NULL, 
    property_id UUID NOT NULL, 
    scenario_id UUID NOT NULL, 
    calculated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    calculated_by UUID, 
    engine_version VARCHAR(20) NOT NULL, 
    noi_year1 FLOAT NOT NULL, 
    cap_rate FLOAT NOT NULL, 
    irr_unlevered FLOAT, 
    irr_levered FLOAT, 
    npv FLOAT, 
    equity_multiple FLOAT, 
    cash_on_cash FLOAT, 
    dscr FLOAT, 
    ltv FLOAT, 
    risk_score FLOAT, 
    assumptions_snapshot JSONB NOT NULL, 
    full_cashflow_json JSONB NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(calculated_by) REFERENCES users (id) ON DELETE SET NULL, 
    FOREIGN KEY(org_id) REFERENCES organizations (id) ON DELETE CASCADE, 
    FOREIGN KEY(property_id) REFERENCES properties (id) ON DELETE CASCADE, 
    FOREIGN KEY(scenario_id) REFERENCES scenarios (id) ON DELETE CASCADE
);

CREATE INDEX ix_results_org_irr ON underwriting_results (org_id, irr_levered);

CREATE INDEX ix_results_property_scenario ON underwriting_results (property_id, scenario_id, calculated_at);

CREATE INDEX ix_underwriting_results_org_id ON underwriting_results (org_id);

CREATE INDEX ix_underwriting_results_property_id ON underwriting_results (property_id);

CREATE INDEX ix_underwriting_results_scenario_id ON underwriting_results (scenario_id);

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

-- Running upgrade 0001 -> 0002

ALTER TABLE properties ENABLE ROW LEVEL SECURITY;

ALTER TABLE properties FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON properties USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

ALTER TABLE documents FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON documents USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);

ALTER TABLE document_pages ENABLE ROW LEVEL SECURITY;

ALTER TABLE document_pages FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON document_pages USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);

ALTER TABLE extracted_data ENABLE ROW LEVEL SECURITY;

ALTER TABLE extracted_data FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON extracted_data USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);

ALTER TABLE scenarios ENABLE ROW LEVEL SECURITY;

ALTER TABLE scenarios FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON scenarios USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);

ALTER TABLE underwriting_results ENABLE ROW LEVEL SECURITY;

ALTER TABLE underwriting_results FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON underwriting_results USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);

ALTER TABLE financing_structures ENABLE ROW LEVEL SECURITY;

ALTER TABLE financing_structures FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON financing_structures USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);

ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;

ALTER TABLE chat_messages FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON chat_messages USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);

ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON audit_logs USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);

UPDATE alembic_version SET version_num='0002' WHERE alembic_version.version_num = '0001';

COMMIT;

