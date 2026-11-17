"use client";
/**
 * Teste grátis configurado pelo dono no Super Admin. A landing e o cadastro leem de /public/trial: NADA do teste é fixo no site.
 * Se a API não responder, assumimos "sem teste" (melhor não prometer algo que não temos certeza).
 */
import { useEffect, useState } from "react";
import { api } from "./api";

export type Trial = { ready: boolean; enabled: boolean; days: number | null; limits: Record<string, any> };

export function useTrial(): Trial {
  const [s, setS] = useState<Trial>({ ready: false, enabled: false, days: null, limits: {} });
  useEffect(() => {
    api("/public/trial").then((r: any) => setS({ ready: true, enabled: !!r.enabled, days: r.days ?? null, limits: r.limits ?? {} }))
      .catch(() => setS({ ready: true, enabled: false, days: null, limits: {} }));
  }, []);
  return s;
}

type T = (k: string, p?: Record<string, any>) => string;
/** Resumo curto do teste, ex.: "1 evento(s) · 2 hora(s) de transmissão". Usado em frases da landing e do cadastro. */
export function trialHeadline(l: Record<string, any>, t: T): string {
  const parts: string[] = [];
  if ("included_events" in l) parts.push(l.included_events === null ? t("eventos ilimitados") : t("{n} evento(s)", { n: l.included_events }));
  if ("included_hours" in l) parts.push(l.included_hours === null ? t("horas de transmissão ilimitadas") : t("{n} hora(s) de transmissão", { n: l.included_hours }));
  return parts.join(" · ");
}
