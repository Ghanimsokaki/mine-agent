-- ForgePilot schema. Run in the Supabase SQL editor as project owner.
-- This migration intentionally uses only the anon key in the Streamlit app;
-- never expose a service_role key to the browser or Streamlit UI.

create extension if not exists pgcrypto with schema extensions;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Administrator allow-list. This is intentionally not client-readable.
-- Change the address only through a project-owner SQL migration.
create table if not exists public.admin_users (
  email text primary key,
  created_at timestamptz not null default now()
);
insert into public.admin_users (email)
values ('emir.erningpraja@gmail.com')
on conflict (email) do nothing;

create or replace function public.is_current_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.admin_users
    where lower(email) = lower(coalesce(auth.jwt() ->> 'email', ''))
  );
$$;

create table if not exists public.usage_windows (
  user_id uuid primary key references auth.users(id) on delete cascade,
  started_at timestamptz not null default now(),
  cooldown_until timestamptz,
  updated_at timestamptz not null default now()
);

create table if not exists public.conversations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  title text not null default 'New conversation' check (char_length(title) <= 120),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists conversations_user_updated_idx on public.conversations (user_id, updated_at desc);

create table if not exists public.messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations(id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content text not null check (char_length(content) <= 100000),
  model text not null default '',
  created_at timestamptz not null default now()
);
create index if not exists messages_conversation_created_idx on public.messages (conversation_id, created_at);

create table if not exists public.memory_items (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  source text not null default 'chat' check (char_length(source) <= 50),
  content text not null check (char_length(content) <= 2000),
  created_at timestamptz not null default now()
);
create index if not exists memory_user_created_idx on public.memory_items (user_id, created_at desc);

create table if not exists public.file_items (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  filename text not null check (char_length(filename) <= 120),
  storage_path text not null unique,
  mime_type text not null default 'application/octet-stream',
  size_bytes bigint not null default 0 check (size_bytes >= 0 and size_bytes <= 52428800),
  kind text not null default 'reference' check (char_length(kind) <= 50),
  created_at timestamptz not null default now()
);
create index if not exists files_user_created_idx on public.file_items (user_id, created_at desc);

create table if not exists public.browser_agents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  name text not null default 'My browser' check (char_length(name) <= 80),
  secret_hash text not null check (char_length(secret_hash) = 64),
  created_at timestamptz not null default now(),
  last_seen_at timestamptz
);
create index if not exists browser_agents_user_idx on public.browser_agents (user_id, created_at desc);

create table if not exists public.browser_tasks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  agent_id uuid not null references public.browser_agents(id) on delete cascade,
  payload jsonb not null,
  status text not null default 'queued' check (status in ('queued', 'dispatched', 'completed', 'declined', 'failed', 'expired')),
  result jsonb,
  created_at timestamptz not null default now(),
  claimed_at timestamptz,
  completed_at timestamptz,
  expires_at timestamptz not null default (now() + interval '15 minutes')
);
create index if not exists browser_tasks_agent_queue_idx on public.browser_tasks (agent_id, status, created_at);

-- Keep each user from attaching a task to someone else's browser agent.
create or replace function public.browser_task_owner_check()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
  if not exists (
    select 1 from public.browser_agents a
    where a.id = new.agent_id and a.user_id = auth.uid()
  ) then
    raise exception 'browser agent does not belong to current user';
  end if;
  new.user_id := auth.uid();
  return new;
end;
$$;

drop trigger if exists browser_task_owner_check_trigger on public.browser_tasks;
create trigger browser_task_owner_check_trigger
before insert on public.browser_tasks
for each row execute function public.browser_task_owner_check();

-- Private bucket. Objects are addressed under <auth.uid()>/<random>-<filename>.
insert into storage.buckets (id, name, public, file_size_limit)
values ('agent-files', 'agent-files', false, 52428800)
on conflict (id) do update set public = false, file_size_limit = 52428800;

alter table public.profiles enable row level security;
alter table public.admin_users enable row level security;
alter table public.usage_windows enable row level security;
alter table public.conversations enable row level security;
alter table public.messages enable row level security;
alter table public.memory_items enable row level security;
alter table public.file_items enable row level security;
alter table public.browser_agents enable row level security;
alter table public.browser_tasks enable row level security;

-- Rerunnable policies.
drop policy if exists "profile private" on public.profiles;
create policy "profile private" on public.profiles for all to authenticated
  using (id = auth.uid()) with check (id = auth.uid());
drop policy if exists "usage private" on public.usage_windows;
create policy "usage private" on public.usage_windows for select to authenticated
  using (user_id = auth.uid());
drop policy if exists "conversation private" on public.conversations;
create policy "conversation private" on public.conversations for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists "message private" on public.messages;
create policy "message private" on public.messages for all to authenticated
  using (exists (select 1 from public.conversations c where c.id = conversation_id and c.user_id = auth.uid()))
  with check (exists (select 1 from public.conversations c where c.id = conversation_id and c.user_id = auth.uid()));
drop policy if exists "memory private" on public.memory_items;
create policy "memory private" on public.memory_items for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists "file metadata private" on public.file_items;
create policy "file metadata private" on public.file_items for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists "browser agent private" on public.browser_agents;
create policy "browser agent private" on public.browser_agents for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());
drop policy if exists "browser task private" on public.browser_tasks;
create policy "browser task private" on public.browser_tasks for all to authenticated
  using (user_id = auth.uid()) with check (user_id = auth.uid());

drop policy if exists "private agent files read" on storage.objects;
create policy "private agent files read" on storage.objects for select to authenticated
  using (bucket_id = 'agent-files' and (storage.foldername(name))[1] = auth.uid()::text);
drop policy if exists "private agent files write" on storage.objects;
create policy "private agent files write" on storage.objects for insert to authenticated
  with check (bucket_id = 'agent-files' and (storage.foldername(name))[1] = auth.uid()::text);
drop policy if exists "private agent files update" on storage.objects;
create policy "private agent files update" on storage.objects for update to authenticated
  using (bucket_id = 'agent-files' and (storage.foldername(name))[1] = auth.uid()::text)
  with check (bucket_id = 'agent-files' and (storage.foldername(name))[1] = auth.uid()::text);
drop policy if exists "private agent files delete" on storage.objects;
create policy "private agent files delete" on storage.objects for delete to authenticated
  using (bucket_id = 'agent-files' and (storage.foldername(name))[1] = auth.uid()::text);

-- Atomic 7-hour usage window / 8-hour cooldown. Called immediately before a model request.
create or replace function public.consume_usage_window()
returns table(allowed boolean, state text, remaining_seconds integer, starts_on_first_request boolean)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user uuid := auth.uid();
  v_now timestamptz := now();
  v_window public.usage_windows%rowtype;
begin
  if v_user is null then
    raise exception 'authentication required';
  end if;

  insert into public.usage_windows(user_id, started_at, cooldown_until, updated_at)
  values (v_user, v_now, null, v_now)
  on conflict (user_id) do nothing;

  select * into v_window from public.usage_windows where user_id = v_user for update;

  if v_window.cooldown_until is not null and v_now < v_window.cooldown_until then
    return query select false, 'cooldown'::text,
      greatest(0, extract(epoch from (v_window.cooldown_until - v_now))::integer), false;
    return;
  end if;

  if v_window.cooldown_until is not null and v_now >= v_window.cooldown_until then
    update public.usage_windows
      set started_at = v_now, cooldown_until = null, updated_at = v_now
      where user_id = v_user;
    return query select true, 'active'::text, 25200, true;
    return;
  end if;

  if v_now >= v_window.started_at + interval '7 hours' then
    update public.usage_windows
      set cooldown_until = v_now + interval '8 hours', updated_at = v_now
      where user_id = v_user;
    return query select false, 'cooldown'::text, 28800, false;
    return;
  end if;

  return query select true, 'active'::text,
    greatest(0, extract(epoch from (v_window.started_at + interval '7 hours' - v_now))::integer), false;
end;
$$;

-- Browser extension functions use a per-browser secret. They do not expose table access to anon users.
create or replace function public.browser_secret_valid(p_agent_id uuid, p_secret text)
returns boolean
language sql
stable
security definer
set search_path = public, extensions
as $$
  select exists (
    select 1 from public.browser_agents
    where id = p_agent_id
      and secret_hash = encode(extensions.digest(p_secret, 'sha256'), 'hex')
  );
$$;

create or replace function public.claim_browser_task(p_agent_id uuid, p_secret text)
returns jsonb
language plpgsql
security definer
set search_path = public, extensions
as $$
declare
  v_task public.browser_tasks%rowtype;
begin
  if not public.browser_secret_valid(p_agent_id, p_secret) then
    raise exception 'invalid browser bridge credentials';
  end if;

  update public.browser_tasks
    set status = 'expired'
    where agent_id = p_agent_id and status = 'queued' and expires_at <= now();

  select * into v_task from public.browser_tasks
    where agent_id = p_agent_id and status = 'queued' and expires_at > now()
    order by created_at asc
    limit 1 for update skip locked;

  update public.browser_agents set last_seen_at = now() where id = p_agent_id;
  if v_task.id is null then
    return null;
  end if;

  update public.browser_tasks
    set status = 'dispatched', claimed_at = now()
    where id = v_task.id;

  return jsonb_build_object('id', v_task.id, 'payload', v_task.payload, 'created_at', v_task.created_at);
end;
$$;

create or replace function public.complete_browser_task(
  p_agent_id uuid,
  p_secret text,
  p_task_id uuid,
  p_status text,
  p_result jsonb default '{}'::jsonb
)
returns boolean
language plpgsql
security definer
set search_path = public, extensions
as $$
begin
  if not public.browser_secret_valid(p_agent_id, p_secret) then
    raise exception 'invalid browser bridge credentials';
  end if;
  if p_status not in ('completed', 'declined', 'failed') then
    raise exception 'invalid completion status';
  end if;

  update public.browser_tasks
    set status = p_status, result = p_result, completed_at = now()
    where id = p_task_id and agent_id = p_agent_id and status = 'dispatched';
  return found;
end;
$$;

revoke all on function public.is_current_admin() from public;
grant execute on function public.is_current_admin() to authenticated;
revoke all on function public.consume_usage_window() from public;
grant execute on function public.consume_usage_window() to authenticated;
revoke all on function public.browser_secret_valid(uuid, text) from public;
revoke all on function public.claim_browser_task(uuid, text) from public;
revoke all on function public.complete_browser_task(uuid, text, uuid, text, jsonb) from public;
grant execute on function public.claim_browser_task(uuid, text) to anon, authenticated;
grant execute on function public.complete_browser_task(uuid, text, uuid, text, jsonb) to anon, authenticated;
