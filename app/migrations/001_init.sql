CREATE TABLE IF NOT EXISTS configurations (
  id SERIAL PRIMARY KEY,
  service TEXT NOT NULL,
  version INTEGER NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_configurations_service_version
  ON configurations(service, version);

CREATE INDEX IF NOT EXISTS ix_configurations_service_created_at
  ON configurations(service, created_at DESC);
