-- RAG Licitaciones: tablas, búsqueda de texto completo en español y almacenamiento.
-- Cada fila pertenece a un usuario (user_id) y RLS solo deja ver y modificar lo propio.

create extension if not exists unaccent with schema extensions;

create or replace function public.rag_unaccent(t text) returns text
language sql immutable parallel safe set search_path = ''
as $$ select extensions.unaccent('extensions.unaccent'::regdictionary, t) $$;

create table if not exists public.rag_documentos (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  nombre text not null,
  categoria text not null,
  hash text not null,
  ruta_archivo text,
  fragmentos int not null default 0,
  caracteres int not null default 0,
  escaneado boolean not null default false,
  created_at timestamptz not null default now(),
  unique (user_id, hash)
);

create table if not exists public.rag_fragmentos (
  id bigint generated always as identity primary key,
  documento_id uuid not null references public.rag_documentos(id) on delete cascade,
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  categoria text not null,
  documento text not null,
  pagina int,
  texto text not null,
  tsv tsvector generated always as (to_tsvector('spanish', public.rag_unaccent(texto))) stored
);

create table if not exists public.rag_analisis (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null default auth.uid() references auth.users(id) on delete cascade,
  pliego text not null,
  resultado text not null,
  fuentes jsonb not null default '[]',
  created_at timestamptz not null default now()
);

create table if not exists public.rag_config (
  user_id uuid primary key default auth.uid() references auth.users(id) on delete cascade,
  empresa text not null default '',
  tipo text not null default 'Agencia de seguros'
);

create index if not exists rag_fragmentos_tsv_idx on public.rag_fragmentos using gin (tsv);
create index if not exists rag_fragmentos_user_idx on public.rag_fragmentos (user_id, categoria);
create index if not exists rag_fragmentos_doc_idx on public.rag_fragmentos (documento_id);
create index if not exists rag_analisis_user_idx on public.rag_analisis (user_id, created_at desc);

alter table public.rag_documentos enable row level security;
alter table public.rag_fragmentos enable row level security;
alter table public.rag_analisis enable row level security;
alter table public.rag_config enable row level security;

create policy "rag_documentos propios" on public.rag_documentos for all to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "rag_fragmentos propios" on public.rag_fragmentos for all to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "rag_analisis propios" on public.rag_analisis for all to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "rag_config propia" on public.rag_config for all to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

-- Búsqueda: para cada consulta (p. ej. cada fragmento del pliego) toma los k mejores fragmentos
-- (cualquier palabra coincide, ordenado por relevancia) y acumula puntajes. Corre con los permisos
-- del usuario (security invoker), así que RLS limita los resultados a sus propios documentos.
create or replace function public.rag_buscar(consultas text[], categorias text[] default null,
                                             k_por_consulta int default 3, maximo int default 40)
returns table (id bigint, documento text, categoria text, pagina int, texto text, puntaje real)
language sql stable security invoker set search_path = ''
as $$
  with q as (
    select ord, nullif(replace(plainto_tsquery('spanish', public.rag_unaccent(c))::text, '&', '|'), '')::tsquery as tq
    from unnest(consultas) with ordinality as u(c, ord)
  ),
  mejores as (
    select f.id, r.rango
    from q
    cross join lateral (
      select fr.id, ts_rank_cd(fr.tsv, q.tq) as rango
      from public.rag_fragmentos fr
      where q.tq is not null and fr.tsv @@ q.tq
        and (categorias is null or fr.categoria = any(categorias))
      order by rango desc
      limit k_por_consulta
    ) r
    join public.rag_fragmentos f on f.id = r.id
  ),
  acumulado as (
    select m.id, sum(m.rango)::real as puntaje from mejores m group by m.id
    order by puntaje desc limit maximo
  )
  select f.id, f.documento, f.categoria, f.pagina, f.texto, a.puntaje
  from acumulado a join public.rag_fragmentos f on f.id = a.id
  order by a.puntaje desc;
$$;

revoke execute on function public.rag_buscar(text[], text[], int, int) from public, anon;
grant execute on function public.rag_buscar(text[], text[], int, int) to authenticated;

-- Almacenamiento privado de los archivos originales: carpeta por usuario (<user_id>/<categoria>/<archivo>).
insert into storage.buckets (id, name, public) values ('rag-documentos', 'rag-documentos', false)
on conflict (id) do nothing;

create policy "rag archivos propios - leer" on storage.objects for select to authenticated
  using (bucket_id = 'rag-documentos' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy "rag archivos propios - subir" on storage.objects for insert to authenticated
  with check (bucket_id = 'rag-documentos' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy "rag archivos propios - borrar" on storage.objects for delete to authenticated
  using (bucket_id = 'rag-documentos' and (storage.foldername(name))[1] = (select auth.uid())::text);
