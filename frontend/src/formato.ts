// Funções puras de formatação, busca e ordenação usadas pelas telas.
// Sem React e sem rede, para serem testadas isoladamente (formato.test.ts).

export const MESES = [
  "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];

export type Periodo = { mes: number; ano: number };

/** Monta a query string, deixando de fora parâmetros vazios. */
export function qs(params?: Record<string, unknown>): string {
  if (!params) return "";
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

const DATA_HORA: Intl.DateTimeFormatOptions = {
  day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
};

/** Data e hora em pt-BR. Vazio vira `vazio`; texto que não é data volta como veio. */
export function fmtDataHora(iso?: string | null, vazio = "—"): string {
  if (!iso) return vazio;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("pt-BR", DATA_HORA);
}

export function fmtBytes(n: number): string {
  if (!n) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

/** "03/2025", ou travessão quando o documento ainda não tem período. */
export function periodoCurto(d: { mes: number | null; ano: number | null }): string {
  if (!d.mes || !d.ano) return "—";
  return `${String(d.mes).padStart(2, "0")}/${d.ano}`;
}

/** Chave ordenável do período: "2025-03". */
export function chavePeriodo(p: Periodo): string {
  return `${p.ano}-${String(p.mes).padStart(2, "0")}`;
}

export function rotuloPeriodo(p: Periodo): string {
  return `${MESES[p.mes] || p.mes}/${p.ano}`;
}

/** O documento ainda está no pipeline (a barra de progresso faz sentido). */
export function emAndamento(status: string): boolean {
  return status === "RECEBIDO" || status === "TRIANDO" || status === "EXTRAINDO";
}

export type GrupoStatus = "concluido" | "erro" | "andamento";

/** Agrupa o status do relatório nas três opções do filtro da tabela. */
export function grupoStatus(status: string): GrupoStatus {
  if (status === "CONCLUIDO") return "concluido";
  return status === "ERRO" ? "erro" : "andamento";
}

/** Duas letras para o avatar: primeira e última palavra do nome, ou o começo do e-mail. */
export function iniciais(nome: string, email: string): string {
  const base = (nome || "").trim() || (email || "").trim() || "?";
  const partes = base.split(/\s+/);
  if (partes.length === 1) return partes[0].slice(0, 2).toUpperCase();
  return (partes[0][0] + partes[partes.length - 1][0]).toUpperCase();
}

/** Minúsculas e sem acentos, para comparar o que a pessoa digitou. */
export function normalizar(s: string): string {
  return (s || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

/**
 * Nota de relevância de `texto` para a busca `query` (0 = não casa).
 * Igual > começa com > contém > letras na ordem (busca aproximada).
 */
export function pontuarBusca(texto: string, query: string): number {
  const t = normalizar(texto);
  const q = normalizar(query).trim();
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

/** Ordena pelo que mais casa com a busca; o que não casa vai para o fim, em ordem alfabética. */
export function ordenarBestMatch<T>(itens: T[], query: string, chave: (x: T) => string): T[] {
  const alfa = (a: T, b: T) => chave(a).localeCompare(chave(b), "pt-BR");
  if (!query.trim()) return [...itens].sort(alfa);
  const scored = itens.map((x) => ({ x, s: pontuarBusca(chave(x), query) }));
  const match = scored.filter((o) => o.s > 0)
    .sort((a, b) => b.s - a.s || alfa(a.x, b.x)).map((o) => o.x);
  const resto = scored.filter((o) => o.s === 0).map((o) => o.x).sort(alfa);
  return [...match, ...resto];
}
