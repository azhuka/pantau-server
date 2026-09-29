-- ============================================================
-- SERVER MONITORING SYSTEM - DATABASE SCHEMA
-- Engine: MariaDB 10.5+
-- Charset: utf8mb4
-- ============================================================

-- ============================================================
-- TABEL: users (admin panel login)
-- ============================================================
CREATE TABLE IF NOT EXISTS users (
    id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(100)  NOT NULL UNIQUE,
    password_hash VARCHAR(255)  NOT NULL,
    role          ENUM('admin', 'viewer') NOT NULL DEFAULT 'admin',
    created_at    TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- ============================================================
-- TABEL: servers
-- ============================================================
CREATE TABLE IF NOT EXISTS servers (
    id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    hostname    VARCHAR(255)  NOT NULL,
    ip_address  VARCHAR(45)   NOT NULL,
    api_key     VARCHAR(64)   NOT NULL UNIQUE,
    is_active   TINYINT(1)    NOT NULL DEFAULT 1,
    last_seen   TIMESTAMP     NULL DEFAULT NULL,
    created_at  TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_servers_api_key (api_key),
    INDEX idx_servers_hostname (hostname)
) ENGINE=InnoDB;

-- ============================================================
-- TABEL: services
-- ============================================================
CREATE TABLE IF NOT EXISTS services (
    id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    server_id     INT UNSIGNED  NOT NULL,
    service_name  VARCHAR(100)  NOT NULL,
    port          INT UNSIGNED  NOT NULL,
    process_name  VARCHAR(100)  NOT NULL,

    FOREIGN KEY (server_id) REFERENCES servers(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    UNIQUE KEY uk_server_service (server_id, service_name),
    INDEX idx_services_port (port)
) ENGINE=InnoDB;

-- ============================================================
-- TABEL: metrics
-- ============================================================
CREATE TABLE IF NOT EXISTS metrics (
    id                BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    service_id        INT UNSIGNED  NOT NULL,
    timestamp         TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status            ENUM('up', 'down') NOT NULL DEFAULT 'down',
    active_connections INT UNSIGNED NOT NULL DEFAULT 0,

    FOREIGN KEY (service_id) REFERENCES services(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    INDEX idx_metrics_service_ts (service_id, timestamp),
    INDEX idx_metrics_timestamp (timestamp)
) ENGINE=InnoDB;
