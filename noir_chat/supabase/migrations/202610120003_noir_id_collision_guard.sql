create or replace function public.dolbagram_handle_new_user()
returns trigger language plpgsql security definer set search_path = ''
as $$
declare chosen_username text; chosen_noir_id text;
begin
  chosen_username := lower(regexp_replace(coalesce(new.raw_user_meta_data->>'username', 'user_' || substr(replace(new.id::text, '-', ''), 1, 12)), '[^a-zA-Z0-9_]', '', 'g'));
  if char_length(chosen_username) < 3 then chosen_username := 'user_' || substr(replace(new.id::text, '-', ''), 1, 12); end if;
  chosen_noir_id := 'NOIR-' || lpad((floor(random() * 900000) + 100000)::text, 6, '0');
  while exists (select 1 from public.dolbagram_profiles p where p.noir_id = chosen_noir_id) loop
    chosen_noir_id := 'NOIR-' || lpad((floor(random() * 900000) + 100000)::text, 6, '0');
  end loop;
  insert into public.dolbagram_profiles (id, username, noir_id, display_name)
  values (new.id, chosen_username, chosen_noir_id, coalesce(nullif(new.raw_user_meta_data->>'display_name',''), chosen_username))
  on conflict (id) do nothing;
  return new;
end;
$$;
revoke all on function public.dolbagram_handle_new_user() from public, anon, authenticated;
