// Configuración pública de Supabase. La clave publicable está pensada para usarse en el navegador:
// la seguridad la dan el inicio de sesión y las políticas RLS de la base de datos.
export const SUPABASE_URL = "https://dnqghjwrrzacbiqcfrry.supabase.co";
export const SUPABASE_KEY = "sb_publishable_YJ_dSKE2CB_W4TvSh6HaQA_rKO4KkTm";
export const FUNCION_CLAUDE = `${SUPABASE_URL}/functions/v1/rag-claude`;
export const BUCKET = "rag-documentos";
