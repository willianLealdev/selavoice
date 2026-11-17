"use client";
/** Dados públicos da organização (endereço, site, redes...). Só mostra o que o organizador preencheu. */
import Icon from "./Icon";
import { useT } from "@/lib/i18n";

const SOCIAL: [string, string][] = [["instagram", "Instagram"], ["facebook", "Facebook"], ["youtube", "YouTube"], ["tiktok", "TikTok"]];

export default function OrgContact({ contact, dark = false }: { contact?: any; dark?: boolean }) {
  const t = useT();
  if (!contact) return null;
  const c = contact; const links = c.links ?? {};
  const place = [c.address, c.city].filter(Boolean).join(" · ");
  const items: React.ReactNode[] = [];
  const ext = { target: "_blank", rel: "noopener noreferrer nofollow" } as const;
  if (place) items.push(<a key="pin" {...ext} href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(place)}`}><Icon name="pin" small /> {place}</a>);
  if (c.website) items.push(<a key="web" {...ext} href={c.website}><Icon name="globe" small /> {c.website.replace(/^https?:\/\/(www\.)?/i, "").replace(/\/$/, "")}</a>);
  for (const [k, label] of SOCIAL) if (links[k]) items.push(<a key={k} {...ext} href={links[k]}><Icon name={k} small /> {label}</a>);
  if (c.phone) items.push(<a key="ph" href={`tel:${c.phone.replace(/[^0-9+]/g, "")}`}><Icon name="phone" small /> {c.phone}</a>);
  if (c.whatsapp) items.push(<a key="wa" {...ext} href={`https://wa.me/${c.whatsapp.replace(/[^0-9]/g, "")}`}><Icon name="phone" small /> WhatsApp</a>);
  if (c.email) items.push(<a key="em" href={`mailto:${c.email}`}><Icon name="mail" small /> {c.email}</a>);
  if (!items.length && !c.description) return null;
  return (
    <div className={`org-contact ${dark ? "on-dark" : ""}`} aria-label={t("Sobre a organização")}>
      {c.description && <p>{c.description}</p>}
      {!!items.length && <div className="oc-links">{items}</div>}
    </div>
  );
}
