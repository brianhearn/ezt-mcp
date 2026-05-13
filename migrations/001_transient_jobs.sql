-- EZT MCP transient async job control-plane tables.
-- Requires a database owner/admin role. The deployed ezt_mcp_app role is read-only
-- in staging and cannot apply this migration directly.

create schema if not exists transient;

create table if not exists transient.jobs (
  job_id text primary key,
  customer_id uuid not null,
  key_id uuid,
  tool_name text not null,
  status text not null check (status in (
    'queued', 'running', 'input_required', 'awaiting_user_selection',
    'completed', 'failed', 'cancelled', 'expired'
  )),
  phase text not null,
  status_message text,
  progress double precision not null default 0,
  total double precision,
  poll_interval_ms integer not null default 2000 check (poll_interval_ms >= 250),
  priority integer not null default 100,
  idempotency_key text,
  request_summary jsonb not null default '{}'::jsonb,
  result_summary jsonb not null default '{}'::jsonb,
  result_handle text,
  error jsonb,
  cancel_requested boolean not null default false,
  leased_by text,
  lease_expires_at timestamptz,
  created_at timestamptz not null,
  started_at timestamptz,
  last_progress_at timestamptz not null,
  completed_at timestamptz,
  expires_at timestamptz not null
);

create index if not exists idx_transient_jobs_customer_status
  on transient.jobs (customer_id, status, created_at);

create index if not exists idx_transient_jobs_queue_claim
  on transient.jobs (status, priority, created_at)
  where status = 'queued';

create index if not exists idx_transient_jobs_expiry
  on transient.jobs (expires_at);

create unique index if not exists idx_transient_jobs_idempotency
  on transient.jobs (customer_id, tool_name, idempotency_key)
  where idempotency_key is not null;

create table if not exists transient.job_events (
  event_id text primary key,
  job_id text not null references transient.jobs(job_id) on delete cascade,
  customer_id uuid not null,
  sequence integer not null,
  event_type text not null check (event_type in (
    'progress', 'warning', 'phase', 'result', 'error', 'cancel'
  )),
  phase text,
  progress double precision,
  total double precision,
  message text,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null,
  unique (job_id, customer_id, sequence)
);

create index if not exists idx_transient_job_events_job_sequence
  on transient.job_events (customer_id, job_id, sequence);

create table if not exists transient.job_results (
  result_handle text primary key,
  job_id text not null references transient.jobs(job_id) on delete cascade,
  customer_id uuid not null,
  content_type text not null,
  payload_compressed bytea not null,
  payload_bytes integer not null check (payload_bytes >= 0),
  created_at timestamptz not null,
  expires_at timestamptz not null
);

create index if not exists idx_transient_job_results_job
  on transient.job_results (customer_id, job_id);

create index if not exists idx_transient_job_results_expiry
  on transient.job_results (expires_at);
