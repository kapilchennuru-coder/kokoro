-- Outreach: initial PostgreSQL schema (multi-tenant foundation).
-- Run once against a fresh `outreach` database. Idempotent (IF NOT EXISTS
-- everywhere) so it's safe to re-run.

-- ==================== organizations ====================

CREATE TABLE IF NOT EXISTS organizations (
    id              BIGSERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL CHECK (btrim(name) <> ''),
    slug            VARCHAR(100) NOT NULL UNIQUE,
    status          VARCHAR(30) NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'suspended', 'inactive')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ==================== users ====================

CREATE TABLE IF NOT EXISTS users (
    id              BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE RESTRICT,
    username        VARCHAR(150) NOT NULL,
    email           VARCHAR(255),
    first_name      VARCHAR(150),
    last_name       VARCHAR(150),
    client_name     VARCHAR(255) NOT NULL,
    password_hash   TEXT NOT NULL,
    role            VARCHAR(30) NOT NULL DEFAULT 'AGENT'
                        CHECK (role IN ('SUPER_ADMIN', 'ADMIN', 'MANAGER', 'AGENT', 'VIEWER')),
    status          VARCHAR(30) NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'inactive')),
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (organization_id, username)
);

CREATE INDEX IF NOT EXISTS idx_users_organization ON users (organization_id);

-- ==================== contact_lists ====================

CREATE TABLE IF NOT EXISTS contact_lists (
    id              BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    created_by      BIGINT REFERENCES users(id) ON DELETE SET NULL,
    name            VARCHAR(255) NOT NULL,
    filename        VARCHAR(500),
    mapping_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
    row_count       INTEGER NOT NULL DEFAULT 0,
    valid_count     INTEGER NOT NULL DEFAULT 0,
    invalid_count   INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contact_lists_organization ON contact_lists (organization_id);

-- ==================== contacts (patients) ====================

CREATE TABLE IF NOT EXISTS contacts (
    id                  BIGSERIAL PRIMARY KEY,
    organization_id     BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    list_id             BIGINT REFERENCES contact_lists(id) ON DELETE SET NULL,
    name                VARCHAR(255) NOT NULL DEFAULT '',
    first_name          VARCHAR(150),
    last_name           VARCHAR(150),
    phone               VARCHAR(32),          -- normalized E.164 where possible
    email               VARCHAR(255),
    company             VARCHAR(255),
    hospital            VARCHAR(255),
    balance             NUMERIC(12, 2),
    location            VARCHAR(255),
    notes               TEXT,
    extras              JSONB NOT NULL DEFAULT '{}'::jsonb,
    validation_status   VARCHAR(20) NOT NULL DEFAULT 'valid'
                            CHECK (validation_status IN ('valid', 'invalid', 'duplicate')),
    validation_errors   JSONB NOT NULL DEFAULT '[]'::jsonb,
    calling_status      VARCHAR(20) NOT NULL DEFAULT 'not_called'
                            CHECK (calling_status IN
                                ('not_called', 'in_progress', 'completed', 'failed', 'no_answer')),
    last_called_at      TIMESTAMPTZ,
    last_campaign_id    BIGINT,   -- FK added after campaigns exists (below)
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contacts_organization ON contacts (organization_id);
CREATE INDEX IF NOT EXISTS idx_contacts_phone ON contacts (phone);
CREATE INDEX IF NOT EXISTS idx_contacts_created_at ON contacts (created_at);
CREATE INDEX IF NOT EXISTS idx_contacts_list ON contacts (list_id);

-- ==================== campaigns ====================

CREATE TABLE IF NOT EXISTS campaigns (
    id                      BIGSERIAL PRIMARY KEY,
    organization_id         BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    created_by              BIGINT REFERENCES users(id) ON DELETE SET NULL,
    list_id                 BIGINT REFERENCES contact_lists(id) ON DELETE SET NULL,
    name                    VARCHAR(255) NOT NULL,
    status                  VARCHAR(20) NOT NULL DEFAULT 'draft'
                                CHECK (status IN
                                    ('draft', 'ready', 'running', 'paused', 'completed', 'failed')),
    voice_id                VARCHAR(50) NOT NULL DEFAULT 'af_jessica',
    voice_speed             NUMERIC(3, 2) NOT NULL DEFAULT 1.0,
    agent_name              VARCHAR(255) NOT NULL DEFAULT 'Outreach',
    opening_message         TEXT,
    calling_mode            VARCHAR(30) NOT NULL DEFAULT 'sequential',
    max_calls               INTEGER,
    delay_ms                INTEGER NOT NULL DEFAULT 2000,
    concurrency             INTEGER NOT NULL DEFAULT 1,
    total_contacts          INTEGER NOT NULL DEFAULT 0,
    completed_calls         INTEGER NOT NULL DEFAULT 0,
    successful_calls        INTEGER NOT NULL DEFAULT 0,
    no_answer_calls         INTEGER NOT NULL DEFAULT 0,
    busy_calls              INTEGER NOT NULL DEFAULT 0,
    failed_calls            INTEGER NOT NULL DEFAULT 0,
    simulated_calls         INTEGER NOT NULL DEFAULT 0,
    in_progress_calls       INTEGER NOT NULL DEFAULT 0,
    current_contact_id      BIGINT,
    current_call_id         BIGINT,
    agent_state             VARCHAR(30) NOT NULL DEFAULT 'idle',
    error_message           TEXT,
    started_at              TIMESTAMPTZ,
    completed_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_campaigns_organization ON campaigns (organization_id);
CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns (status);
CREATE INDEX IF NOT EXISTS idx_campaigns_created_at ON campaigns (created_at);

ALTER TABLE contacts
    ADD CONSTRAINT fk_contacts_last_campaign
    FOREIGN KEY (last_campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL;

-- ==================== campaign_contacts ====================

CREATE TABLE IF NOT EXISTS campaign_contacts (
    id              BIGSERIAL PRIMARY KEY,
    campaign_id     BIGINT NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    contact_id      BIGINT NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                        CHECK (status IN
                            ('pending', 'in_progress', 'retry_pending', 'completed', 'failed', 'no_answer')),
    call_id         BIGINT,   -- FK added after calls exists (below)
    retry_count     INTEGER NOT NULL DEFAULT 0,
    next_retry_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (campaign_id, contact_id)
);

CREATE INDEX IF NOT EXISTS idx_campaign_contacts_campaign ON campaign_contacts (campaign_id);
CREATE INDEX IF NOT EXISTS idx_campaign_contacts_contact ON campaign_contacts (contact_id);
CREATE INDEX IF NOT EXISTS idx_campaign_contacts_status ON campaign_contacts (status);
CREATE INDEX IF NOT EXISTS idx_campaign_contacts_next_retry ON campaign_contacts (next_retry_at);

-- ==================== calls ====================

CREATE TABLE IF NOT EXISTS calls (
    id                      BIGSERIAL PRIMARY KEY,
    organization_id         BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    campaign_id             BIGINT REFERENCES campaigns(id) ON DELETE SET NULL,
    campaign_contact_id     BIGINT REFERENCES campaign_contacts(id) ON DELETE SET NULL,
    contact_id              BIGINT REFERENCES contacts(id) ON DELETE SET NULL,
    -- Snapshot of the patient at call time - call history must stay
    -- meaningful even after the patient record is edited or deleted later.
    patient_name             VARCHAR(255),
    patient_phone            VARCHAR(32),
    patient_hospital         VARCHAR(255),
    patient_balance          NUMERIC(12, 2),
    provider_call_sid       VARCHAR(64),
    status                  VARCHAR(20) NOT NULL DEFAULT 'in_progress'
                                CHECK (status IN ('in_progress', 'completed', 'failed', 'no_answer')),
    outcome                 VARCHAR(20)
                                CHECK (outcome IS NULL OR outcome IN
                                    ('answered', 'no_answer', 'busy', 'failed', 'invalid_number', 'simulated')),
    duration_sec            INTEGER NOT NULL DEFAULT 0,
    script_text             TEXT,
    transcript              JSONB NOT NULL DEFAULT '[]'::jsonb,
    events                  JSONB NOT NULL DEFAULT '[]'::jsonb,
    detail                  TEXT,
    audio_filename          VARCHAR(255),
    started_at              TIMESTAMPTZ,
    ended_at                TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_calls_organization ON calls (organization_id);
CREATE INDEX IF NOT EXISTS idx_calls_campaign ON calls (campaign_id);
CREATE INDEX IF NOT EXISTS idx_calls_contact ON calls (contact_id);
CREATE INDEX IF NOT EXISTS idx_calls_status ON calls (status);
CREATE INDEX IF NOT EXISTS idx_calls_created_at ON calls (created_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_calls_provider_sid ON calls (provider_call_sid) WHERE provider_call_sid IS NOT NULL;

ALTER TABLE campaign_contacts
    ADD CONSTRAINT fk_campaign_contacts_call
    FOREIGN KEY (call_id) REFERENCES calls(id) ON DELETE SET NULL;

-- ==================== settings ====================
-- Organization-scoped (shared across all users in the org), not per-user -
-- this is a deliberate behavior change from the SQLite version. See the
-- migration doc: sharing calling rules/voice/template org-wide makes sense
-- for a multi-user team, whereas per-user settings didn't.

CREATE TABLE IF NOT EXISTS settings (
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    key             VARCHAR(100) NOT NULL,
    value           TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (organization_id, key)
);

-- ==================== notifications ====================

CREATE TABLE IF NOT EXISTS notifications (
    id              BIGSERIAL PRIMARY KEY,
    organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    message         TEXT NOT NULL,
    level           VARCHAR(20) NOT NULL DEFAULT 'info'
                        CHECK (level IN ('info', 'success', 'warning', 'error')),
    is_read         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    read_at         TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications (user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_is_read ON notifications (is_read);

-- ==================== login_history ====================

CREATE TABLE IF NOT EXISTS login_history (
    id                  BIGSERIAL PRIMARY KEY,
    organization_id     BIGINT REFERENCES organizations(id) ON DELETE SET NULL,
    user_id             BIGINT REFERENCES users(id) ON DELETE SET NULL,
    username_attempted  VARCHAR(150) NOT NULL,
    success             BOOLEAN NOT NULL,
    failure_reason      VARCHAR(100),
    ip_address          VARCHAR(64),
    user_agent          VARCHAR(500),
    login_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    logout_at           TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_login_history_organization ON login_history (organization_id);
CREATE INDEX IF NOT EXISTS idx_login_history_user ON login_history (user_id);
CREATE INDEX IF NOT EXISTS idx_login_history_created_at ON login_history (login_at);

-- ==================== audit_logs ====================

CREATE TABLE IF NOT EXISTS audit_logs (
    id              BIGSERIAL PRIMARY KEY,
    organization_id BIGINT REFERENCES organizations(id) ON DELETE SET NULL,
    user_id         BIGINT REFERENCES users(id) ON DELETE SET NULL,
    username        VARCHAR(150),
    action          VARCHAR(100) NOT NULL,
    resource_type   VARCHAR(50),
    resource_id     BIGINT,
    details         JSONB NOT NULL DEFAULT '{}'::jsonb,
    ip_address      VARCHAR(64),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_organization ON audit_logs (organization_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_user ON audit_logs (user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs (created_at);
