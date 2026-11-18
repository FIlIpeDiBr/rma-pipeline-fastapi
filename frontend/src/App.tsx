import { useEffect, useState } from "react";

import Definicoes from "./Definicoes";
import Documentos from "./Documentos";
import Email from "./Email";
import Empresas from "./Empresas";
import { iniciais } from "./formato";
import Indicadores from "./Indicadores";
import Relatorios from "./Relatorios";
import { cores, fonteSerif } from "./ui";

type Health = { status: string; db: string; storage: string };
type User = { oid: string; email: string; nome: string; org_id?: string };

const ABAS = [
  { id: "documentos", rotulo: "Documentos", comp: Documentos,
    d: "M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z", d2: "M13 2v7h7" },
  { id: "indicadores", rotulo: "Indicadores", comp: Indicadores,
    d: "M3 3v18h18", d2: "M7 18v-5M12 18v-9M17 18v-13" },
  { id: "relatorios", rotulo: "Relatórios", comp: Relatorios,
    d: "M5 3h14a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z", d2: "M8 8h8M8 12h8M8 16h5" },
  { id: "empresas", rotulo: "Empresas", comp: Empresas,
    d: "M4 21V7l8-4 8 4v14", d2: "M9 21v-6h6v6M9 11h.01M15 11h.01" },
  { id: "definicoes", rotulo: "Definições", comp: Definicoes,
    d: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
    d2: "M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 8 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H2a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 3.6 8a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H8a1.65 1.65 0 0 0 1-1.51V2a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V8a1.65 1.65 0 0 0 1.51 1H22a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" },
  { id: "email", rotulo: "Email", comp: Email,
    d: "M4 4h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z", d2: "m2 7 10 6 10-6" },
] as const;

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [aba, setAba] = useState<string>("documentos");

  useEffect(() => {
    fetch("/healthz").then((r) => r.json()).then(setHealth).catch(() => setHealth(null));
    fetch("/api/me").then((r) => (r.ok ? r.json() : null)).then(setUser).catch(() => setUser(null));
  }, []);

  const saude = (v?: string) => (v === "ok" ? "✅" : "⚠️");
  const Ativa = ABAS.find((a) => a.id === aba)?.comp ?? Documentos;

  return (
    <main style={{ maxWidth: 1180, margin: "0 auto", padding: "26px 32px 64px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 24, flexWrap: "wrap" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 11 }}>
          <div style={{
            width: 38, height: 38, borderRadius: 10, background: cores.primaria, color: "white",
            display: "flex", alignItems: "center", justifyContent: "center", flex: "none",
            fontFamily: fonteSerif, fontWeight: 600, fontSize: 17,
          }}>R</div>
          <div style={{ lineHeight: 1.2 }}>
            <div style={{ fontFamily: fonteSerif, fontWeight: 600, fontSize: 20, color: cores.heading, letterSpacing: "-0.01em" }}>
              RMA
            </div>
            <div style={{ fontSize: 12, color: cores.cinza }}>Relatório Mensal de Acompanhamento</div>
          </div>
        </div>

        {user ? (
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <span style={{ fontSize: 12, color: cores.cinza }} title="Saúde do sistema">
              DB {saude(health?.db)} · Storage {saude(health?.storage)}
            </span>
            <div style={{ display: "flex", alignItems: "center", gap: 10, paddingLeft: 14, borderLeft: `1px solid ${cores.borda}` }}>
              <div style={{
                width: 38, height: 38, borderRadius: "50%", background: cores.primaria, color: "white",
                display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 13, flex: "none",
              }}>{iniciais(user.nome, user.email)}</div>
              <div style={{ lineHeight: 1.3 }}>
                <div style={{ fontSize: 13, color: cores.heading, fontWeight: 600, whiteSpace: "nowrap" }}>
                  {user.nome || user.email}
                </div>
                <a href="/auth/logout" style={{ fontSize: 12, color: cores.cinza, textDecoration: "none" }}>Sair</a>
              </div>
            </div>
          </div>
        ) : (
          <a href="/auth/login" style={{ ...linkBtn }}>Entrar com Microsoft</a>
        )}
      </div>

      {!user ? (
        <p style={{ marginTop: "2.5rem", color: cores.texto }}>
          Faça login para usar o portal. <a href="/auth/login" style={{ color: cores.primariaEscura }}>Entrar com Microsoft</a>
        </p>
      ) : (
        <>
          <nav style={{ display: "flex", gap: 2, borderBottom: `1px solid ${cores.borda}`, margin: "20px 0 26px", overflowX: "auto" }}>
            {ABAS.map((a) => {
              const ativo = a.id === aba;
              return (
                <button
                  key={a.id}
                  onClick={() => setAba(a.id)}
                  style={{
                    display: "inline-flex", alignItems: "center", gap: 7, fontFamily: "inherit",
                    padding: "0 13px 12px", border: "none", background: "none", cursor: "pointer",
                    fontSize: 14, whiteSpace: "nowrap", marginBottom: -1,
                    borderBottom: `2.5px solid ${ativo ? cores.primaria : "transparent"}`,
                    color: ativo ? cores.heading : "#5a6b62", fontWeight: ativo ? 600 : 500,
                  }}
                >
                  <svg width="17" height="17" viewBox="0 0 24 24" fill="none"
                       stroke={ativo ? cores.primaria : cores.cinza} strokeWidth="2"
                       strokeLinecap="round" strokeLinejoin="round" style={{ flex: "none" }}>
                    <path d={a.d} />
                    <path d={a.d2} />
                  </svg>
                  {a.rotulo}
                </button>
              );
            })}
          </nav>
          <Ativa />
        </>
      )}
    </main>
  );
}

const linkBtn = {
  display: "inline-flex", alignItems: "center", background: cores.primaria, color: "white",
  textDecoration: "none", fontWeight: 600, fontSize: 13.5, padding: "9px 18px", borderRadius: 8,
  boxShadow: "0 1px 2px rgba(31,122,67,.25)",
} as const;
