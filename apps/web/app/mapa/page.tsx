/** Mapa de todas as telas (ajuda para revisão em desenvolvimento). Remover/proteger antes de produção. */
import BackButton from "@/components/BackButton";
import { notFound } from "next/navigation";
import Link from "next/link";

const GROUPS: [string, [string, string, string][]][] = [
  ["Público (sem login)", [
    ["/", "Landing de vendas", "Página inicial com preços, FAQ e demonstração"],
    ["/e/65ubgkbrgi", "Página do ouvinte (evento de teste AO VIVO)", "Escolha de idioma, transcrição acumulada, Voltar ao vivo"],
    ["/buscar", "Buscar organização pelo nome (público)", "Digite \"UFC\" ou \"Igreja\""],
    ["/o/igreja-teste-local", "Perfil público da organização (destino do QR do perfil)", "Eventos ao vivo e agendados"],
    ["/legal/privacidade", "Política de privacidade (rascunho)", ""],
    ["/legal/termos", "Termos de uso (rascunho)", ""],
    ["/login", "Entrar", ""], ["/register", "Criar conta grátis", ""],
    ["/forgot", "Esqueci minha senha", ""], ["/reset?token=teste", "Nova senha (precisa de token real)", ""],
    ["/invite?token=teste", "Aceitar convite (precisa de token real)", ""],
  ]],
  ["Painel do organizador (login: demo.local@example.com)", [
    ["/dashboard", "Eventos", "Lista, busca, criar evento"],
    ["/dashboard/profile", "Perfil da organização", "QR do perfil, aparecer na busca, cor"],
    ["/dashboard/billing", "Plano e uso", "Planos e contratação (checkout simulado)"],
    ["/dashboard/team", "Equipe", "Convites"],
    ["/dashboard", "Abrir um evento → Controle, QR, apostila", "Clique em “Abrir →” numa linha"],
    ["/dashboard", "Evento → Capturar áudio", "Botão dentro da página do evento"],
    ["/fake-checkout?session=x", "Checkout simulado (dev)", "Só funciona vindo de “Contratar”"],
  ]],
  ["Super Admin (admin@selavoice.local + MFA)", [
    ["/admin/login", "Login do Super Admin", "Senha + código de 6 dígitos"],
    ["/admin", "Console", "Métricas, organizações, planos, provedores, auditoria"],
    ["/admin/integrations", "Chaves e integrações", "Onde você cola as chaves"],
  ]],
];

export default function Mapa() {
  if (process.env.NODE_ENV === "production") notFound(); // tela de mapa SÓ em desenvolvimento
  return (
    <main className="container" style={{ maxWidth: 860, padding: "40px 20px" }}>
      <BackButton fallback="/" />
      <h1 style={{ marginTop: 16 }}>Mapa de telas (desenvolvimento)</h1>
      <p className="fine">API (docs interativas): <a href="http://localhost:8000/docs">http://localhost:8000/docs</a></p>
      {GROUPS.map(([g, items]) => (
        <section key={g} style={{ marginTop: 26 }}>
          <h2>{g}</h2>
          <table><tbody>
            {items.map(([href, t, d]) => (
              <tr key={href + t}><td><Link href={href}>{t}</Link></td><td className="fine">{d}</td><td className="fine"><code>{href}</code></td></tr>
            ))}
          </tbody></table>
        </section>
      ))}
    </main>
  );
}
