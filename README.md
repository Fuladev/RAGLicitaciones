# RAG Licitaciones (beta)

Web para preparar observaciones a pliegos de condiciones apoyándose en tus propios documentos.

**Página publicada:** https://fuladev.github.io/RAGLicitaciones/

## Cómo funciona
- **Página estática** (GitHub Pages, rama `pages`): `index.html` y `assets/`. Lee los PDF, Word y Excel en tu navegador y los divide en fragmentos.
- **Supabase** (proyecto `gestor-informes`, tablas con prefijo `rag_`):
  - Inicio de sesión con correo y contraseña. Solo pueden registrarse los correos de la tabla `miembros`.
  - `rag_documentos`, `rag_fragmentos`, `rag_analisis`, `rag_config`: cada fila pertenece a un usuario y RLS solo deja ver lo propio.
  - Búsqueda de texto completo en español (`rag_buscar`) sobre los fragmentos.
  - Bucket privado `rag-documentos` con los archivos originales.
  - Edge Function `rag-claude`: recibe el pliego y los fragmentos recuperados, llama a Claude (`claude-opus-5-5`) y devuelve la respuesta en streaming. La clave de Anthropic vive como secreto de Supabase, nunca en la página.

## Puesta en marcha (una sola vez)
1. En Supabase → proyecto **gestor-informes** → Edge Functions → Secrets, crea `ANTHROPIC_API_KEY` con tu clave de https://console.anthropic.com/settings/keys.
2. En Supabase → Authentication → URL Configuration, agrega `https://fuladev.github.io/RAGLicitaciones/` a Redirect URLs (para recuperación de contraseña).
3. Entra a la página con tu correo y contraseña de Supabase.

## Estructura
```
index.html, assets/          página (GitHub Pages)
assets/vendor/               librerías copiadas (supabase-js, pdf.js, mammoth, SheetJS, marked, DOMPurify)
supabase/migrations/         SQL de tablas, RLS, búsqueda y almacenamiento
supabase/functions/rag-claude/  Edge Function que llama a Claude
local-streamlit/             versión local en Python (Streamlit), sin Supabase
```

## Limitaciones de la beta
- PDF escaneados: no hay OCR; la página avisa cuando un archivo parece escaneado.
- La búsqueda es por palabras (texto completo en español), no semántica.
- En el plan gratuito de Supabase una Edge Function puede correr hasta 150 segundos; con pliegos muy largos usa la profundidad "Rápida" o "Normal".
- Las observaciones deben revisarse por el área jurídica antes de radicarlas.
