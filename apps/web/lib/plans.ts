/**
 * Descrição humana de um plano a partir dos limites (entitlements). Usada na landing, na contratação e na
 * prévia do editor do Super Admin, para o texto ser SEMPRE igual ao que o sistema aplica.
 * Convenção: valor null = ilimitado; chave ausente = não mencionar (plano antigo).
 */
type T = (k: string, p?: Record<string, any>) => string;
const has = (e: any, k: string) => e && Object.prototype.hasOwnProperty.call(e, k);
const n = (v: number) => v.toLocaleString("pt-BR");

export function planLines(e: Record<string, any>, t: T, money?: (c: number) => string): string[] {
  const out: string[] = [];
  if (has(e, "included_events")) out.push(e.included_events === null ? t("Eventos ilimitados") : t("{n} evento(s) incluído(s)", { n: e.included_events }));
  if (has(e, "included_hours")) out.push(e.included_hours === null ? t("Horas de transmissão ilimitadas") : t("{n} hora(s) de transmissão incluída(s)", { n: n(e.included_hours) }));
  if (has(e, "max_event_hours") && e.max_event_hours !== null) out.push(t("Até {n} hora(s) por evento", { n: n(e.max_event_hours) }));
  if (has(e, "listener_concurrency")) out.push(e.listener_concurrency === null ? t("Ouvintes ilimitados") : t("Até {n} ouvintes simultâneos", { n: n(e.listener_concurrency) }));
  if (has(e, "max_languages")) out.push(e.max_languages === null ? t("Idiomas simultâneos ilimitados") : t("Até {n} idiomas simultâneos", { n: e.max_languages }));
  if (e?.allowed_languages?.length) out.push(t("Idiomas incluídos: {list}", { list: e.allowed_languages.map((c: string) => c.toUpperCase()).join(", ") }));
  if (has(e, "included_language_minutes")) out.push(e.included_language_minutes === null ? t("Minutos-idioma ilimitados") : t("{n} minutos-idioma incluídos", { n: n(e.included_language_minutes) }));
  if (has(e, "max_concurrent_events") && e.max_concurrent_events !== null && e.max_concurrent_events > 1) out.push(t("{n} eventos ao vivo ao mesmo tempo", { n: e.max_concurrent_events }));
  if (has(e, "admin_seats")) out.push(e.admin_seats === null ? t("Equipe ilimitada") : t("{n} administradores", { n: e.admin_seats }));
  if (e?.recordings) out.push(t("Gravação do evento"));
  if (e?.pdf_booklets) out.push(t("Documento pós-evento em PDF"));
  if (has(e, "extra_hour_cents") && e.extra_hour_cents && money) out.push(t("Hora extra: {price}", { price: money(e.extra_hour_cents) }));
  return out;
}

/** O plano tem horas contadas? (para mostrar a nota "a contagem começa ao iniciar a transmissão"). */
export const countsHours = (e: Record<string, any>) => has(e, "included_hours") && e.included_hours !== null;
