-- Module 5 — Creator Network: creator registration & profile
--
-- Exposure model: web reads/writes `creators` / `creator_accounts` directly through the
-- Supabase Data API under RLS (see docs/specs/api-contract.md). No worker endpoint, no
-- Python models — these are plain CRUD tables.
--
-- Ownership rule: `creators.user_id` is DEFAULT auth.uid() — the client never writes it.
-- Every policy is scoped to the owner.
--
-- Decisions baked in (per task review):
--   * SELECT / INSERT / UPDATE only — authenticated DELETE is intentionally NOT exposed.
--   * `creators.user_id` defaults to auth.uid(); NOT NULL. Client sends only editable
--     profile fields. RLS `WITH CHECK (user_id = auth.uid())` kept as defense-in-depth.
--   * `creator_accounts.creator_id` is derived in a BEFORE INSERT trigger from the caller's
--     auth identity (resolve creators.id by user_id). Client never writes creator_id.
--     RLS `WITH CHECK EXISTS (...)` kept as defense-in-depth.
--   * System / ownership columns (id, user_id, creator_id, timestamps, status) are made
--     non-writable by column-level privileges, not just by RLS.
--   * `status` is platform-managed (service_role); a creator cannot self-activate.
--   * No `is_verified` column — no verification workflow exists in this task.
--   * `creator_accounts.platform` and `.handle` are stored canonicalized (lowercased, trimmed,
--     leading `@` stripped) by BEFORE INSERT/UPDATE triggers, and `platform_handle` is a
--     generated, globally unique key derived from those canonical values. One social handle
--     on one platform cannot be claimed by two creators. This is normalization for uniqueness,
--     not proof of ownership.

-- ---------------------------------------------------------------------------
-- Shared helper: keep updated_at current
-- ---------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at := now();
  return new;
end;
$$;

-- ---------------------------------------------------------------------------
-- creators — the creator's profile, 1:1 with an auth user
-- ---------------------------------------------------------------------------
create table public.creators (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null default auth.uid() references auth.users (id) on delete cascade,
  display_name text not null check (char_length(display_name) between 1 and 100),
  bio          text check (bio is null or char_length(bio) <= 2000),
  niche        text check (niche is null or char_length(niche) <= 50),
  language     text check (language is null or char_length(language) <= 16),  -- BCP-47, e.g. en, en-US, vi
  country      text check (country is null or char_length(country) = 2),      -- ISO 3166-1 alpha-2
  avatar_url   text check (avatar_url is null or avatar_url ~ '^https?://'),
  status       text not null default 'pending'
               check (status in ('pending', 'active', 'suspended')),
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create trigger creators_set_updated_at
  before update on public.creators
  for each row
  execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- creator_accounts — a creator's social accounts (one row per platform handle)
--
-- `platform` and `handle` are stored canonicalized by triggers below (platform lowercased+
-- trimmed; handle lowercased, trimmed, leading '@' stripped). `platform_handle` is generated
-- from those canonical values and unique: the same social account cannot belong to two
-- creators. It is `generated always ... stored`, so it can never be written directly.
-- ---------------------------------------------------------------------------
create table public.creator_accounts (
  id              uuid primary key default gen_random_uuid(),
  creator_id      uuid not null references public.creators (id) on delete cascade,
  platform        text not null check (char_length(platform) between 1 and 30),
  handle          text not null check (char_length(handle) between 1 and 50),
  platform_handle text generated always as (platform || ':' || handle) stored,
  url             text check (url is null or url ~ '^https?://'),
  follower_count  bigint not null default 0 check (follower_count >= 0),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),

  -- Global uniqueness on the canonical key. The old (creator_id, platform, handle) composite
  -- unique is intentionally dropped — the normalized global key is sufficient for this task.
  constraint creator_accounts_platform_handle_key unique (platform_handle)
);

-- The platform_handle unique index also serves the RLS ownership lookup only indirectly;
-- RLS resolves ownership via creators.user_id, not via this index.

create trigger creator_accounts_set_updated_at
  before update on public.creator_accounts
  for each row
  execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- BEFORE INSERT: derive creator_id from the authenticated user
--
-- Flow: auth.uid() -> creators.user_id -> creators.id -> NEW.creator_id.
-- If the caller has no creator profile, raise a clear error.
--
-- Privileged path: an explicit NEW.creator_id is trusted and left untouched. Only
-- roles holding INSERT privilege on the creator_id column can set it, and that grant is
-- withheld from `authenticated` (see column-level privileges below). So this branch is
-- reachable by service_role/admin only, and the FK still enforces that the creator exists.
-- The authenticated path (creator_id not writable -> NEW.creator_id is NULL) always derives
-- from auth.uid(); RLS `WITH CHECK EXISTS (...)` is the second line of defence.
-- ---------------------------------------------------------------------------
create or replace function public.set_creator_id_from_auth()
returns trigger
language plpgsql
set search_path = ''
as $$
declare
  v_creator_id uuid;
begin
  -- Privileged call supplying an explicit owner: respect it.
  if new.creator_id is not null then
    return new;
  end if;

  -- Authenticated call: resolve the caller's own creator profile.
  select c.id into v_creator_id
    from public.creators c
   where c.user_id = auth.uid();

  if v_creator_id is null then
    raise exception 'creator profile not found for authenticated user'
      using errcode = 'no_data_found';
  end if;

  new.creator_id := v_creator_id;
  return new;
end;
$$;

create trigger creator_accounts_set_creator_id_from_auth
  before insert on public.creator_accounts
  for each row
  execute function public.set_creator_id_from_auth();

-- ---------------------------------------------------------------------------
-- Canonicalization triggers for creator_accounts (store canonical values)
-- ---------------------------------------------------------------------------
create or replace function public.normalize_creator_account()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.platform := lower(btrim(new.platform));
  new.handle   := ltrim(lower(btrim(new.handle)), '@');
  return new;
end;
$$;

create trigger creator_accounts_normalize
  before insert or update on public.creator_accounts
  for each row
  execute function public.normalize_creator_account();

-- ---------------------------------------------------------------------------
-- Row Level Security
--
-- RLS decides *which rows* a caller may touch; column-level privileges below decide
-- *which columns*. Both are required: RLS alone would let a creator rewrite their own
-- `status`, and column grants alone would let them touch any row.
-- ---------------------------------------------------------------------------
alter table public.creators         enable row level security;
alter table public.creator_accounts enable row level security;

-- creators: owner may SELECT / INSERT / UPDATE own row. No DELETE policy -> denied.
create policy "creators_select_own"
  on public.creators
  for select
  to authenticated
  using (user_id = (select auth.uid()));

-- user_id is populated by DEFAULT auth.uid(); WITH CHECK keeps that invariant as
-- defense-in-depth in case a future default is removed or the column is written.
create policy "creators_insert_own"
  on public.creators
  for insert
  to authenticated
  with check (user_id = (select auth.uid()));

create policy "creators_update_own"
  on public.creators
  for update
  to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

-- creator_accounts: scoped to accounts owned by the caller's own creator profile.
-- creator_id is derived server-side (trigger), not client-written; the EXISTS checks
-- remain defense-in-depth against any path that could try to set creator_id explicitly.
create policy "creator_accounts_select_own"
  on public.creator_accounts
  for select
  to authenticated
  using (
    exists (
      select 1 from public.creators c
      where c.id = creator_id and c.user_id = (select auth.uid())
    )
  );

create policy "creator_accounts_insert_own"
  on public.creator_accounts
  for insert
  to authenticated
  with check (
    exists (
      select 1 from public.creators c
      where c.id = creator_id and c.user_id = (select auth.uid())
    )
  );

create policy "creator_accounts_update_own"
  on public.creator_accounts
  for update
  to authenticated
  using (
    exists (
      select 1 from public.creators c
      where c.id = creator_id and c.user_id = (select auth.uid())
    )
  )
  with check (
    exists (
      select 1 from public.creators c
      where c.id = creator_id and c.user_id = (select auth.uid())
    )
  );

-- ---------------------------------------------------------------------------
-- Column-level privileges
--
-- Supabase grants ALL on new public tables to anon/authenticated/service_role. We narrow
-- that so system columns are simply not writable through the Data API:
--   * creators: a creator may insert/update only profile columns. `user_id`, `status`,
--     `id`, `created_at`, `updated_at` stay server-managed. `status` defaults to 'pending';
--     only service_role (which keeps full grants) can change it.
--   * creator_accounts: `creator_id` (insert AND update), `platform_handle`, `id`, and
--     timestamps stay server-managed. `platform_handle` is generated and can never be
--     written anyway. `platform` and `handle` are stored canonicalized by the
--     BEFORE INSERT/UPDATE trigger; updating either recomputes `platform_handle`.
--
-- Note: service_role bypasses RLS and keeps its full table grants, so platform/admin
-- tooling can still manage `status` and any other column.
-- ---------------------------------------------------------------------------
revoke insert, update, delete on public.creators from anon, authenticated;
grant select on public.creators to authenticated;
grant insert (display_name, bio, niche, language, country, avatar_url)
  on public.creators to authenticated;
grant update (display_name, bio, niche, language, country, avatar_url)
  on public.creators to authenticated;

revoke insert, update, delete on public.creator_accounts from anon, authenticated;
grant select on public.creator_accounts to authenticated;
grant insert (platform, handle, url, follower_count)
  on public.creator_accounts to authenticated;
grant update (platform, handle, url, follower_count)
  on public.creator_accounts to authenticated;
