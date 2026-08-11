-- Public marketing site: "Request a Demo" leads. Deliberately NOT scoped to
-- an organization_id - these are prospective customers, not data belonging
-- to an existing tenant.

CREATE TABLE IF NOT EXISTS demo_requests (
    id                      BIGSERIAL PRIMARY KEY,

    first_name              VARCHAR(150) NOT NULL,
    last_name               VARCHAR(150) NOT NULL,
    email                   VARCHAR(255) NOT NULL,
    company_name            VARCHAR(255) NOT NULL,
    job_title               VARCHAR(150),
    country                 VARCHAR(100) NOT NULL,
    phone                   VARCHAR(40) NOT NULL,
    website                 VARCHAR(255),
    industry                VARCHAR(150) NOT NULL,
    company_size            VARCHAR(50),

    address_line1           VARCHAR(255),
    address_line2           VARCHAR(255),
    city                    VARCHAR(150),
    state                   VARCHAR(150),
    postal_code             VARCHAR(30),

    automation_need         TEXT,
    monthly_call_volume     VARCHAR(50),
    current_process         TEXT,
    preferred_demo_date     VARCHAR(20),
    preferred_demo_time     VARCHAR(20),
    timezone                VARCHAR(100),
    message                 TEXT,
    consent                 BOOLEAN NOT NULL DEFAULT FALSE,

    status                  VARCHAR(20) NOT NULL DEFAULT 'NEW'
                                CHECK (status IN ('NEW', 'CONTACTED', 'QUALIFIED', 'DEMO_SCHEDULED', 'CLOSED')),
    notes                   TEXT,

    ip_address              VARCHAR(64),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_demo_requests_status ON demo_requests (status);
CREATE INDEX IF NOT EXISTS idx_demo_requests_created_at ON demo_requests (created_at);
CREATE INDEX IF NOT EXISTS idx_demo_requests_ip ON demo_requests (ip_address);

-- The app connects as a dedicated restricted role (outreach_app, see
-- webapp/.env DATABASE_USER), not the role that runs migrations - a newly
-- created table isn't visible to it without an explicit grant.
GRANT SELECT, INSERT, UPDATE, DELETE ON demo_requests TO outreach_app;
GRANT USAGE, SELECT ON SEQUENCE demo_requests_id_seq TO outreach_app;
