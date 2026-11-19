-- Test cho migration 20261117020000_p1_pipeline_persistence.sql. Chạy sau khi áp mọi migration.
-- Mỗi khối `expect_error` phải bị DB từ chối đúng lý do; cuối file in ALL OK.
begin;

create function pg_temp.expect_error(p_sql text, p_like text) returns void language plpgsql as $$
begin
  execute p_sql;
  raise exception 'EXPECTED ERROR LIKE %, BUT SUCCEEDED: %', p_like, p_sql;
exception when others then
  if sqlerrm like 'EXPECTED ERROR LIKE%' then raise; end if;
  if sqlerrm not like p_like then
    raise exception 'wrong error for %: got [%], wanted like [%]', p_sql, sqlerrm, p_like;
  end if;
end $$;

-- Dữ liệu nền
insert into auth.users (id, email) values
  ('00000000-0000-4000-8000-0000000000a1', 'owner@example.com'),
  ('00000000-0000-4000-8000-0000000000a2', 'other@example.com');
insert into public.merchants (id, user_id, company_name, company_slug) values
  ('00000000-0000-4000-8000-0000000000b1', '00000000-0000-4000-8000-0000000000a1', 'Owner Co', 'owner-co'),
  ('00000000-0000-4000-8000-0000000000b2', '00000000-0000-4000-8000-0000000000a2', 'Other Co', 'other-co');
insert into public.products (id, merchant_id, website_url, name) values
  ('00000000-0000-4000-8000-0000000000c1', '00000000-0000-4000-8000-0000000000b1',
   'https://pdfcraft.devtoolcafe.com/', 'PDFCraft');

-- 1. Cấp PKB version tuần tự 1, 2
select public.create_pkb_version('00000000-0000-4000-8000-0000000000c1', '{"schema_version":"0.3"}', '[]');
do $$ begin
  assert public.create_pkb_version('00000000-0000-4000-8000-0000000000c1', '{"schema_version":"0.3"}', '[]') = 2,
    'version phải tăng dần';
end $$;
select pg_temp.expect_error($$select public.create_pkb_version('00000000-0000-4000-8000-0000000000c1', '{"schema_version":"9"}', '[]')$$, '%check%');

-- 2. Script không sinh được từ PKB chưa duyệt
select pg_temp.expect_error($$select public.create_script_revision('00000000-0000-4000-8000-0000000000c1', 1, '{}', 'k-r1')$$, '%requires an approved PKB%');

-- 3. Người không sở hữu không duyệt được
select pg_temp.expect_error($$select public.review_pkb('00000000-0000-4000-8000-0000000000c1', 1, '00000000-0000-4000-8000-0000000000a2', 'approve')$$, '%does not own%');
-- 4. Không nhảy draft -> approved
select pg_temp.expect_error($$select public.review_pkb('00000000-0000-4000-8000-0000000000c1', 1, '00000000-0000-4000-8000-0000000000a1', 'approve')$$, '%not allowed%');

-- 5. Duyệt PKB v1 (điểm duyệt 1)
select public.review_pkb('00000000-0000-4000-8000-0000000000c1', 1, '00000000-0000-4000-8000-0000000000a1', 'submit');
select public.review_pkb('00000000-0000-4000-8000-0000000000c1', 1, '00000000-0000-4000-8000-0000000000a1', 'approve', 'ok');
do $$ begin
  assert (select current_knowledge_version from public.products where name = 'PDFCraft') = 1, 'pointer phải trỏ v1';
  assert (select reviewer_role from public.product_knowledge where version = 1) = 'merchant';
end $$;
-- PKB đã duyệt bất biến
select pg_temp.expect_error($$update public.product_knowledge set data = '{"schema_version":"0.3","x":1}' where version = 1$$, '%immutable%');
-- Pointer không trỏ tới PKB chưa duyệt (v2 còn draft)
select pg_temp.expect_error($$update public.products set current_knowledge_version = 2$$, '%approved PKB%');
-- Reject phải có lý do
select public.review_pkb('00000000-0000-4000-8000-0000000000c1', 2, '00000000-0000-4000-8000-0000000000a1', 'submit');
select pg_temp.expect_error($$select public.review_pkb('00000000-0000-4000-8000-0000000000c1', 2, '00000000-0000-4000-8000-0000000000a1', 'reject', '  ')$$, '%check%');

-- 6. Script revision idempotent
do $$ declare r1 int; r2 int; r3 int; begin
  r1 := public.create_script_revision('00000000-0000-4000-8000-0000000000c1', 1, '{"scenes":[]}', 'run1:script');
  r2 := public.create_script_revision('00000000-0000-4000-8000-0000000000c1', 1, '{"scenes":[]}', 'run1:script');
  assert r1 = 1 and r2 = 1, 'cùng idempotency_key phải trả revision cũ';
  r3 := public.create_script_revision('00000000-0000-4000-8000-0000000000c1', 1, '{"scenes":["x"]}', 'run1:script-2', 1);
  assert r3 = 2, 'revision mới tăng dần';
end $$;

-- 7. Video job cần script đã duyệt
select pg_temp.expect_error($$insert into public.generation_jobs (product_id, job_type, idempotency_key, input_snapshot, pkb_version, script_revision)
  values ('00000000-0000-4000-8000-0000000000c1', 'video', 'v-1', '{}', 1, 1)$$, '%approved script revision%');
select public.review_script_revision('00000000-0000-4000-8000-0000000000c1', 2, '00000000-0000-4000-8000-0000000000a1', 'submit');
select public.review_script_revision('00000000-0000-4000-8000-0000000000c1', 2, '00000000-0000-4000-8000-0000000000a1', 'approve');
select pg_temp.expect_error($$update public.script_revisions set content = '{}' where revision = 2$$, '%immutable%');

-- 8. Video job: ghi n8n execution ID, vòng đời, bất biến, chống chạy trùng
insert into public.generation_jobs (id, product_id, job_type, idempotency_key, input_snapshot, pkb_version, script_revision, n8n_execution_id)
  values ('00000000-0000-4000-8000-0000000000d1', '00000000-0000-4000-8000-0000000000c1', 'video', 'v-2', '{"aspect":"16:9"}', 1, 2, '12345');
select pg_temp.expect_error($$insert into public.generation_jobs (product_id, job_type, idempotency_key, input_snapshot, pkb_version, script_revision)
  values ('00000000-0000-4000-8000-0000000000c1', 'video', 'v-3', '{}', 1, 2)$$, '%one_video_per_revision%');
select pg_temp.expect_error($$insert into public.generation_jobs (product_id, job_type, idempotency_key, input_snapshot, pkb_version, script_revision)
  values ('00000000-0000-4000-8000-0000000000c1', 'video', 'v-2', '{}', 1, 2)$$, '%product_idempotency_key%');
select pg_temp.expect_error($$update public.generation_jobs set status = 'completed' where id = '00000000-0000-4000-8000-0000000000d1'$$, '%not allowed%');
update public.generation_jobs set status = 'running', attempts = 1 where id = '00000000-0000-4000-8000-0000000000d1';
select pg_temp.expect_error($$update public.generation_jobs set status = 'failed' where id = '00000000-0000-4000-8000-0000000000d1'$$, '%failed_has_error%');
update public.generation_jobs set status = 'failed', error = 'tts_unavailable' where id = '00000000-0000-4000-8000-0000000000d1';
do $$ begin assert (select finished_at from public.generation_jobs where id = '00000000-0000-4000-8000-0000000000d1') is not null; end $$;
select pg_temp.expect_error($$update public.generation_jobs set error = 'x' where id = '00000000-0000-4000-8000-0000000000d1'$$, '%final%');
-- Sau khi fail, chạy lại bằng key mới được phép
insert into public.generation_jobs (product_id, job_type, idempotency_key, input_snapshot, pkb_version, script_revision, n8n_execution_id)
  values ('00000000-0000-4000-8000-0000000000c1', 'video', 'v-4', '{}', 1, 2, '12346');

-- 8b. render_profile: cùng revision, khác profile thì được thêm video job; trùng profile thì không
select pg_temp.expect_error($$insert into public.generation_jobs (product_id, job_type, idempotency_key, input_snapshot, pkb_version, script_revision)
  values ('00000000-0000-4000-8000-0000000000c1', 'video', 'v-5', '{}', 1, 2)$$, '%one_video_per_revision%');
insert into public.generation_jobs (product_id, job_type, idempotency_key, input_snapshot, pkb_version, script_revision, render_profile)
  values ('00000000-0000-4000-8000-0000000000c1', 'video', 'v-6', '{}', 1, 2, '9:16');
select pg_temp.expect_error($$insert into public.generation_jobs (product_id, job_type, idempotency_key, input_snapshot, pkb_version, script_revision, render_profile)
  values ('00000000-0000-4000-8000-0000000000c1', 'video', 'v-7', '{}', 1, 2, '9:16')$$, '%one_video_per_revision%');
select pg_temp.expect_error($$update public.generation_jobs set render_profile = '1:1' where idempotency_key = 'v-6'$$, '%immutable%');

-- 8c. create_generation_job idempotent theo (product_id, key); key trùng ở product khác không xung đột
do $$ declare j1 uuid; j2 uuid; j3 uuid; begin
  j1 := public.create_generation_job('00000000-0000-4000-8000-0000000000c1', 'crawl', 'n8n-77:crawl', '{"u":1}');
  j2 := public.create_generation_job('00000000-0000-4000-8000-0000000000c1', 'crawl', 'n8n-77:crawl', '{"u":2}');
  assert j1 = j2, 'retry cùng key phải trả job cũ';
  assert (select count(*) from public.generation_jobs where idempotency_key = 'n8n-77:crawl') = 1;
  insert into public.products (id, merchant_id, website_url) values
    ('00000000-0000-4000-8000-0000000000c2', '00000000-0000-4000-8000-0000000000b2', 'https://example.org/');
  j3 := public.create_generation_job('00000000-0000-4000-8000-0000000000c2', 'crawl', 'n8n-77:crawl', '{}');
  assert j3 <> j1, 'product khác, cùng key: job riêng';
end $$;
-- crawl job của c1 vừa tạo (n8n-77) đang queued: giải phóng cho test mục 9
update public.generation_jobs set status = 'failed', error = 'test cleanup' where idempotency_key = 'n8n-77:crawl' and product_id = '00000000-0000-4000-8000-0000000000c1';
-- Script idempotency cũng theo product
select public.create_pkb_version('00000000-0000-4000-8000-0000000000c2', '{"schema_version":"0.3"}', '[]');
select public.review_pkb('00000000-0000-4000-8000-0000000000c2', 1, '00000000-0000-4000-8000-0000000000a2', 'submit');
select public.review_pkb('00000000-0000-4000-8000-0000000000c2', 1, '00000000-0000-4000-8000-0000000000a2', 'approve');
do $$ begin
  assert public.create_script_revision('00000000-0000-4000-8000-0000000000c2', 1, '{}', 'run1:script') = 1,
    'cùng key ở product khác phải tạo revision riêng';
end $$;

-- 8d. affiliate_url: NULL được; có giá trị thì phải là URL http(s)
do $$ begin assert (select affiliate_url from public.products where id = '00000000-0000-4000-8000-0000000000c1') is null; end $$;
select pg_temp.expect_error($$update public.products set affiliate_url = 'not-a-url' where id = '00000000-0000-4000-8000-0000000000c1'$$, '%check%');
update public.products set affiliate_url = 'https://example.com/go' where id = '00000000-0000-4000-8000-0000000000c1';
update public.products set affiliate_url = null where id = '00000000-0000-4000-8000-0000000000c1';

-- 9. Crawl: chỉ một job đang chạy mỗi product
insert into public.generation_jobs (product_id, job_type, idempotency_key, input_snapshot)
  values ('00000000-0000-4000-8000-0000000000c1', 'crawl', 'c-1', '{"url":"https://pdfcraft.devtoolcafe.com"}');
select pg_temp.expect_error($$insert into public.generation_jobs (product_id, job_type, idempotency_key, input_snapshot)
  values ('00000000-0000-4000-8000-0000000000c1', 'crawl', 'c-2', '{}')$$, '%one_active_crawl%');

-- 10. RLS: owner thấy dữ liệu của mình, người khác không thấy, không ghi được
set local role authenticated;
set local request.jwt.claim.sub = '00000000-0000-4000-8000-0000000000a1';
do $$ begin
  assert (select count(*) from public.products) = 1;
  assert (select count(*) from public.generation_jobs) >= 3;
end $$;
select pg_temp.expect_error($$update public.products set name = 'hack'$$, '%permission denied%');
select pg_temp.expect_error($$select public.review_pkb('00000000-0000-4000-8000-0000000000c1', 2, '00000000-0000-4000-8000-0000000000a1', 'reject', 'x')$$, '%permission denied%');
set local request.jwt.claim.sub = '00000000-0000-4000-8000-0000000000a2';
do $$ begin
  assert (select count(*) from public.products) = 1, 'merchant khác chỉ thấy product của mình';
  assert not exists (select 1 from public.products where id = '00000000-0000-4000-8000-0000000000c1'), 'không thấy product của owner';
  assert (select count(*) from public.product_knowledge where product_id = '00000000-0000-4000-8000-0000000000c1') = 0;
  assert (select count(*) from public.script_revisions where product_id = '00000000-0000-4000-8000-0000000000c1') = 0;
  assert (select count(*) from public.generation_jobs where product_id = '00000000-0000-4000-8000-0000000000c1') = 0;
end $$;
reset role;

do $$ begin raise notice 'ALL OK'; end $$;
rollback;
