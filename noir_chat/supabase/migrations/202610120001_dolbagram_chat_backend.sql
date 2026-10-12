create table if not exists public.dolbagram_profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  username text not null unique check (char_length(username) between 3 and 24),
  noir_id text not null unique,
  display_name text not null default 'Dolbagram user',
  avatar_url text,
  created_at timestamptz not null default now()
);

create table if not exists public.dolbagram_conversations (
  id uuid primary key default gen_random_uuid(),
  kind text not null default 'group' check (kind in ('direct','group','channel')),
  title text not null,
  description text not null default '',
  is_public boolean not null default false,
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.dolbagram_conversation_members (
  conversation_id uuid not null references public.dolbagram_conversations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null default 'member' check (role in ('owner','admin','member')),
  joined_at timestamptz not null default now(),
  last_read_at timestamptz,
  primary key (conversation_id, user_id)
);

create table if not exists public.dolbagram_messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.dolbagram_conversations(id) on delete cascade,
  sender_id uuid not null references auth.users(id) on delete cascade,
  body text not null check (char_length(body) between 1 and 4000),
  created_at timestamptz not null default now(),
  edited_at timestamptz,
  deleted_at timestamptz
);

create index if not exists dolbagram_messages_conversation_created_idx on public.dolbagram_messages (conversation_id, created_at desc);
create index if not exists dolbagram_members_user_idx on public.dolbagram_conversation_members (user_id, joined_at desc);

create or replace function public.dolbagram_is_member(p_conversation_id uuid)
returns boolean language sql stable security definer set search_path = ''
as $$ select exists (select 1 from public.dolbagram_conversation_members m where m.conversation_id = p_conversation_id and m.user_id = (select auth.uid())); $$;

create or replace function public.dolbagram_is_creator(p_conversation_id uuid)
returns boolean language sql stable security definer set search_path = ''
as $$ select exists (select 1 from public.dolbagram_conversations c where c.id = p_conversation_id and c.created_by = (select auth.uid())); $$;

revoke all on function public.dolbagram_is_member(uuid) from public;
revoke all on function public.dolbagram_is_creator(uuid) from public;
grant execute on function public.dolbagram_is_member(uuid) to authenticated;
grant execute on function public.dolbagram_is_creator(uuid) to authenticated;

alter table public.dolbagram_profiles enable row level security;
alter table public.dolbagram_conversations enable row level security;
alter table public.dolbagram_conversation_members enable row level security;
alter table public.dolbagram_messages enable row level security;

create policy "Dolbagram profiles are visible to signed-in users" on public.dolbagram_profiles for select to authenticated using (true);
create policy "Users can update their own Dolbagram profile" on public.dolbagram_profiles for update to authenticated using ((select auth.uid()) = id) with check ((select auth.uid()) = id);
create policy "Users can see public or joined Dolbagram conversations" on public.dolbagram_conversations for select to authenticated using (is_public or public.dolbagram_is_member(id));
create policy "Signed-in users can create Dolbagram conversations" on public.dolbagram_conversations for insert to authenticated with check ((select auth.uid()) = created_by);
create policy "Creators can update their Dolbagram conversations" on public.dolbagram_conversations for update to authenticated using ((select auth.uid()) = created_by) with check ((select auth.uid()) = created_by);
create policy "Members can see Dolbagram memberships" on public.dolbagram_conversation_members for select to authenticated using (user_id = (select auth.uid()) or public.dolbagram_is_member(conversation_id) or public.dolbagram_is_creator(conversation_id));
create policy "Users can join public conversations or creators can add members" on public.dolbagram_conversation_members for insert to authenticated with check ((user_id = (select auth.uid()) and exists (select 1 from public.dolbagram_conversations c where c.id = conversation_id and c.is_public)) or public.dolbagram_is_creator(conversation_id));
create policy "Users can leave or creators can remove memberships" on public.dolbagram_conversation_members for delete to authenticated using (user_id = (select auth.uid()) or public.dolbagram_is_creator(conversation_id));
create policy "Members can read Dolbagram messages" on public.dolbagram_messages for select to authenticated using (public.dolbagram_is_member(conversation_id));
create policy "Members can send Dolbagram messages" on public.dolbagram_messages for insert to authenticated with check ((select auth.uid()) = sender_id and public.dolbagram_is_member(conversation_id));
create policy "Senders can edit their Dolbagram messages" on public.dolbagram_messages for update to authenticated using ((select auth.uid()) = sender_id and public.dolbagram_is_member(conversation_id)) with check ((select auth.uid()) = sender_id and public.dolbagram_is_member(conversation_id));

grant select, update on public.dolbagram_profiles to authenticated;
grant select, insert, update on public.dolbagram_conversations to authenticated;
grant select, insert, delete on public.dolbagram_conversation_members to authenticated;
grant select, insert, update on public.dolbagram_messages to authenticated;

create or replace function public.dolbagram_handle_new_user()
returns trigger language plpgsql security definer set search_path = ''
as $$
declare chosen_username text; chosen_noir_id text;
begin
  chosen_username := lower(regexp_replace(coalesce(new.raw_user_meta_data->>'username', 'user_' || substr(replace(new.id::text, '-', ''), 1, 8)), '[^a-zA-Z0-9_]', '', 'g'));
  if char_length(chosen_username) < 3 then chosen_username := 'user_' || substr(replace(new.id::text, '-', ''), 1, 8); end if;
  chosen_noir_id := 'NOIR-' || upper(substr(replace(new.id::text, '-', ''), 1, 6));
  insert into public.dolbagram_profiles (id, username, noir_id, display_name)
  values (new.id, chosen_username, chosen_noir_id, coalesce(nullif(new.raw_user_meta_data->>'display_name',''), chosen_username))
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_dolbagram_auth_user_created on auth.users;
create trigger on_dolbagram_auth_user_created after insert on auth.users for each row execute procedure public.dolbagram_handle_new_user();

insert into public.dolbagram_conversations (kind, title, description, is_public)
select 'group', seed.title, seed.description, true
from (values ('Late Night', 'Разговоры после полуночи'), ('Mindspace', 'Идеи, мысли и открытия'), ('Indie Corner', 'Музыка, кино и творчество'), ('Quiet Club', 'Можно просто быть собой')) as seed(title, description)
where not exists (select 1 from public.dolbagram_conversations c where c.title = seed.title and c.is_public = true);

do $$ begin
  alter publication supabase_realtime add table public.dolbagram_messages;
exception when duplicate_object then null; when undefined_object then null;
end $$;
