create schema if not exists private;
revoke all on schema private from public;
grant usage on schema private to authenticated;

create or replace function private.dolbagram_is_member(p_conversation_id uuid)
returns boolean language sql stable security definer set search_path = ''
as $$ select exists (select 1 from public.dolbagram_conversation_members m where m.conversation_id = p_conversation_id and m.user_id = (select auth.uid())); $$;
create or replace function private.dolbagram_is_creator(p_conversation_id uuid)
returns boolean language sql stable security definer set search_path = ''
as $$ select exists (select 1 from public.dolbagram_conversations c where c.id = p_conversation_id and c.created_by = (select auth.uid())); $$;
revoke all on function private.dolbagram_is_member(uuid) from public, anon;
revoke all on function private.dolbagram_is_creator(uuid) from public, anon;
grant execute on function private.dolbagram_is_member(uuid) to authenticated;
grant execute on function private.dolbagram_is_creator(uuid) to authenticated;

alter policy "Users can see public or joined Dolbagram conversations" on public.dolbagram_conversations using (is_public or private.dolbagram_is_member(id));
alter policy "Members can see Dolbagram memberships" on public.dolbagram_conversation_members using (user_id = (select auth.uid()) or private.dolbagram_is_member(conversation_id) or private.dolbagram_is_creator(conversation_id));
alter policy "Users can join public conversations or creators can add members" on public.dolbagram_conversation_members with check ((user_id = (select auth.uid()) and exists (select 1 from public.dolbagram_conversations c where c.id = conversation_id and c.is_public)) or private.dolbagram_is_creator(conversation_id));
alter policy "Users can leave or creators can remove memberships" on public.dolbagram_conversation_members using (user_id = (select auth.uid()) or private.dolbagram_is_creator(conversation_id));
alter policy "Members can read Dolbagram messages" on public.dolbagram_messages using (private.dolbagram_is_member(conversation_id));
alter policy "Members can send Dolbagram messages" on public.dolbagram_messages with check ((select auth.uid()) = sender_id and private.dolbagram_is_member(conversation_id));
alter policy "Senders can edit their Dolbagram messages" on public.dolbagram_messages using ((select auth.uid()) = sender_id and private.dolbagram_is_member(conversation_id)) with check ((select auth.uid()) = sender_id and private.dolbagram_is_member(conversation_id));

drop function if exists public.dolbagram_is_member(uuid);
drop function if exists public.dolbagram_is_creator(uuid);
revoke all on function public.dolbagram_handle_new_user() from public, anon, authenticated;
create index if not exists dolbagram_conversations_created_by_idx on public.dolbagram_conversations(created_by);
create index if not exists dolbagram_messages_sender_idx on public.dolbagram_messages(sender_id);
