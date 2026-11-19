# supabase/tests

Test SQL chạy bằng `psql` trên Postgres trống (không cần Supabase CLI hay Docker).

```bash
createdb p1test
psql -v ON_ERROR_STOP=1 -d p1test -f stub_supabase.sql                # giả lập auth.users, auth.uid(), role
for f in ../migrations/*.sql; do psql -v ON_ERROR_STOP=1 -d p1test -f "$f"; done
psql -v ON_ERROR_STOP=1 -d p1test -f p1_pipeline_persistence.test.sql  # in "ALL OK" nếu đạt
```

`stub_supabase.sql` chỉ để test local. Không chạy trên Supabase thật.
