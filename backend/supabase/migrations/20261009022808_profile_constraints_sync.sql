-- Module 5 — Schema Reconciliation: profile constraints sync with ERD v1.3.3
--
-- PURPOSE
--   Align the already-applied Module 5 profile migrations with ERD v1.3.3
--   (Issue #23, decision-log #18). The ERD requires two UNIQUE constraints on
--   the existing profile tables that the earlier migrations did not declare.
--   This migration adds them; it contains no other schema change.
--
-- CONSTRAINTS ADDED (both ADDITIVE — no destructive change, no data loss)
--   1. creators_user_id_key UNIQUE (user_id)
--      ERD: creators.user_id is UNIQUE — 1 auth user = at most 1 creator profile.
--      Note: the sibling `merchants` table already has UNIQUE(user_id)
--      (constraint merchants_user_id_key). This brings `creators` in line.
--   2. creator_accounts_id_creator_id_key UNIQUE (id, creator_id)
--      ERD: composite UNIQUE (id, creator_id). Trivially satisfied because `id`
--      is already the primary key, but required because it is the FK target for
--      the future composite FK published_posts.(creator_account_id, creator_id).
--
-- WHY ADDITIVE
--   `creators.user_id` is application-unique today: it is DEFAULT auth.uid() and
--   NOT client-writable (column-level privileges withhold INSERT/UPDATE), so the
--   UNIQUE is a structural invariant, not a behaviour change. The duplicate-check
--   block below fails fast with a clear message if any pre-existing duplicate
--   rows would block the constraint, instead of raising an opaque error.
--   The composite UNIQUE on creator_accounts cannot fail: `id` is the PK.
--
-- SCOPE
--   * No existing migration was modified. Both 20261006020041_creator_network.sql
--     and 20261006052010_merchant_registration.sql are untouched.
--   * No column, trigger, RLS policy or column grant is changed.
--   * Both constraints are declared with ADD CONSTRAINT (never ... NOT VALID),
--     so the verification script can assert convalidated = true.
--
-- REFERENCES: ERD v1.3.3 (docs/specs/erd/erd.dbml, creators + creator_accounts),
--             data-dictionary v1.3.3, Issue #23, decision-log #18.

-- ---------------------------------------------------------------------------
-- CHANGE 1 — creators.user_id UNIQUE
--
-- Fail fast and informatively if duplicate user_id rows already exist; a bare
-- ALTER TABLE would surface only a generic constraint error and leave the
-- operator guessing which rows to fix.
-- ---------------------------------------------------------------------------
do $$
begin
  if exists (
    select 1
      from public.creators
     group by user_id
    having count(*) > 1
  ) then
    raise exception 'Cannot add UNIQUE(creators.user_id): duplicate user_id values exist. Resolve duplicates first.';
  end if;
end
$$;

alter table public.creators
  add constraint creators_user_id_key unique (user_id);

-- ---------------------------------------------------------------------------
-- CHANGE 2 — creator_accounts (id, creator_id) UNIQUE
--
-- FK target for the future composite FK
-- published_posts.(creator_account_id, creator_id). No duplicate check needed:
-- `id` is the primary key, so the pair is unique by construction.
-- ---------------------------------------------------------------------------
alter table public.creator_accounts
  add constraint creator_accounts_id_creator_id_key unique (id, creator_id);