"use client";
/**
 * Perfil da igreja/organização: nome, cor, aparecer na busca pública, e o QR do PERFIL (que mostra os eventos ao vivo).
 * O ouvinte pode escanear esse QR (fixo, pode ser impresso) em vez do QR de cada evento.
 */
import { useEffect, useState } from "react";
import QRCode from "qrcode";
import Icon from "@/components/Icon";
import OrgLogo from "@/components/OrgLogo";
import { api, setToken } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function Profile() {
  const t = useT();
  const [org, setOrg] = useState<any>(null); const [qr, setQr] = useState(""); const [msg, setMsg] = useState<{ ok: boolean; m: string } | null>(null);
  const [name, setName] = useState(""); const [color, setColor] = useState("#0B63CE"); const [listed, setListed] = useState(true); const [hist, setHist] = useState(true);
  const [c, setC] = useState<Record<string, string>>({});
  const [delPw, setDelPw] = useState(""); const [delErr, setDelErr] = useState("");
  const [au, setAu] = useState<{ filter: string; noise_suppression: boolean; only_event_language: boolean }>({ filter: "normal", noise_suppression: true, only_event_language: true }); const [busy, setBusy] = useState(false);
  useEffect(() => {
    api("/organizations/me").then(async (o) => {
      setOrg(o); setName(o.name); setListed(o.listed); setHist(o.history_public !== false); setC(o.contact ?? {}); if (o.audio) setAu(o.audio); setColor(o.branding?.primary_color || "#0B63CE");
      setQr(await QRCode.toDataURL(`${location.origin}/o/${o.slug}`, { width: 260, margin: 1 }));
    }).catch((e) => setMsg({ ok: false, m: e.message }));
  }, []);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    try { await api("/organizations/me", { method: "PATCH", json: { name, listed, history_public: hist, contact: c, audio: au, branding: { primary_color: color } } }); setMsg({ ok: true, m: t("Salvo.") }); }
    catch (x: any) { setMsg({ ok: false, m: x.message }); }
  }
  async function sendLogo(f?: File) {
    if (!f) return; setBusy(true); setMsg(null);
    const fd = new FormData(); fd.append("file", f);
    try { const r = await api("/organizations/me/logo", { method: "POST", body: fd }); setOrg({ ...org, branding: { ...org.branding, logo_url: r.logo_url } }); setMsg({ ok: true, m: "Logo atualizado." }); }
    catch (x: any) { setMsg({ ok: false, m: x.message }); } finally { setBusy(false); }
  }
  async function removeLogo() {
    try { await api("/organizations/me/logo", { method: "DELETE" }); const b = { ...org.branding }; delete b.logo_url; setOrg({ ...org, branding: b }); setMsg({ ok: true, m: "Logo removido." }); }
    catch (x: any) { setMsg({ ok: false, m: x.message }); }
  }
  const f = (k: string) => ({ value: c[k] ?? "", onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setC({ ...c, [k]: e.target.value }) });
  if (!org) return <p>{t("Carregando…")}</p>;
  const url = `${location.origin}/o/${org.slug}`;
  return (
    <>
      <div className="page-h"><h1>{t("Perfil da organização")}</h1></div>
      {msg && <div className={msg.ok ? "ok" : "err"}>{t(msg.m)}</div>}
      <div className="grid-2">
        <form className="card" onSubmit={save}>
          <label>{t("Logo da organização")}</label>
          <div className="logo-up">
            <OrgLogo name={name || org.name} url={org.branding?.logo_url} size={72} />
            <div>
              <label className="btn btn-ghost btn-sm" style={{ margin: 0, cursor: "pointer" }}><Icon name="upload" small /> {busy ? t("Enviando…") : t("Enviar logo")}
                <input type="file" accept="image/png,image/jpeg,image/webp" hidden disabled={busy} onChange={(e) => { sendLogo(e.target.files?.[0]); e.target.value = ""; }} /></label>
              {org.branding?.logo_url && <button type="button" className="btn btn-ghost btn-sm" style={{ marginLeft: 8 }} onClick={removeLogo}>{t("Remover")}</button>}
              <p className="fine" style={{ margin: "6px 0 0" }}>{t("PNG, JPG ou WebP, até 2 MB. Aparece para todo o público.")}</p>
            </div>
          </div>
          <label>{t("Nome da organização")}</label><input required minLength={2} value={name} onChange={(e) => setName(e.target.value)} />
          <h3 style={{ marginTop: 28 }}>{t("Áudio e ruído")}</h3>
          <p className="fine">{t("Controla o que o sistema traduz quando há barulho, conversa ao redor ou fala em outro idioma.")}</p>
          <label>{t("Filtro de voz do palestrante")}</label>
          <p className="fine" style={{ marginTop: -2 }}>{t("O palestrante fica perto do microfone, então a voz dele chega MAIS ALTA. O filtro ignora o que chega baixinho, como pessoas conversando ao fundo.")}</p>
          <div className="choice col">
            {([["off", "Desligado", "Não ignora nada. Use quando o som vem de uma mesa de som (já vem limpo)."], ["normal", "Normal (recomendado)", "Ignora conversa que chega baixinho no microfone. Serve para a maioria dos casos."], ["strong", "Forte", "Ignora até vozes um pouco mais baixas. Use em sala muito barulhenta. Cuidado: pode cortar o palestrante se ele falar muito baixo."]] as const).map(([k, title, d]) => (
              <button type="button" key={k} className={au.filter === k ? "on" : ""} onClick={() => setAu({ ...au, filter: k })}><b>{t(title)}</b><span>{t(d)}</span></button>
            ))}
          </div>
          <label className="pf-check"><input type="checkbox" checked={au.noise_suppression} onChange={(e) => setAu({ ...au, noise_suppression: e.target.checked })} /> {t("Reduzir ruído do ambiente na captura pelo navegador")}</label>
          <label className="pf-check"><input type="checkbox" checked={au.only_event_language} onChange={(e) => setAu({ ...au, only_event_language: e.target.checked })} /> {t("Traduzir somente o idioma do evento (ignorar outras línguas e falas ininteligíveis)")}</label>
          <p className="fine">{t("O sistema separa a voz principal pelo VOLUME: use um microfone próximo à boca do palestrante (lapela, headset ou de mão) para o filtro funcionar bem.")}</p>

          <h3 style={{ marginTop: 28 }}>{t("Dados públicos")}</h3>
          <p className="fine">{t("Aparecem para o público para confirmar que está no lugar certo. Preencha só o que quiser mostrar.")}</p>
          <label>{t("Sobre a organização")}</label><textarea rows={3} maxLength={400} {...f("description")} />
          <label>{t("Endereço")}</label><input maxLength={200} {...f("address")} placeholder="123 Main St" />
          <label>{t("Cidade / país")}</label><input maxLength={100} {...f("city")} placeholder="Las Vegas, NV · USA" />
          <label>{t("Site")}</label><input maxLength={200} {...f("website")} placeholder="https://" />
          <div className="grid-2">
            <div><label>Instagram</label><input {...f("instagram")} placeholder="@usuario" /></div>
            <div><label>Facebook</label><input {...f("facebook")} placeholder="pagina" /></div>
            <div><label>YouTube</label><input {...f("youtube")} placeholder="@canal" /></div>
            <div><label>TikTok</label><input {...f("tiktok")} placeholder="@usuario" /></div>
            <div><label>{t("Telefone")}</label><input {...f("phone")} /></div>
            <div><label>WhatsApp</label><input {...f("whatsapp")} placeholder="+1 702 000 0000" /></div>
          </div>
          <label>{t("E-mail de contato")}</label><input type="email" {...f("email")} />
          <label>{t("Cor principal (documentos)")}</label><input type="color" value={color} onChange={(e) => setColor(e.target.value)} style={{ width: 80, height: 40, padding: 2 }} />
          <label style={{ display: "flex", gap: 8, alignItems: "center", fontWeight: 500 }}>
            <input type="checkbox" style={{ width: "auto" }} checked={listed} onChange={(e) => setListed(e.target.checked)} /> {t("Aparecer na busca pública")}
          </label>
          <p className="fine">{t("Se desmarcar, só quem tiver o QR ou o link do perfil encontra sua organização.")}</p>
          <label style={{ display: "flex", gap: 8, alignItems: "center", fontWeight: 500 }}>
            <input type="checkbox" style={{ width: "auto" }} checked={hist} onChange={(e) => setHist(e.target.checked)} /> {t("Mostrar histórico de eventos no perfil público")}
          </label>
          <p className="fine">{t("O público poderá reabrir a transcrição dos eventos já encerrados.")}</p>
          <button className="btn btn-primary" style={{ marginTop: 12 }}>{t("Salvar")}</button>
        </form>
        <div className="card" style={{ textAlign: "center" }}>
          <h3>{t("QR Code do perfil da organização")}</h3>
          {qr && <img src={qr} alt={t("QR Code do perfil da organização")} width={260} height={260} />}
          <p><a href={url} target="_blank" rel="noreferrer">{url}</a></p>
          <p className="fine">{t("Imprima e exiba no local: o público escaneia e vê os eventos ao vivo, sem criar conta.")}</p>
          <a className="btn btn-ghost btn-sm" href={qr} download={`qr-${org.slug}.png`}>{t("Baixar QR")}</a>
        </div>
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <h3>{t("Excluir minha conta")}</h3>
        <p className="fine">{t("Apaga seus dados pessoais e remove seu acesso. Se você é a única pessoa da organização, ela também é encerrada e sai do ar. Isso não pode ser desfeito.")}</p>
        <form className="row" style={{ alignItems: "flex-end" }} onSubmit={async (e) => {
          e.preventDefault();
          if (!confirm(t("Excluir sua conta de verdade? Isso não pode ser desfeito."))) return;
          try { await api("/auth/me/delete", { method: "POST", json: { password: delPw } }); setToken(null); location.href = "/"; } catch (x: any) { setDelErr(x.message); }
        }}>
          <div><label>{t("Digite sua senha para confirmar")}</label><input type="password" required value={delPw} onChange={(e) => setDelPw(e.target.value)} autoComplete="current-password" /></div>
          <button className="btn btn-danger">{t("Excluir minha conta")}</button>
        </form>
        {delErr && <div className="err" style={{ marginTop: 10 }}>{t(delErr)}</div>}
      </div>
    </>
  );
}
