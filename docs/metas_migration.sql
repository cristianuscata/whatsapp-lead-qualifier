-- Migración: tabla `metas` (fuente única de metas del coach, editable desde WhatsApp).
-- Ejecutar UNA vez en el SQL Editor de Supabase. Idempotente.

create table if not exists metas (
  key            text primary key,
  descripcion    text not null,
  estado         text default 'activa',   -- activa | pausada | lograda | abandonada
  prioridad      int  default 3,          -- 1 (máxima) .. 5
  fecha_objetivo date,
  created_at     timestamptz default now(),
  updated_at     timestamptz default now()
);

-- Semilla con las metas actuales (no pisa si ya existen).
insert into metas (key, descripcion, prioridad) values
  ('Networking',   'Networking estratégico: construir y activar contactos de alto valor.',       1),
  ('BienesRaices', 'Inversiones en bienes raíces: asistir a eventos y evaluar oportunidades.',   2),
  ('Tecnologia',   'Tecnología: mantenerse a la vanguardia y capitalizarla.',                    1),
  ('Azure',        'Certificación Azure AI-102: en proceso (objetivo julio 2026).',              2),
  ('Maestría',     'Maestría UNAC: sustentar en diciembre 2026.',                                2),
  ('MVP',          'Agente WhatsApp MVP: en producción.',                                        1)
on conflict (key) do nothing;

-- Plazos (fecha_objetivo) para las metas con fecha conocida. Las demás quedan
-- sin plazo hasta que lo definas por WhatsApp ("agrega/renombra ... para julio 2026").
-- Si ya corriste la primera versión de esta migración, ejecuta SOLO estos UPDATE:
update metas set fecha_objetivo = '2026-07-31' where key = 'Azure'    and fecha_objetivo is null;
update metas set fecha_objetivo = '2026-12-15' where key = 'Maestría' and fecha_objetivo is null;
