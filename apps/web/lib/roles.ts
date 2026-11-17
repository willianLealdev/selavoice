/** Nome AMIGÁVEL dos papéis (o servidor usa nomes técnicos como TENANT_ADMIN; o usuário nunca deve vê-los). */
type T = (k: string) => string;
export function roleLabel(role: string | undefined, t: T): string {
  switch (role) {
    case "TENANT_ADMIN": return t("Admin");
    case "EVENT_OPERATOR": return t("Operador");
    case "MEMBER": return t("Membro");
    case "SUPER_ADMIN": return "Super Admin";
    default: return role || "—";
  }
}
