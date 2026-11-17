"use client";
/** A captura de áudio agora fica na própria tela do evento (configura antes de Iniciar). Esta rota só redireciona. */
import { use, useEffect } from "react";

export default function CaptureRedirect({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  useEffect(() => { location.replace(`/dashboard/events/${id}`); }, [id]);
  return null;
}
