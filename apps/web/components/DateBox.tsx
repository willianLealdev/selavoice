/** Quadradinho de data (mês + dia + ano) usado nas listas de eventos (perfil público e painel). */
export default function DateBox({ iso, locale }: { iso: string; locale: string }) {
  const d = new Date(iso);
  return (
    <div className="datebox" aria-hidden="true">
      <span>{d.toLocaleDateString(locale, { month: "short" }).replace(".", "")}</span>
      <b>{d.getDate()}</b>
      <i>{d.getFullYear()}</i>
    </div>
  );
}
