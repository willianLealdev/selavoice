"use client";
/** Super Admin — PROVEDORES DE IA: saúde, configuração e capacidades de idioma (verificado × não verificado). */
import { useEffect, useState } from "react";
import { PageHead, Panel } from "@/components/AdminUI";
import { api } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function Provedores() {
  const t = useT();
  const [prov, setProv] = useState<any[]>([]); const [err, setErr] = useState("");
  useEffect(() => { api("/admin/providers").then(setProv).catch((e) => setErr(e.message)); }, []);
  return (
    <>
      <PageHead title={t("Provedores de IA")} sub={t("Saúde e idiomas oferecidos por cada provedor.")} />
      {err && <div className="err">{t(err)}</div>}
      <div className="prov-grid">
        {prov.map((p) => (
          <Panel key={p.name} title={p.name} right={p.healthy ? <span className="badge badge-ok">OK</span> : p.configured ? <span className="badge badge-live">{t("Com problema")}</span> : <span className="badge">{t("Não configurado")}</span>}>
            <p className="fine" style={{ marginTop: 0 }}>{p.detail}</p>
            <div className="chips">
              {p.languages.slice(0, 60).map((l: any) => <span key={l.language} className={`chip-lang ${l.verified ? "v" : ""}`} title={l.verified ? t("verificado") : t("não verificado")}>{l.language}{l.verified ? "" : "?"}</span>)}
              {!p.languages.length && <span className="fine">{t("Nenhum idioma listado.")}</span>}
              {p.languages.length > 60 && <span className="fine">+{p.languages.length - 60}</span>}
            </div>
          </Panel>
        ))}
      </div>
      <p className="fine">{t("“?” = capacidade ainda NÃO verificada contra a documentação oficial/teste real.")}</p>
    </>
  );
}
