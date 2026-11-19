-- Module 5 — Merchant Network: merchant registration & profile
--
-- Exposure model: web reads/writes `merchants` directly through the Supabase Data API
-- under RLS. No worker endpoint, no Python models — this is a plain CRUD table.
-- The database contract lives here; the worker HTTP contract is a separate concern
-- (docs/specs/api-contract.md) and is not touched by this task.
--
-- Ownership: 1 auth user = 1 merchant profile, enforced by `user_id` UNIQUE.
-- `user_id` defaults to auth.uid(); the client never writes it. Every policy is
-- scoped to the owner.
--
-- Editable (client-writable) columns: company_name, company_slug, website, logo_url,
-- description, contact_email, country.
--
-- System-managed columns (NOT writable by authenticated): id, user_id, status,
-- created_at, updated_at.
--
-- RLS: owner-only SELECT / INSERT / UPDATE. No DELETE policy -> authenticated
-- delete is blocked.
--
-- Registration flow: authenticated user INSERTs editable fields only; `user_id`
-- is populated by DEFAULT auth.uid(); RLS `WITH CHECK (user_id = auth.uid())`
-- is kept as defense-in-depth; column-level privileges withhold INSERT on user_id.
--
-- Normalization (BEFORE INSERT/UPDATE, canonical values stored in-table):
--   company_name  := btrim(...)                              (required)
--   company_slug  := lower(btrim(...))                       (required)
--   website       := NULLIF(btrim(...), '')                  (optional: '' -> NULL)
--   logo_url      := NULLIF(btrim(...), '')                  (optional: '' -> NULL)
--   description   := NULLIF(btrim(...), '')                  (optional: '' -> NULL)
--   contact_email := NULLIF(lower(btrim(...)), '')           (optional: '' -> NULL)
--   country       := NULLIF(upper(btrim(...)), '')           (optional: '' -> NULL)
-- Required fields are NOT nullif'd: an empty value after btrim must fail their
-- length CHECK. Optional fields treat '', whitespace, and null as equivalent (NULL).
--
-- Slug lifecycle: `company_slug` is editable only while status = 'pending'.
-- Enforced by a BEFORE UPDATE trigger (not RLS), comparing canonical values.
--
-- Strict privileged note: the slug lifecycle invariant applies to ALL roles,
-- including service_role. There is no runtime bypass. A post-activation slug
-- correction is an explicit operational maintenance procedure (e.g. a
-- reviewed one-off migration), not an automatic runtime path.

-- ---------------------------------------------------------------------------
-- Shared helper: keep updated_at current
-- Generic and task-independent; kept `CREATE OR REPLACE` so it does not conflict
-- with the identical helper introduced by the Creator Network migration.
-- ---------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end
$$;

-- ---------------------------------------------------------------------------
-- merchants — a merchant's profile, 1:1 with an auth user
-- ---------------------------------------------------------------------------
create table public.merchants (
  id            uuid primary key default gen_random_uuid(),
  user_id       uuid not null default auth.uid() references auth.users (id) on delete cascade,
  company_name  text not null check (char_length(company_name) between 1 and 200),
  company_slug  text not null check (char_length(company_slug) between 3 and 80 and company_slug ~ '^[a-z0-9-]+$'),
  website       text check (website is null or website ~ '^https?://'),
  logo_url      text check (logo_url is null or logo_url ~ '^https?://'),
  description   text check (description is null or char_length(description) <= 2000),
  contact_email text check (
                  contact_email is null
                  or (
                    contact_email ~ '^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$'
                    and char_length(contact_email) <= 254
                  )
                ),
  country       text check (country is null or country ~ '^[A-Z]{2}$'),
  status        text not null default 'pending'
                check (status in ('pending', 'active', 'suspended')),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),

  constraint merchants_user_id_key      unique (user_id),
  constraint merchants_company_slug_key unique (company_slug)
);

-- Additional index for future admin queries; the two UNIQUE constraints above
-- already provide their own indexes.
create index merchants_status_idx on public.merchants (status);

-- ---------------------------------------------------------------------------
-- Trigger: canonicalize & store normalized values
-- ---------------------------------------------------------------------------
create or replace function public.normalize_merchant()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.company_name    := btrim(new.company_name);
  new.company_slug    := lower(btrim(new.company_slug));
  new.website         := nullif(btrim(new.website), '');
  new.logo_url        := nullif(btrim(new.logo_url), '');
  new.description     := nullif(btrim(new.description), '');
  new.contact_email   := nullif(lower(btrim(new.contact_email)), '');
  new.country         := nullif(upper(btrim(new.country)), '');
  return new;
end
$$;

create trigger merchants_normalize
  before insert or update on public.merchants
  for each row execute function public.normalize_merchant();

-- ---------------------------------------------------------------------------
-- Trigger: slug lifecycle (editable only while pending)
-- Independent of trigger execution order: it computes the canonical incoming
-- slug itself and compares against the already-canonical stored value.
-- ---------------------------------------------------------------------------
create or replace function public.check_merchant_slug_lifecycle()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  canonical_new_slug text := lower(btrim(new.company_slug));
begin
  if old.status <> 'pending'
     and canonical_new_slug is distinct from old.company_slug then
    raise exception 'company_slug cannot be changed once status is %', old.status
      using errcode = 'restrict_violation';
  end if;
  return new;
end
$$;

create trigger merchants_slug_lifecycle
  before update on public.merchants
  for each row execute function public.check_merchant_slug_lifecycle();

-- ---------------------------------------------------------------------------
-- Trigger: updated_at
-- ---------------------------------------------------------------------------
create trigger merchants_set_updated_at
  before update on public.merchants
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Row Level Security
-- RLS decides *which rows* a caller may touch; column-level privileges below
-- decide *which columns*. Both are required: RLS alone would let a merchant
-- rewrite their own `status`, and column grants alone would let them touch any
-- row.
-- ---------------------------------------------------------------------------
alter table public.merchants enable row level security;

create policy "merchants_select_own"
  on public.merchants
  for select
  to authenticated
  using (user_id = (select auth.uid()));

create policy "merchants_insert_own"
  on public.merchants
  for insert
  to authenticated
  with check (user_id = (select auth.uid()));

create policy "merchants_update_own"
  on public.merchants
  for update
  to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

-- No DELETE policy -> authenticated delete is blocked.

-- ---------------------------------------------------------------------------
-- Column-level privileges
-- Supabase grants ALL on new public tables to anon/authenticated/service_role.
-- We narrow that so system columns are not writable through the Data API.
-- `id`, `user_id`, `status`, `created_at`, `updated_at` stay server-managed.
-- `status` defaults to 'pending'; only service_role (which keeps full grants)
-- can change it. `company_slug` remains writable at the privilege layer, but
-- the slug lifecycle trigger rejects changes once status <> 'pending'.
-- Note: service_role bypasses RLS and keeps its full table grants.
-- ---------------------------------------------------------------------------
revoke insert, update, delete on public.merchants from anon, authenticated;
grant select on public.merchants to authenticated;
grant insert (company_name, company_slug, website, logo_url, description, contact_email, country)
  on public.merchants to authenticated;
grant update (company_name, company_slug, website, logo_url, description, contact_email, country)
  on public.merchants to authenticated;