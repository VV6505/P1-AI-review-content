-- P1 pilot (#99) — lưu Product, PKB version, script revision, Job ID, trạng thái/lỗi, n8n execution ID.
--
-- Nguồn thiết kế: ERD v1.3.3 (`docs/specs/erd/erd.dbml`) mục 04 products, 05 product_knowledge, 09 generation_jobs.
-- Khác ERD (có chủ đích, ghi ở decision-log #24 và data-dictionary):
--   1. Thêm `script_revisions`: bản kịch bản M2 theo revision. ERD để `content_scripts`, nhưng bảng đó cần
--      `campaigns` (chưa có migration) nên P1 chưa dùng được. Đây là giải pháp CHUYỂN TIẾP cho pilot P1, chưa mặc định
--      thay `content_scripts` vĩnh viễn. Hướng ánh xạ khi có campaigns: docs/specs/p1-pipeline-db-contract.md mục 6.
--   2. `generation_jobs`: thêm `pkb_version`, `script_revision`, `n8n_execution_id`; thay `content_script_id` bằng
--      `script_revision`. `job_type` giữ 'crawl' | 'video' như ERD.
--   3. `products.affiliate_url` cho phép NULL (ERD: NOT NULL). Pilot PDFCraft không có link affiliate. Khi có giá trị
--      vẫn phải là URL http(s) hợp lệ.
--   4. `idempotency_key` là duy nhất THEO PRODUCT `(product_id, idempotency_key)` ở cả `script_revisions` và
--      `generation_jobs` (ERD: unique toàn bảng ở `generation_jobs`). Retry cùng key trên cùng product không tạo bản trùng;
--      product khác dùng cùng key không xung đột.
--   5. `generation_jobs.render_profile` (nullable, text tự do) để thêm 16:9 / 9:16 hoặc preset sau này mà không đổi
--      index chống chạy trùng. Migration này không quyết cách chia job render.
-- Traceability: Product → PKB version → script revision → n8n execution → generation job.
-- `n8n_execution_id` chỉ để liên kết/tra log; trạng thái nghiệp vụ chuẩn nằm ở các bảng này.
--
-- Quyền: chỉ backend (service_role) ghi. Owner (merchant) chỉ đọc dữ liệu của chính mình qua RLS.
-- Thao tác nhiều bước (cấp version, duyệt) đi qua RPC chỉ cấp cho service_role; FastAPI xác minh JWT rồi truyền `p_actor`.
-- Schema đầy đủ của PKB (`data`, `sources`) và script do worker kiểm bằng JSON Schema; DB chỉ kiểm dạng.

-- ---------------------------------------------------------------------------
-- products
-- ---------------------------------------------------------------------------
create table public.products (
  id                         uuid primary key default gen_random_uuid(),
  merchant_id                uuid not null references public.merchants (id),
  website_url                text not null check (website_url ~ '^https?://' and char_length(website_url) <= 2048),
  affiliate_url              text check (affiliate_url is null or affiliate_url ~ '^https?://'),
  name                       text check (name is null or char_length(btrim(name)) between 1 and 200),
  description                text check (description is null or char_length(description) <= 2000),
  category                   text check (category is null or char_length(category) <= 100),
  merchant_input             jsonb not null default '{}'::jsonb check (jsonb_typeof(merchant_input) = 'object'),
  current_knowledge_version  int check (current_knowledge_version is null or current_knowledge_version > 0),
  status                     text not null default 'draft' check (status in ('draft', 'active', 'archived')),
  created_at                 timestamptz not null default now(),
  updated_at                 timestamptz not null default now(),
  constraint products_website_url_key unique (website_url),
  constraint products_id_merchant_key unique (id, merchant_id)
);
create index products_merchant_id_idx on public.products (merchant_id);

-- ---------------------------------------------------------------------------
-- product_knowledge — PKB theo version (data/sources là JSON, xem docs/specs/pkb/)
-- ---------------------------------------------------------------------------
create table public.product_knowledge (
  product_id     uuid not null references public.products (id),
  version        int  not null check (version > 0),
  status         text not null default 'draft' check (status in ('draft', 'in_review', 'approved', 'rejected')),
  data           jsonb not null check (jsonb_typeof(data) = 'object' and data ->> 'schema_version' in ('0.2', '0.3')),
  sources        jsonb not null check (jsonb_typeof(sources) = 'array'),
  reviewed_by    uuid references auth.users (id),
  reviewed_at    timestamptz,
  reviewer_role  text check (reviewer_role in ('merchant', 'admin')),
  review_note    text check (review_note is null or char_length(review_note) <= 1000),
  created_at     timestamptz not null default now(),
  primary key (product_id, version),
  constraint product_knowledge_review_consistency check (
    (status in ('draft', 'in_review')
       and reviewed_by is null and reviewed_at is null and reviewer_role is null and review_note is null)
    or (status = 'approved'
       and reviewed_by is not null and reviewed_at is not null and reviewer_role = 'merchant')
    or (status = 'rejected'
       and reviewed_by is not null and reviewed_at is not null
       and reviewer_role in ('merchant', 'admin')
       and review_note is not null and char_length(btrim(review_note)) > 0)
  )
);

alter table public.products
  add constraint products_current_knowledge_fkey
  foreign key (id, current_knowledge_version)
  references public.product_knowledge (product_id, version);

-- ---------------------------------------------------------------------------
-- script_revisions — kịch bản M2 theo revision, chỉ sinh từ PKB đã duyệt
-- ---------------------------------------------------------------------------
create table public.script_revisions (
  product_id         uuid not null references public.products (id),
  revision           int  not null check (revision > 0),
  knowledge_version  int  not null,
  parent_revision    int,
  status             text not null default 'draft' check (status in ('draft', 'in_review', 'approved', 'rejected')),
  content            jsonb not null check (jsonb_typeof(content) = 'object'),
  report             jsonb not null default '{}'::jsonb check (jsonb_typeof(report) = 'object'),
  cost_breakdown     jsonb not null default '{}'::jsonb check (jsonb_typeof(cost_breakdown) = 'object'),
  idempotency_key    text not null check (char_length(idempotency_key) between 1 and 200),
  reviewed_by        uuid references auth.users (id),
  reviewed_at        timestamptz,
  review_note        text check (review_note is null or char_length(review_note) <= 1000),
  created_at         timestamptz not null default now(),
  primary key (product_id, revision),
  constraint script_revisions_product_idempotency_key unique (product_id, idempotency_key),
  constraint script_revisions_knowledge_fkey
    foreign key (product_id, knowledge_version) references public.product_knowledge (product_id, version),
  constraint script_revisions_parent_fkey
    foreign key (product_id, parent_revision) references public.script_revisions (product_id, revision),
  constraint script_revisions_parent_older check (parent_revision is null or parent_revision < revision),
  constraint script_revisions_review_consistency check (
    (status in ('draft', 'in_review')
       and reviewed_by is null and reviewed_at is null and review_note is null)
    or (status = 'approved' and reviewed_by is not null and reviewed_at is not null)
    or (status = 'rejected'
       and reviewed_by is not null and reviewed_at is not null
       and review_note is not null and char_length(btrim(review_note)) > 0)
  )
);

-- ---------------------------------------------------------------------------
-- generation_jobs — Job ID cho crawl / video; n8n gọi API theo Job ID
-- ---------------------------------------------------------------------------
create table public.generation_jobs (
  id                uuid primary key default gen_random_uuid(),
  product_id        uuid not null references public.products (id),
  job_type          text not null check (job_type in ('crawl', 'video')),
  status            text not null default 'queued' check (status in ('queued', 'running', 'completed', 'failed')),
  idempotency_key   text not null check (char_length(idempotency_key) between 1 and 200),
  input_snapshot    jsonb not null check (jsonb_typeof(input_snapshot) = 'object'),
  pkb_version       int,
  script_revision   int,
  render_profile    text check (render_profile is null or char_length(render_profile) between 1 and 100),
  n8n_execution_id  text check (n8n_execution_id is null or char_length(n8n_execution_id) between 1 and 100),
  result_manifest   jsonb check (result_manifest is null or jsonb_typeof(result_manifest) = 'object'),
  error             text check (error is null or char_length(error) <= 2000),
  attempts          int not null default 0 check (attempts >= 0),
  tokens_in         int,
  tokens_out        int,
  cost_usd          numeric(12, 6),
  cost_breakdown    jsonb not null default '{}'::jsonb check (jsonb_typeof(cost_breakdown) = 'object'),
  created_at        timestamptz not null default now(),
  finished_at       timestamptz,
  constraint generation_jobs_product_idempotency_key unique (product_id, idempotency_key),
  constraint generation_jobs_pkb_fkey
    foreign key (product_id, pkb_version) references public.product_knowledge (product_id, version),
  constraint generation_jobs_script_fkey
    foreign key (product_id, script_revision) references public.script_revisions (product_id, revision),
  -- crawl: chưa có script; pkb_version chỉ có khi đã tạo PKB. video: bắt buộc cả hai.
  constraint generation_jobs_type_refs check (
    (job_type = 'crawl' and script_revision is null)
    or (job_type = 'video' and pkb_version is not null and script_revision is not null)
  ),
  constraint generation_jobs_failed_has_error check (status <> 'failed' or error is not null),
  constraint generation_jobs_finished_consistency check (
    (status in ('completed', 'failed')) = (finished_at is not null)
  )
);
create index generation_jobs_product_idx on public.generation_jobs (product_id, created_at desc);
create index generation_jobs_status_idx on public.generation_jobs (status) where status in ('queued', 'running');
create index generation_jobs_n8n_execution_idx on public.generation_jobs (n8n_execution_id) where n8n_execution_id is not null;
-- Chạy lại không sinh kết quả trùng: mỗi product tối đa 1 crawl đang chạy; mỗi (revision, render_profile) tối đa 1 video
-- chưa fail (render_profile NULL = mặc định). Chạy lại có chủ đích sau khi fail dùng idempotency_key mới.
create unique index generation_jobs_one_active_crawl on public.generation_jobs (product_id)
  where job_type = 'crawl' and status in ('queued', 'running');
create unique index generation_jobs_one_video_per_revision
  on public.generation_jobs (product_id, script_revision, (coalesce(render_profile, '')))
  where job_type = 'video' and status <> 'failed';

-- ---------------------------------------------------------------------------
-- Trigger: updated_at, bất biến, vòng đời
-- ---------------------------------------------------------------------------
create trigger products_set_updated_at
  before update on public.products
  for each row execute function public.set_updated_at();

create function public.products_guard()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_op = 'UPDATE' and new.merchant_id is distinct from old.merchant_id then
    raise exception 'products.merchant_id is immutable' using errcode = 'restrict_violation';
  end if;
  if new.current_knowledge_version is not null
     and not exists (
       select 1 from public.product_knowledge k
       where k.product_id = new.id and k.version = new.current_knowledge_version and k.status = 'approved'
     ) then
    raise exception 'current_knowledge_version must point to an approved PKB' using errcode = 'check_violation';
  end if;
  if new.status = 'active'
     and (new.name is null or new.current_knowledge_version is null) then
    raise exception 'active product requires name and approved PKB' using errcode = 'check_violation';
  end if;
  return new;
end
$$;
create trigger products_guard
  before insert or update on public.products
  for each row execute function public.products_guard();

-- Dùng chung cho product_knowledge và script_revisions: bản đã duyệt bất biến, vòng đời một chiều.
create function public.review_lifecycle_guard()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_op = 'UPDATE' then
    if old.status = 'approved' then
      raise exception '% is approved and immutable; create a new version', tg_table_name
        using errcode = 'restrict_violation';
    end if;
    if new.status is distinct from old.status
       and not ((old.status, new.status) in
         (('draft', 'in_review'), ('draft', 'rejected'), ('in_review', 'approved'), ('in_review', 'rejected'))) then
      raise exception '% status % -> % is not allowed', tg_table_name, old.status, new.status
        using errcode = 'restrict_violation';
    end if;
    if old.status = 'rejected' then
      raise exception '% is rejected and immutable', tg_table_name using errcode = 'restrict_violation';
    end if;
  end if;
  return new;
end
$$;
create trigger product_knowledge_lifecycle
  before update on public.product_knowledge
  for each row execute function public.review_lifecycle_guard();
create trigger script_revisions_lifecycle
  before update on public.script_revisions
  for each row execute function public.review_lifecycle_guard();

-- Script chỉ sinh từ PKB đã duyệt.
create function public.script_revisions_require_approved_pkb()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if not exists (
    select 1 from public.product_knowledge k
    where k.product_id = new.product_id and k.version = new.knowledge_version and k.status = 'approved'
  ) then
    raise exception 'script revision requires an approved PKB (product %, version %)',
      new.product_id, new.knowledge_version using errcode = 'check_violation';
  end if;
  return new;
end
$$;
create trigger script_revisions_require_approved_pkb
  before insert on public.script_revisions
  for each row execute function public.script_revisions_require_approved_pkb();

-- Job: video chỉ chạy với script đã duyệt và đúng PKB của script; trạng thái cuối bất biến; ghi nhận thời điểm kết thúc.
create function public.generation_jobs_guard()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if tg_op = 'INSERT' and new.job_type = 'video' then
    if not exists (
      select 1 from public.script_revisions s
      where s.product_id = new.product_id and s.revision = new.script_revision
        and s.status = 'approved' and s.knowledge_version = new.pkb_version
    ) then
      raise exception 'video job requires an approved script revision of the same PKB version'
        using errcode = 'check_violation';
    end if;
  end if;
  if tg_op = 'UPDATE' then
    if old.status in ('completed', 'failed') then
      raise exception 'job % is %, state is final', old.id, old.status using errcode = 'restrict_violation';
    end if;
    if new.status is distinct from old.status
       and not ((old.status, new.status) in
         (('queued', 'running'), ('queued', 'failed'), ('running', 'completed'), ('running', 'failed'),
          ('running', 'queued'))) then
      raise exception 'job status % -> % is not allowed', old.status, new.status
        using errcode = 'restrict_violation';
    end if;
    if new.product_id is distinct from old.product_id or new.job_type is distinct from old.job_type
       or new.idempotency_key is distinct from old.idempotency_key
       or new.input_snapshot is distinct from old.input_snapshot
       or new.render_profile is distinct from old.render_profile then
      raise exception 'job identity and input are immutable' using errcode = 'restrict_violation';
    end if;
    if new.status in ('completed', 'failed') and new.finished_at is null then
      new.finished_at := now();
    end if;
  end if;
  return new;
end
$$;
create trigger generation_jobs_guard
  before insert or update on public.generation_jobs
  for each row execute function public.generation_jobs_guard();

-- ---------------------------------------------------------------------------
-- RPC (chỉ service_role). FastAPI đã xác minh JWT và truyền p_actor.
-- ---------------------------------------------------------------------------

-- Cấp PKB version mới trong một giao dịch (khoá dòng product để không trùng version).
create function public.create_pkb_version(p_product_id uuid, p_data jsonb, p_sources jsonb)
returns int
language plpgsql
set search_path = ''
as $$
declare
  v_version int;
begin
  perform 1 from public.products where id = p_product_id for update;
  if not found then
    raise exception 'product % not found', p_product_id using errcode = 'foreign_key_violation';
  end if;
  select coalesce(max(version), 0) + 1 into v_version
    from public.product_knowledge where product_id = p_product_id;
  insert into public.product_knowledge (product_id, version, data, sources)
    values (p_product_id, v_version, p_data, p_sources);
  return v_version;
end
$$;

-- Duyệt PKB: submit (draft → in_review), approve, reject. Chỉ merchant sở hữu product được duyệt.
create function public.review_pkb(
  p_product_id uuid, p_version int, p_actor uuid, p_decision text, p_note text default null
)
returns void
language plpgsql
set search_path = ''
as $$
begin
  if p_decision not in ('submit', 'approve', 'reject') then
    raise exception 'unknown decision %', p_decision using errcode = 'invalid_parameter_value';
  end if;
  if not exists (
    select 1 from public.products p join public.merchants m on m.id = p.merchant_id
    where p.id = p_product_id and m.user_id = p_actor
  ) then
    raise exception 'actor does not own product %', p_product_id using errcode = 'insufficient_privilege';
  end if;
  perform 1 from public.products where id = p_product_id for update;
  if p_decision = 'submit' then
    update public.product_knowledge set status = 'in_review'
      where product_id = p_product_id and version = p_version;
  elsif p_decision = 'approve' then
    update public.product_knowledge
      set status = 'approved', reviewed_by = p_actor, reviewed_at = now(), reviewer_role = 'merchant',
          review_note = nullif(btrim(p_note), '')
      where product_id = p_product_id and version = p_version;
  else
    update public.product_knowledge
      set status = 'rejected', reviewed_by = p_actor, reviewed_at = now(), reviewer_role = 'merchant',
          review_note = p_note
      where product_id = p_product_id and version = p_version;
  end if;
  if not found then
    raise exception 'pkb % v% not found', p_product_id, p_version using errcode = 'no_data_found';
  end if;
  if p_decision = 'approve' then
    update public.products set current_knowledge_version = p_version where id = p_product_id;
  end if;
end
$$;

-- Tạo script revision mới; cùng idempotency_key trả lại revision cũ (n8n retry không sinh bản trùng).
create function public.create_script_revision(
  p_product_id uuid, p_knowledge_version int, p_content jsonb, p_idempotency_key text,
  p_parent_revision int default null, p_report jsonb default '{}'::jsonb,
  p_cost_breakdown jsonb default '{}'::jsonb
)
returns int
language plpgsql
set search_path = ''
as $$
declare
  v_revision int;
begin
  perform 1 from public.products where id = p_product_id for update;
  if not found then
    raise exception 'product % not found', p_product_id using errcode = 'foreign_key_violation';
  end if;
  select revision into v_revision from public.script_revisions
    where idempotency_key = p_idempotency_key and product_id = p_product_id;
  if found then
    return v_revision;
  end if;
  select coalesce(max(revision), 0) + 1 into v_revision
    from public.script_revisions where product_id = p_product_id;
  insert into public.script_revisions
    (product_id, revision, knowledge_version, parent_revision, content, report, cost_breakdown, idempotency_key)
    values (p_product_id, v_revision, p_knowledge_version, p_parent_revision, p_content, p_report,
            p_cost_breakdown, p_idempotency_key);
  return v_revision;
end
$$;

-- Tạo job idempotent: cùng (product_id, idempotency_key) trả lại job cũ, không kiểm lại tham số (n8n retry).
-- Muốn chạy lại có chủ đích (sau khi job fail) phải dùng key mới.
create function public.create_generation_job(
  p_product_id uuid, p_job_type text, p_idempotency_key text, p_input_snapshot jsonb,
  p_pkb_version int default null, p_script_revision int default null,
  p_n8n_execution_id text default null, p_render_profile text default null
)
returns uuid
language plpgsql
set search_path = ''
as $$
declare
  v_id uuid;
begin
  perform 1 from public.products where id = p_product_id for update;
  if not found then
    raise exception 'product % not found', p_product_id using errcode = 'foreign_key_violation';
  end if;
  select id into v_id from public.generation_jobs
    where product_id = p_product_id and idempotency_key = p_idempotency_key;
  if found then
    return v_id;
  end if;
  insert into public.generation_jobs
    (product_id, job_type, idempotency_key, input_snapshot, pkb_version, script_revision,
     n8n_execution_id, render_profile)
    values (p_product_id, p_job_type, p_idempotency_key, p_input_snapshot, p_pkb_version, p_script_revision,
            p_n8n_execution_id, p_render_profile)
    returning id into v_id;
  return v_id;
end
$$;

create function public.review_script_revision(
  p_product_id uuid, p_revision int, p_actor uuid, p_decision text, p_note text default null
)
returns void
language plpgsql
set search_path = ''
as $$
begin
  if p_decision not in ('submit', 'approve', 'reject') then
    raise exception 'unknown decision %', p_decision using errcode = 'invalid_parameter_value';
  end if;
  if not exists (
    select 1 from public.products p join public.merchants m on m.id = p.merchant_id
    where p.id = p_product_id and m.user_id = p_actor
  ) then
    raise exception 'actor does not own product %', p_product_id using errcode = 'insufficient_privilege';
  end if;
  if p_decision = 'submit' then
    update public.script_revisions set status = 'in_review'
      where product_id = p_product_id and revision = p_revision;
  elsif p_decision = 'approve' then
    update public.script_revisions
      set status = 'approved', reviewed_by = p_actor, reviewed_at = now(), review_note = nullif(btrim(p_note), '')
      where product_id = p_product_id and revision = p_revision;
  else
    update public.script_revisions
      set status = 'rejected', reviewed_by = p_actor, reviewed_at = now(), review_note = p_note
      where product_id = p_product_id and revision = p_revision;
  end if;
  if not found then
    raise exception 'script revision % r% not found', p_product_id, p_revision using errcode = 'no_data_found';
  end if;
end
$$;

revoke all on function public.create_pkb_version(uuid, jsonb, jsonb) from public, anon, authenticated;
revoke all on function public.review_pkb(uuid, int, uuid, text, text) from public, anon, authenticated;
revoke all on function public.create_script_revision(uuid, int, jsonb, text, int, jsonb, jsonb) from public, anon, authenticated;
revoke all on function public.review_script_revision(uuid, int, uuid, text, text) from public, anon, authenticated;
revoke all on function public.create_generation_job(uuid, text, text, jsonb, int, int, text, text) from public, anon, authenticated;
grant execute on function public.create_pkb_version(uuid, jsonb, jsonb) to service_role;
grant execute on function public.review_pkb(uuid, int, uuid, text, text) to service_role;
grant execute on function public.create_script_revision(uuid, int, jsonb, text, int, jsonb, jsonb) to service_role;
grant execute on function public.review_script_revision(uuid, int, uuid, text, text) to service_role;
grant execute on function public.create_generation_job(uuid, text, text, jsonb, int, int, text, text) to service_role;

-- ---------------------------------------------------------------------------
-- RLS: owner đọc dữ liệu của mình; không có policy ghi → authenticated không ghi được.
-- ---------------------------------------------------------------------------
alter table public.products          enable row level security;
alter table public.product_knowledge enable row level security;
alter table public.script_revisions  enable row level security;
alter table public.generation_jobs   enable row level security;

revoke all on public.products, public.product_knowledge, public.script_revisions, public.generation_jobs
  from anon, authenticated;
grant select on public.products, public.product_knowledge, public.script_revisions, public.generation_jobs
  to authenticated;
grant all on public.products, public.product_knowledge, public.script_revisions, public.generation_jobs
  to service_role;

create policy products_select_own on public.products
  for select to authenticated
  using (exists (select 1 from public.merchants m where m.id = products.merchant_id and m.user_id = (select auth.uid())));

create policy product_knowledge_select_own on public.product_knowledge
  for select to authenticated
  using (exists (
    select 1 from public.products p join public.merchants m on m.id = p.merchant_id
    where p.id = product_knowledge.product_id and m.user_id = (select auth.uid())));

create policy script_revisions_select_own on public.script_revisions
  for select to authenticated
  using (exists (
    select 1 from public.products p join public.merchants m on m.id = p.merchant_id
    where p.id = script_revisions.product_id and m.user_id = (select auth.uid())));

create policy generation_jobs_select_own on public.generation_jobs
  for select to authenticated
  using (exists (
    select 1 from public.products p join public.merchants m on m.id = p.merchant_id
    where p.id = generation_jobs.product_id and m.user_id = (select auth.uid())));
