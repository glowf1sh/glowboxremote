-- ============================================================================
-- BelaBox Cloud Management - Database Migration
-- Version: 1.0.0
-- Description: Adds BelaBox product and management tables
-- ============================================================================

-- ============================================================================
-- PART 1: Create BelaBox Product
-- ============================================================================

INSERT INTO products (
    id,
    code,
    name,
    description,
    version,
    license_key_pattern,
    default_max_activations,
    default_validity_days,
    features,
    pricing,
    is_active,
    active,
    currency,
    created_at,
    updated_at
) VALUES (
    gen_random_uuid(),
    'GFBLB',
    'Glowf1sh Belabox Remote',
    'Remote Control and Management of a Vanilla Belabox System',
    '1.0.0',
    'GFBLB-{YEAR}-{TYPE}-{WORD}-{BASE32}',
    NULL,  -- Unlimited boxes per license
    365,
    '{
        "remote_control": true,
        "stream_management": true,
        "bitrate_control": true,
        "live_status": true,
        "config_management": true,
        "ssh_access": true,
        "system_updates": true,
        "multi_box_support": true,
        "unlimited_boxes": true
    }'::jsonb,
    '{
        "currency": "EUR",
        "base_plans": [
            {
                "name": "Monthly",
                "interval": "month",
                "price_per_box": 1.39,
                "description": "Monthly subscription per box"
            },
            {
                "name": "Yearly",
                "interval": "year",
                "price_per_box": 12.99,
                "description": "Annual subscription per box"
            }
        ],
        "volume_discounts": [
            {
                "min_boxes": 2,
                "max_boxes": 3,
                "discount_percent": 10,
                "description": "2-3 boxes: 10% discount"
            },
            {
                "min_boxes": 4,
                "max_boxes": 5,
                "discount_percent": 15,
                "description": "4-5 boxes: 15% discount"
            },
            {
                "min_boxes": 6,
                "max_boxes": null,
                "discount_percent": 20,
                "description": "6+ boxes: 20% discount"
            }
        ]
    }'::jsonb,
    true,
    true,
    'EUR',
    now(),
    now()
);

-- ============================================================================
-- PART 2: Create BelaBox Management Tables
-- ============================================================================

-- Table: belaboxes
-- Stores all registered BelaBox devices
CREATE TABLE IF NOT EXISTS belaboxes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    box_id VARCHAR(100) UNIQUE NOT NULL,
    api_key UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    name VARCHAR(255),
    description TEXT,

    -- Ownership & Assignment
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    assigned_user_id UUID REFERENCES admin_users(id) ON DELETE SET NULL,

    -- Status
    is_active BOOLEAN DEFAULT true,
    is_online BOOLEAN DEFAULT false,
    last_seen TIMESTAMPTZ,
    last_ip_address INET,

    -- Remote Management
    remote_mgmt_enabled BOOLEAN DEFAULT true,
    ssh_last_access TIMESTAMPTZ,
    ssh_last_accessed_by UUID REFERENCES admin_users(id),

    -- Hardware & System Info
    hardware_info JSONB DEFAULT '{}'::jsonb,
    system_info JSONB DEFAULT '{}'::jsonb,

    -- Streaming Status (cached from box)
    current_status JSONB DEFAULT '{}'::jsonb,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    created_by UUID REFERENCES admin_users(id),
    updated_by UUID REFERENCES admin_users(id)
);

-- Indexes for belaboxes
CREATE INDEX idx_belaboxes_box_id ON belaboxes(box_id);
CREATE INDEX idx_belaboxes_api_key ON belaboxes(api_key);
CREATE INDEX idx_belaboxes_tenant_id ON belaboxes(tenant_id);
CREATE INDEX idx_belaboxes_assigned_user_id ON belaboxes(assigned_user_id);
CREATE INDEX idx_belaboxes_is_active ON belaboxes(is_active) WHERE is_active = true;
CREATE INDEX idx_belaboxes_is_online ON belaboxes(is_online) WHERE is_online = true;
CREATE INDEX idx_belaboxes_last_seen ON belaboxes(last_seen DESC);

-- Trigger for updated_at
CREATE TRIGGER update_belaboxes_updated_at
    BEFORE UPDATE ON belaboxes
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE belaboxes IS 'Registered BelaBox devices with status and configuration';
COMMENT ON COLUMN belaboxes.box_id IS 'Unique identifier for the box (e.g., belabox-production-1)';
COMMENT ON COLUMN belaboxes.api_key IS 'API key for WebSocket authentication';
COMMENT ON COLUMN belaboxes.remote_mgmt_enabled IS 'Whether SSH remote management is enabled (user-controllable)';
COMMENT ON COLUMN belaboxes.hardware_info IS 'Hardware specs (CPU, RAM, storage, etc.)';
COMMENT ON COLUMN belaboxes.system_info IS 'OS version, installed packages, etc.';
COMMENT ON COLUMN belaboxes.current_status IS 'Last known streaming status (is_streaming, bitrate, etc.)';

-- ============================================================================

-- Table: user_box_assignments
-- Tracks which users have access to which boxes (for multi-user scenarios)
CREATE TABLE IF NOT EXISTS user_box_assignments (
    user_id UUID NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    box_id UUID NOT NULL REFERENCES belaboxes(id) ON DELETE CASCADE,

    -- Assignment Metadata
    assigned_at TIMESTAMPTZ DEFAULT now(),
    assigned_by UUID REFERENCES admin_users(id),

    -- Permissions (for future granular permissions)
    permissions JSONB DEFAULT '{"view": true, "control": true, "configure": true}'::jsonb,

    PRIMARY KEY (user_id, box_id)
);

-- Indexes for user_box_assignments
CREATE INDEX idx_user_box_assignments_user_id ON user_box_assignments(user_id);
CREATE INDEX idx_user_box_assignments_box_id ON user_box_assignments(box_id);

COMMENT ON TABLE user_box_assignments IS 'User-to-BelaBox assignments for access control';
COMMENT ON COLUMN user_box_assignments.permissions IS 'Granular permissions (view, control, configure)';

-- ============================================================================

-- Table: service_api_keys
-- API keys for service-to-service authentication
CREATE TABLE IF NOT EXISTS service_api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_name VARCHAR(100) UNIQUE NOT NULL,
    api_key UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),

    -- Permissions
    permissions JSONB DEFAULT '{}'::jsonb,
    allowed_endpoints TEXT[],

    -- Status
    is_active BOOLEAN DEFAULT true,
    expires_at TIMESTAMPTZ,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    created_by UUID REFERENCES admin_users(id),
    last_used_at TIMESTAMPTZ,
    last_used_from INET
);

-- Indexes for service_api_keys
CREATE INDEX idx_service_api_keys_api_key ON service_api_keys(api_key) WHERE is_active = true;
CREATE INDEX idx_service_api_keys_service_name ON service_api_keys(service_name);
CREATE INDEX idx_service_api_keys_is_active ON service_api_keys(is_active) WHERE is_active = true;

-- Trigger for updated_at
CREATE TRIGGER update_service_api_keys_updated_at
    BEFORE UPDATE ON service_api_keys
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE service_api_keys IS 'API keys for service-to-service authentication (e.g., cloud.gl0w.bot)';
COMMENT ON COLUMN service_api_keys.permissions IS 'JSON object defining service permissions';
COMMENT ON COLUMN service_api_keys.allowed_endpoints IS 'Array of allowed API endpoint patterns';

-- ============================================================================

-- Table: ssh_master_keys
-- Stores SSH master keys for remote management
CREATE TABLE IF NOT EXISTS ssh_master_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key_name VARCHAR(100) UNIQUE NOT NULL,
    public_key TEXT NOT NULL,
    private_key_encrypted TEXT NOT NULL,  -- Encrypted with app secret
    fingerprint VARCHAR(255) NOT NULL,
    key_type VARCHAR(20) DEFAULT 'rsa',
    key_size INTEGER DEFAULT 4096,

    -- Status
    is_active BOOLEAN DEFAULT true,
    is_deployed BOOLEAN DEFAULT false,

    -- Rotation tracking
    replaces_key_id UUID REFERENCES ssh_master_keys(id),
    rotation_initiated_at TIMESTAMPTZ,
    rotation_completed_at TIMESTAMPTZ,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT now(),
    created_by UUID REFERENCES admin_users(id),

    -- Deployment tracking
    deployed_to_boxes INTEGER DEFAULT 0,
    last_deployment_at TIMESTAMPTZ
);

-- Indexes for ssh_master_keys
CREATE INDEX idx_ssh_master_keys_is_active ON ssh_master_keys(is_active) WHERE is_active = true;
CREATE INDEX idx_ssh_master_keys_fingerprint ON ssh_master_keys(fingerprint);

COMMENT ON TABLE ssh_master_keys IS 'SSH master keys for remote management of BelaBoxes';
COMMENT ON COLUMN ssh_master_keys.private_key_encrypted IS 'Encrypted private key (never sent to client)';
COMMENT ON COLUMN ssh_master_keys.is_deployed IS 'Whether key has been deployed to all boxes';
COMMENT ON COLUMN ssh_master_keys.deployed_to_boxes IS 'Count of boxes with this key deployed';

-- ============================================================================

-- Table: box_audit_log
-- Audit trail for all actions on BelaBoxes
CREATE TABLE IF NOT EXISTS box_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    box_id UUID REFERENCES belaboxes(id) ON DELETE SET NULL,

    -- Action details
    action_type VARCHAR(50) NOT NULL,  -- 'start', 'stop', 'config_change', 'ssh_access', etc.
    action_details JSONB DEFAULT '{}'::jsonb,

    -- Actor
    user_id UUID REFERENCES admin_users(id) ON DELETE SET NULL,
    user_email VARCHAR(255),
    user_ip INET,
    user_agent TEXT,

    -- Result
    success BOOLEAN,
    error_message TEXT,

    -- Timestamp
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for box_audit_log
CREATE INDEX idx_box_audit_log_box_id ON box_audit_log(box_id);
CREATE INDEX idx_box_audit_log_user_id ON box_audit_log(user_id);
CREATE INDEX idx_box_audit_log_action_type ON box_audit_log(action_type);
CREATE INDEX idx_box_audit_log_created_at ON box_audit_log(created_at DESC);
CREATE INDEX idx_box_audit_log_box_created ON box_audit_log(box_id, created_at DESC);

COMMENT ON TABLE box_audit_log IS 'Audit trail for all BelaBox actions';
COMMENT ON COLUMN box_audit_log.action_type IS 'Type of action performed';
COMMENT ON COLUMN box_audit_log.action_details IS 'JSON details of the action';

-- ============================================================================
-- PART 3: Insert Initial Data
-- ============================================================================

-- Insert service API key for cloud.gl0w.bot
INSERT INTO service_api_keys (
    service_name,
    api_key,
    permissions,
    allowed_endpoints,
    is_active
) VALUES (
    'cloud.gl0w.bot',
    gen_random_uuid(),
    '{
        "verify_user": true,
        "check_permission": true,
        "get_user_boxes": true,
        "update_box_status": true,
        "get_ssh_key": true,
        "audit_log": true
    }'::jsonb,
    ARRAY[
        '/api/service/verify-user',
        '/api/service/check-permission',
        '/api/service/user-boxes/*',
        '/api/service/box-status-update',
        '/api/service/get-ssh-key',
        '/api/service/calculate-price/*'
    ],
    true
) ON CONFLICT (service_name) DO NOTHING;

-- Insert existing BelaBox (belabox-production-1) with current API key
INSERT INTO belaboxes (
    box_id,
    api_key,
    name,
    description,
    is_active,
    is_online,
    remote_mgmt_enabled
) VALUES (
    'belabox-production-1',
    '5ac6bd8f-af9e-4d05-816d-86540937f958'::uuid,
    'BelaBox Production 1',
    'Primary production BelaBox',
    true,
    false,  -- Will be updated by WebSocket
    true
) ON CONFLICT (box_id) DO NOTHING;

-- ============================================================================
-- PART 4: Grant Permissions
-- ============================================================================

-- Grant permissions to license_user (application user)
GRANT SELECT, INSERT, UPDATE, DELETE ON belaboxes TO license_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON user_box_assignments TO license_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON service_api_keys TO license_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ssh_master_keys TO license_user;
GRANT SELECT, INSERT ON box_audit_log TO license_user;

-- Grant sequence usage
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO license_user;

-- ============================================================================
-- PART 5: Helper Functions
-- ============================================================================

-- Function: Calculate pricing for a user based on number of boxes
CREATE OR REPLACE FUNCTION calculate_belabox_pricing(
    p_user_id UUID,
    p_interval VARCHAR DEFAULT 'month'
)
RETURNS TABLE (
    num_boxes INTEGER,
    interval VARCHAR,
    base_price_per_box NUMERIC,
    discount_percent INTEGER,
    price_per_box NUMERIC,
    total_price NUMERIC
) AS $$
DECLARE
    v_num_boxes INTEGER;
    v_base_price NUMERIC;
    v_discount INTEGER := 0;
BEGIN
    -- Count user's boxes
    SELECT COUNT(*) INTO v_num_boxes
    FROM user_box_assignments uba
    JOIN belaboxes b ON uba.box_id = b.id
    WHERE uba.user_id = p_user_id
      AND b.is_active = true;

    -- Get base price from product
    IF p_interval = 'year' THEN
        v_base_price := 12.99;
    ELSE
        v_base_price := 1.39;
    END IF;

    -- Calculate volume discount
    IF v_num_boxes >= 6 THEN
        v_discount := 20;
    ELSIF v_num_boxes >= 4 THEN
        v_discount := 15;
    ELSIF v_num_boxes >= 2 THEN
        v_discount := 10;
    END IF;

    -- Return calculated pricing
    RETURN QUERY SELECT
        v_num_boxes,
        p_interval,
        v_base_price,
        v_discount,
        ROUND(v_base_price * (1 - v_discount::NUMERIC / 100), 2),
        ROUND(v_base_price * (1 - v_discount::NUMERIC / 100) * v_num_boxes, 2);
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION calculate_belabox_pricing IS 'Calculate pricing with volume discounts for a user';

-- ============================================================================

-- Function: Update box online status
CREATE OR REPLACE FUNCTION update_box_status(
    p_box_id VARCHAR,
    p_is_online BOOLEAN,
    p_status_data JSONB DEFAULT NULL,
    p_ip_address INET DEFAULT NULL
)
RETURNS VOID AS $$
BEGIN
    UPDATE belaboxes
    SET
        is_online = p_is_online,
        last_seen = CASE WHEN p_is_online THEN now() ELSE last_seen END,
        current_status = COALESCE(p_status_data, current_status),
        last_ip_address = COALESCE(p_ip_address, last_ip_address),
        updated_at = now()
    WHERE box_id = p_box_id;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION update_box_status IS 'Update BelaBox online status and cached data';

-- ============================================================================
-- MIGRATION COMPLETE
-- ============================================================================

-- Display service API key for cloud.gl0w.bot
SELECT
    'Service API Key for cloud.gl0w.bot:' AS info,
    api_key::TEXT AS api_key
FROM service_api_keys
WHERE service_name = 'cloud.gl0w.bot';

-- Display summary
SELECT
    'Migration completed successfully!' AS status,
    (SELECT COUNT(*) FROM belaboxes) AS total_boxes,
    (SELECT COUNT(*) FROM service_api_keys WHERE is_active = true) AS active_service_keys;
