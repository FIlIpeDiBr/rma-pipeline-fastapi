// Pequenos componentes e estilos compartilhados.
import { useState } from "react";
import type { CSSProperties, ReactNode } from "react";

import { MESES } from "./api";

export const fonteSerif = "'Source Serif 4', Georgia, serif";

export const cores = {
  primaria: "#2f9e54",       // verde principal
  primariaEscura: "#1f7a43",
  borda: "#e7ece7",
  inputBorda: "#d8e0d9",
  suave: "#f1f4f1",          // separadores de linha
  hover: "#f4f6f4",
  cabecalho: "#fafbfa",      // fundo do thead
  texto: "#45524b",
  heading: "#16231c",
  cinza: "#8a958c",
  headMuted: "#6b7a70",
  ok: "#1f7a43",
  erro: "#dc2626",
  ativo: "#eef6f0",
  chipBg: "#e8f3ec", chipFg: "#1f7a43",
  ambarBg: "#fef3e2", ambarFg: "#b45309",
  infoBg: "#eef2f6", infoFg: "#1f5a8a",
};

export const btn: CSSProperties = {
  display: "inline-flex", alignItems: "center", gap: 7, fontFamily: "inherit",
  padding: "8px 14px", borderRadius: 8, border: `1px solid ${cores.inputBorda}`,
  background: "white", color: cores.texto, cursor: "pointer", fontSize: 13, fontWeight: 500,
};
export const btnPrim: CSSProperties = {
  ...btn, background: cores.primaria, color: "white", border: "none",
  fontWeight: 600, fontSize: 13.5, padding: "9px 18px",
  boxShadow: "0 1px 2px rgba(31,122,67,.25)",
};
export const input: CSSProperties = {
  padding: "8px 12px", borderRadius: 8, border: `1px solid ${cores.inputBorda}`,
  fontSize: 13.5, color: cores.heading, background: "white", fontFamily: "inherit",
};

export const tabelaWrap: CSSProperties = {
  border: `1px solid ${cores.borda}`, borderRadius: 12, overflow: "hidden",
  background: "white", boxShadow: "0 1px 2px rgba(22,35,28,.04)",
};
export const thPlain: CSSProperties = {
  textAlign: "left", fontWeight: 600, color: cores.headMuted, fontSize: 12,
  letterSpacing: ".03em", textTransform: "uppercase", padding: "11px 16px",
  borderBottom: `1px solid ${cores.borda}`, background: cores.cabecalho,
};

export function Card({ titulo, children, acao }: { titulo: string; children: ReactNode; acao?: ReactNode }) {
  return (
    <section style={{
      border: `1px solid ${cores.borda}`, borderRadius: 12, padding: "1.1rem 1.35rem",
      marginBottom: "1.25rem", background: "white", boxShadow: "0 1px 2px rgba(22,35,28,.04)",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: ".75rem", gap: 16, flexWrap: "wrap" }}>
        <h2 style={{ margin: 0, fontSize: 19, fontFamily: fonteSerif, fontWeight: 600, color: cores.heading, letterSpacing: "-0.01em" }}>{titulo}</h2>
        {acao}
      </div>
      {children}
    </section>
  );
}

export function Aviso({ erro, ok }: { erro?: string; ok?: string }) {
  if (erro) {
    return <p style={{ color: cores.erro, margin: ".5rem 0", fontSize: 13.5 }}>⚠️ {erro}</p>;
  }
  if (ok) return <p style={{ color: cores.ok, margin: ".5rem 0", fontSize: 13.5 }}>✓ {ok}</p>;
  return null;
}

export function Badge({ tipo = "neutro", children }: {
  tipo?: "ok" | "alerta" | "erro" | "info" | "neutro"; children: ReactNode;
}) {
  const map: Record<string, { bg: string; fg: string }> = {
    ok: { bg: cores.chipBg, fg: cores.chipFg },
    alerta: { bg: cores.ambarBg, fg: cores.ambarFg },
    erro: { bg: "#fdeaea", fg: cores.erro },
    info: { bg: cores.infoBg, fg: cores.infoFg },
    neutro: { bg: cores.suave, fg: cores.headMuted },
  };
  const c = map[tipo];
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6, background: c.bg, color: c.fg,
      fontSize: 11.5, fontWeight: 600, padding: "5px 12px", borderRadius: 20, whiteSpace: "nowrap",
    }}>
      {children}
    </span>
  );
}

export function PeriodoSeletor({
  mes, ano, onMes, onAno,
}: { mes: number; ano: number; onMes: (m: number) => void; onAno: (a: number) => void }) {
  const meses = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];
  return (
    <span style={{ display: "inline-flex", gap: 8 }}>
      <select value={mes} onChange={(e) => onMes(Number(e.target.value))} style={input}>
        {meses.map((m, i) => <option key={i + 1} value={i + 1}>{m}</option>)}
      </select>
      <input type="number" value={ano} onChange={(e) => onAno(Number(e.target.value))}
             style={{ ...input, width: 90 }} />
    </span>
  );
}

export type Periodo = { mes: number; ano: number };

export function chavePeriodo(p: Periodo): string {
  return `${p.ano}-${String(p.mes).padStart(2, "0")}`;
}
export function rotuloPeriodo(p: Periodo): string {
  return `${MESES[p.mes] || p.mes}/${p.ano}`;
}

export function SeletorPeriodos({
  periodos, valor, onChange, vazio = "— sem períodos —",
}: {
  periodos: Periodo[]; valor: Periodo | null; onChange: (p: Periodo) => void; vazio?: string;
}) {
  if (periodos.length === 0) {
    return <select style={{ ...input, minWidth: 150 }} disabled><option>{vazio}</option></select>;
  }
  const sel = valor ? chavePeriodo(valor) : "";
  return (
    <select
      style={{ ...input, minWidth: 150 }}
      value={sel}
      onChange={(e) => {
        const p = periodos.find((x) => chavePeriodo(x) === e.target.value);
        if (p) onChange(p);
      }}
    >
      {!valor && <option value="">— período —</option>}
      {periodos.map((p) => (
        <option key={chavePeriodo(p)} value={chavePeriodo(p)}>{rotuloPeriodo(p)}</option>
      ))}
    </select>
  );
}

function _norm(s: string): string {
  return (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
}

export function pontuarBusca(texto: string, query: string): number {
  const t = _norm(texto);
  const q = _norm(query).trim();
  if (!q) return 1;
  if (t === q) return 1000;
  if (t.startsWith(q)) return 600 - t.length;
  const idx = t.indexOf(q);
  if (idx >= 0) return 300 - idx;
  let i = 0;
  for (const c of t) {
    if (c === q[i]) i += 1;
    if (i === q.length) break;
  }
  return i === q.length ? 60 - t.length : 0;
}

export function ordenarBestMatch<T>(itens: T[], query: string, chave: (x: T) => string): T[] {
  const alfa = (a: T, b: T) => chave(a).localeCompare(chave(b), "pt-BR");
  if (!query.trim()) return [...itens].sort(alfa);
  const scored = itens.map((x) => ({ x, s: pontuarBusca(chave(x), query) }));
  const match = scored.filter((o) => o.s > 0)
    .sort((a, b) => b.s - a.s || alfa(a.x, b.x)).map((o) => o.x);
  const resto = scored.filter((o) => o.s === 0).map((o) => o.x).sort(alfa);
  return [...match, ...resto];
}

export type OpcaoOrd = { valor: string; rotulo: string; digitar?: boolean };

export function ThOrdenavel({
  titulo, coluna, opcoes, ativoOpcao, onEscolher, texto, onTexto, style,
}: {
  titulo: string;
  coluna: string;
  opcoes: OpcaoOrd[];
  ativoOpcao: string | null;
  onEscolher: (coluna: string, opcao: string) => void;
  texto?: string;
  onTexto?: (t: string) => void;
  style?: CSSProperties;
}) {
  const [aberto, setAberto] = useState(false);
  const op = ativoOpcao ? opcoes.find((o) => o.valor === ativoOpcao) : null;

  return (
    <th
      style={{
        textAlign: "left", fontWeight: 600, fontSize: 12, letterSpacing: ".03em",
        textTransform: "uppercase", padding: "11px 16px", position: "relative", userSelect: "none",
        borderBottom: `1px solid ${cores.borda}`,
        background: op ? cores.ativo : cores.cabecalho,
        color: op ? cores.primariaEscura : cores.headMuted, ...style,
      }}
    >
      <span
        onClick={() => setAberto((v) => !v)}
        style={{ display: "inline-flex", alignItems: "center", gap: 4, cursor: "pointer" }}
      >
        {titulo}
        {op
          ? <span style={{ textTransform: "none", letterSpacing: 0, fontSize: 11, color: cores.primaria }}>· {op.rotulo}</span>
          : <span style={{ color: cores.cinza, fontSize: 12 }}>⌄</span>}
      </span>

      {op?.digitar && onTexto && (
        <input
          autoFocus
          value={texto ?? ""}
          onChange={(e) => onTexto(e.target.value)}
          placeholder={`digite o ${op.rotulo}…`}
          style={{ ...input, textTransform: "none", letterSpacing: 0, fontWeight: 400, marginLeft: 6, width: 130, padding: "3px 8px", fontSize: 12 }}
        />
      )}

      {aberto && (
        <>
          <div onClick={() => setAberto(false)} style={{ position: "fixed", inset: 0, zIndex: 10 }} />
          <div style={{
            position: "absolute", top: "100%", left: 0, zIndex: 11, marginTop: 2,
            background: "white", border: `1px solid ${cores.borda}`, borderRadius: 10,
            boxShadow: "0 8px 24px rgba(22,35,28,.14)", minWidth: 168, overflow: "hidden",
            fontWeight: 400, textTransform: "none", letterSpacing: 0,
          }}>
            {opcoes.map((o) => (
              <div
                key={o.valor}
                onClick={() => { onEscolher(coluna, o.valor); setAberto(false); }}
                style={{
                  padding: "9px 13px", cursor: "pointer", fontSize: 13,
                  background: o.valor === ativoOpcao ? cores.ativo : "white",
                  color: o.valor === ativoOpcao ? cores.primariaEscura : cores.texto,
                }}
                onMouseEnter={(e) => { e.currentTarget.style.background = cores.hover; }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = o.valor === ativoOpcao ? cores.ativo : "white";
                }}
              >
                {o.rotulo}
              </div>
            ))}
          </div>
        </>
      )}
    </th>
  );
}

export function Modal({ titulo, onFechar, children, largura = 540 }: {
  titulo: string; onFechar: () => void; children: ReactNode; largura?: number;
}) {
  return (
    <div
      onClick={onFechar}
      style={{
        position: "fixed", inset: 0, background: "rgba(22,35,28,.42)", zIndex: 50,
        display: "flex", alignItems: "flex-start", justifyContent: "center", padding: "6vh 1rem",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "white", borderRadius: 14, padding: "1.35rem 1.6rem",
          width: "100%", maxWidth: largura, maxHeight: "84vh", overflowY: "auto",
          boxShadow: "0 24px 64px rgba(22,35,28,.28)", border: `1px solid ${cores.borda}`,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
          <h3 style={{ margin: 0, fontSize: 18, fontFamily: fonteSerif, fontWeight: 600, color: cores.heading }}>{titulo}</h3>
          <button onClick={onFechar} style={{ ...btn, padding: "4px 9px", color: cores.headMuted }} title="Fechar">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function GraficoBarras({ dados, altura = 30 }: {
  dados: { rotulo: string; valor: number; texto: string }[];
  altura?: number;
}) {
  if (dados.length === 0) {
    return <p style={{ color: cores.cinza, fontSize: 13 }}>Selecione indicadores para montar o gráfico.</p>;
  }
  const maxAbs = Math.max(1, ...dados.map((d) => Math.abs(d.valor)));
  const larguraRotulo = 190;
  const larguraValor = 110;
  const larguraBarra = 420;
  const w = larguraRotulo + larguraBarra + larguraValor;
  const h = dados.length * altura + 8;
  const temNeg = dados.some((d) => d.valor < 0);
  const zeroX = larguraRotulo + (temNeg ? larguraBarra / 2 : 0);
  const escala = (temNeg ? larguraBarra / 2 : larguraBarra) / maxAbs;

  return (
    <div style={{ overflowX: "auto" }}>
      <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", maxWidth: w, height: h }}>
        {dados.map((d, i) => {
          const y = i * altura + 4;
          const comp = Math.abs(d.valor) * escala;
          const x = d.valor < 0 ? zeroX - comp : zeroX;
          return (
            <g key={i}>
              <text x={larguraRotulo - 8} y={y + altura / 2} textAnchor="end"
                    dominantBaseline="middle" fontSize="12" fill={cores.texto}>
                {d.rotulo.length > 30 ? d.rotulo.slice(0, 29) + "…" : d.rotulo}
              </text>
              <rect x={x} y={y + 5} width={Math.max(comp, 1)} height={altura - 13} rx="4"
                    fill={d.valor < 0 ? cores.erro : cores.primaria} opacity="0.9" />
              <text x={larguraRotulo + larguraBarra + 8} y={y + altura / 2} textAnchor="start"
                    dominantBaseline="middle" fontSize="12" fill={cores.heading}
                    style={{ fontVariantNumeric: "tabular-nums" }}>
                {d.texto}
              </text>
            </g>
          );
        })}
        <line x1={zeroX} y1={2} x2={zeroX} y2={dados.length * altura + 2}
              stroke={cores.borda} strokeWidth="1" />
      </svg>
    </div>
  );
}
