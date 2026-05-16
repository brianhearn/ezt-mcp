-- EZT MCP transient job payload hardening.
-- Requires a database owner/admin role. The deployed ezt_mcp_app role is read-only
-- in staging and cannot apply this migration directly.

create table if not exists transient.job_payloads (
  payload_handle text primary key,
  job_id text not null references transient.jobs(job_id) on delete cascade,
  customer_id uuid not null,
  content_type text not null default 'application/json',
  payload_compressed bytea not null,
  payload_bytes integer not null check (payload_bytes >= 0),
  created_at timestamptz not null,
  expires_at timestamptz not null
);

create index if not exists idx_transient_job_payloads_job
  on transient.job_payloads (customer_id, job_id);

create index if not exists idx_transient_job_payloads_expiry
  on transient.job_payloads (expires_at);

alter table transient.jobs
  add column if not exists attempt_count integer not null default 0,
  add column if not exists max_attempts integer not null default 3,
  add column if not exists next_attempt_at timestamptz,
  add column if not exists payload_handle text;

create index if not exists idx_transient_jobs_running_reclaim
  on transient.jobs (status, lease_expires_at, next_attempt_at)
  where status = 'running';

create index if not exists idx_transient_jobs_customer_active
  on transient.jobs (customer_id, status, created_at)
  where status in ('queued', 'running', 'input_required', 'awaiting_user_selection');

grant select, insert, update, delete on transient.job_payloads to ezt_mcp_app;
