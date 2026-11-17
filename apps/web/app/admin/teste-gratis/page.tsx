"use client";
/**
 * Super Admin — TESTE GRÁTIS. O dono decide se existe teste e TUDO o que ele inclui (mesmas opções de um plano).
 * Vale para as contas criadas DEPOIS de salvar. A landing e o cadastro mostram exatamente o que está aqui.
 */
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { PageHead, Panel } from "@/components/AdminUI";
import Icon from "@/components/Icon";
import { Field, LimitsFields, limitsFromEnt, limitsToEnt, N, type LimitsForm, type Num } from "@/components/LimitsEditor";
import { api, money } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { planLines } from "@/lib/plans";
import { trialHeadline } from "@/lib/trial";

export default function TesteGratis() {
  const t = useT();
  const [enabled, setEnabled] = useState(true);
  const [days, setDays] = useState<Num>(N("", true));         // "ilimitado" = o teste não expira
  const [f, setF] = useState<LimitsForm | null>(null);
  const [all, setAll] = useState<{ code: string }[]>([]);
  const [err, setErr] = useState(""); const [ok, setOk] = useState(""); const [saving, setSaving] = useState(false);

  useEffect(() => {
    api("/admin/trial").then((c: any) => { setEnabled(c.enabled); setDays(c.days ? N(c.days) : N("", true)); setF(limitsFromEnt(c.limits ?? {})); }).catch((e) => setErr(e.message));
    api("/public/languages").then(setAll).catch(() => {});
  }, []);
  const limits = useMemo(() => (f ? limitsToEnt(f) : {}), [f]);
  const lines = useMemo(() => planLines(limits, t as any, (c) => money(c, "usd")), [limits, t]);

  async function save() {
    if (!f) return; setErr(""); setOk(""); setSaving(true);
    try {
      await api("/admin/trial", { method: "PUT", json: { enabled, days: days.u ? null : Math.max(1, Math.round(Number(String(days.v).replace(",", ".")) || 1)), limits } });
      setOk(t("Teste grátis salvo. Vale para as contas criadas a partir de agora; a página inicial já mostra o novo teste."));
    } catch (e: any) { setErr(e.message); } finally { setSaving(false); }
  }

  return (
    <>
      <PageHead title={t("Teste grátis")} sub={t("Defina o que uma organização nova recebe ao criar a conta. Você decide tudo aqui.")} />
      {err && <div className="err">{t(err)}</div>}{ok && <div className="ok">{ok}</div>}
      {f && (
        <div className="editor">
          <div className="editor-form">
            <Panel title={t("Configuração do teste")} hint={t("Vale para as contas criadas DEPOIS de salvar. Quem já recebeu um teste continua com o que recebeu.")}>
              <div className="choice">
                <button type="button" className={enabled ? "on" : ""} onClick={() => setEnabled(true)}><b>{t("Teste grátis LIGADO")}</b><span>{t("Conta nova recebe o teste abaixo, sem cartão de crédito.")}</span></button>
                <button type="button" className={!enabled ? "on" : ""} onClick={() => setEnabled(false)}><b>{t("Teste grátis DESLIGADO")}</b><span>{t("Conta nova não recebe nada e precisa contratar um plano para transmitir.")}</span></button>
              </div>
              {enabled && <>
                <div className="pf-grid"><Field label={t("Validade do teste")} hint={t("Depois desse prazo o teste deixa de valer, mesmo que sobre saldo.")} value={days} onChange={setDays} unit={t("dias")} unlimitedLabel={t("Não expira")} /></div>
                <LimitsFields f={f} set={(p) => setF({ ...f, ...p })} scope="TRIAL" all={all} />
              </>}
              <div className="row" style={{ marginTop: 20 }}>
                <button className="btn btn-primary btn-lg" disabled={saving} onClick={save}>{saving ? t("Salvando…") : t("Salvar teste grátis")}</button>
              </div>
            </Panel>
          </div>
          <aside className="editor-preview">
            <div className="card price">
              <span className="fine">{t("Como aparece na página inicial")}</span>
              {enabled ? <>
                <h3>{t("Teste grátis")}</h3>
                <p className="muted" style={{ marginTop: 0 }}>{trialHeadline(limits, t as any)}</p>
                <ul>{lines.map((l) => <li key={l}><Icon name="check" /> {l}</li>)}</ul>
                {!days.u && <p className="fine">{t("Válido por {n} dias.", { n: days.v })}</p>}
              </> : <p className="muted">{t("Com o teste desligado, a página inicial não mostra nenhuma oferta de teste.")}</p>}
              <Link className="fine" href="/" target="_blank">{t("Abrir a página inicial")}</Link>
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
