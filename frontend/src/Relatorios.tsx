import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "./api";
import {
  Aviso, btn, btnPrim, Card, cores, input, type OpcaoOrd, ordenarBestMatch,
  type Periodo, SeletorPeriodos, ThOrdenavel,
} from "./ui";

type Tpl = { id: string; nome: string; suporta_grupo: boolean };
type Emp = { id: string; nome: string; grupo: string };
type PeriodosData = { empresas: Record<string, Periodo[]>; grupos: Record<string, Periodo[]> };
type Rep = {
  id: string; mes: number; ano: number; status: string; progresso: number;
  etapa: string; erro: string; nome_arquivo: string; pronto: boolean;
  grupo: string | null; entidade?: string; criado_em?: string | null; anual?: boolean;
};

const CORES_ST: Record<string, string> = {
  FILA: "#6b7280", GERANDO: "#2563eb", CONCLUIDO: "#16a34a", ERRO: "#dc2626",
};

const OPC: Record<string, OpcaoOrd[]> = {
  gerado: [{ valor: "recente", rotulo: "mais recente" }, { valor: "antigo", rotulo: "mais antigo" }],
  entidade: [
    { valor: "az", rotulo: "alfabética ↓" }, { valor: "za", rotulo: "alfabética ↑" },
    { valor: "nome", rotulo: "nome", digitar: true },
  ],
  periodo: [{ valor: "recente", rotulo: "mais recente" }, { valor: "antigo", rotulo: "mais antigo" }],
  status: [
    { valor: "concluido", rotulo: "concluído" }, { valor: "andamento", rotulo: "em andamento" },
    { valor: "erro", rotulo: "com erro" },
  ],
};

const grupoStatus = (s: string) => (s === "CONCLUIDO" ? "concluido" : s === "ERRO" ? "erro" : "andamento");
const entidadeDe = (r: { entidade?: string; grupo: string | null }) => r.entidade || r.grupo || "";

function fmtData(iso?: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR", {
    day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export default function Relatorios() {
  const [tpls, setTpls] = useState<Tpl[]>([]);
  const [emps, setEmps] = useState<Emp[]>([]);
  const [periodos, setPeriodos] = useState<PeriodosData>({ empresas: {}, grupos: {} });
  const [reports, setReports] = useState<Rep[]>([]);
  const [templateId, setTemplateId] = useState("");
  const [modo, setModo] = useState<"empresa" | "grupo">("empresa");
  const [companyId, setCompanyId] = useState("");
  const [grupo, setGrupo] = useState("");
  const [per, setPer] = useState<Periodo | null>(null);
  const [erro, setErro] = useState("");
  const [ord, setOrd] = useState<{ coluna: string; opcao: string } | null>(null);
  const [busca, setBusca] = useState("");
  const [periodicidade, setPeriodicidade] = useState<"mensal" | "anual">("mensal");
  const [anoAnual, setAnoAnual] = useState<number | null>(null);
  const timer = useRef<number | null>(null);

  async function carregarReports() {
    try {
      const d = await api.get("/reports");
      setReports(d.relatorios);
    } catch {
      /* mantém */
    }
  }
  useEffect(() => {
    api.get("/templates").then((d) => {
      setTpls(d.templates);
      if (d.templates[0]) setTemplateId(d.templates[0].id);
    }).catch((e) => setErro((e as Error).message));
    api.get("/companies").then((d) => setEmps(d.empresas)).catch(() => {});
    api.get("/companies/periodos").then(setPeriodos).catch(() => {});
    carregarReports();
    timer.current = window.setInterval(carregarReports, 4000);
    return () => { if (timer.current) window.clearInterval(timer.current); };
  }, []);

  const grupos = useMemo(
    () => Array.from(new Set(emps.map((e) => e.grupo).filter(Boolean))),
    [emps],
  );
  const tpl = tpls.find((t) => t.id === templateId);
  const periodosDisp = useMemo<Periodo[]>(
    () => (modo === "grupo" ? periodos.grupos[grupo] : periodos.empresas[companyId]) || [],
    [modo, grupo, companyId, periodos],
  );
  const anosDisp = useMemo(
    () => Array.from(new Set(periodosDisp.map((p) => p.ano))).sort((a, b) => b - a),
    [periodosDisp],
  );
  const entidadeOk = modo === "grupo" ? !!grupo : !!companyId;

  useEffect(() => {
    setPer(periodosDisp.length ? periodosDisp[periodosDisp.length - 1] : null);
    const anos = periodosDisp.map((p) => p.ano);
    setAnoAnual(anos.length ? Math.max(...anos) : null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modo, companyId, grupo, periodosDisp.length]);

  async function gerar() {
    setErro("");
    const params: Record<string, unknown> = { template_id: templateId };
    if (periodicidade === "anual") {
      if (!anoAnual) return;
      params.ano = anoAnual;
      params.anual = true;
    } else {
      if (!per) return;
      params.mes = per.mes;
      params.ano = per.ano;
    }
    if (modo === "grupo") params.grupo = grupo; else params.company_id = companyId;
    try {
      await api.post("/reports", params);
      await carregarReports();
    } catch (e) {
      setErro((e as Error).message);
    }
  }

  const podeGerar = !!templateId && entidadeOk
    && (periodicidade === "anual" ? !!anoAnual : !!per)
    && (modo !== "grupo" || !!tpl?.suporta_grupo);

  function escolher(coluna: string, opcao: string) {
    setOrd({ coluna, opcao });
    setBusca("");
  }
  const opcaoDe = (coluna: string) => (ord?.coluna === coluna ? ord.opcao : null);

  function ordenar(arr0: Rep[]): Rep[] {
    if (!ord) return arr0;
    const arr = [...arr0];
    switch (ord.coluna) {
      case "gerado":
        return arr.sort((a, b) => {
          const c = (a.criado_em || "").localeCompare(b.criado_em || "");
          return ord.opcao === "recente" ? -c : c;
        });
      case "periodo": {
        const k = (r: Rep) => r.ano * 100 + r.mes;
        return arr.sort((a, b) => (ord.opcao === "recente" ? k(b) - k(a) : k(a) - k(b)));
      }
      case "entidade":
        if (ord.opcao === "nome") return ordenarBestMatch(arr, busca, entidadeDe);
        arr.sort((a, b) => entidadeDe(a).localeCompare(entidadeDe(b), "pt-BR"));
        return ord.opcao === "za" ? arr.reverse() : arr;
      case "status":
        return arr.sort((a, b) =>
          (grupoStatus(a.status) === ord.opcao ? 0 : 1) - (grupoStatus(b.status) === ord.opcao ? 0 : 1));
      default:
        return arr;
    }
  }

  const lista = ordenar(reports);

  return (
    <>
      <Card titulo="Gerar relatório">
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <select style={{ ...input, minWidth: 180 }} value={templateId} onChange={(e) => setTemplateId(e.target.value)}>
            {tpls.map((t) => <option key={t.id} value={t.id}>{t.nome}</option>)}
          </select>
          <select style={input} value={modo} onChange={(e) => setModo(e.target.value as "empresa" | "grupo")}>
            <option value="empresa">Empresa</option>
            <option value="grupo">Grupo</option>
          </select>
          {modo === "empresa" ? (
            <select style={{ ...input, minWidth: 220 }} value={companyId} onChange={(e) => setCompanyId(e.target.value)}>
              <option value="">— empresa —</option>
              {emps.map((e) => <option key={e.id} value={e.id}>{e.nome}</option>)}
            </select>
          ) : (
            <select style={{ ...input, minWidth: 220 }} value={grupo} onChange={(e) => setGrupo(e.target.value)}>
              <option value="">— grupo —</option>
              {grupos.map((g) => <option key={g} value={g}>{g}</option>)}
            </select>
          )}
          <select style={input} value={periodicidade}
                  onChange={(e) => setPeriodicidade(e.target.value as "mensal" | "anual")}>
            <option value="mensal">Mensal</option>
            <option value="anual">Anual</option>
          </select>
          {periodicidade === "anual" ? (
            <select style={{ ...input, width: 120 }} value={anoAnual ?? ""}
                    onChange={(e) => setAnoAnual(Number(e.target.value))}>
              <option value="">— ano —</option>
              {anosDisp.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          ) : (
            <SeletorPeriodos
              periodos={periodosDisp}
              valor={per}
              onChange={setPer}
              vazio={entidadeOk ? "— sem documentos —" : "— período —"}
            />
          )}
          <button style={btnPrim} disabled={!podeGerar} onClick={gerar}>Gerar</button>
        </div>
        {entidadeOk && periodosDisp.length === 0 && (
          <p style={{ color: cores.cinza, fontSize: 12 }}>
            Esta {modo} não possui períodos com documentos.
          </p>
        )}
        {modo === "grupo" && tpl && !tpl.suporta_grupo && (
          <p style={{ color: cores.cinza, fontSize: 12 }}>Este template não suporta grupo.</p>
        )}
        <Aviso erro={erro} />
      </Card>

      <Card titulo="Relatórios" acao={<button style={btn} onClick={carregarReports}>Atualizar</button>}>
        {reports.length === 0 ? (
          <p style={{ color: cores.cinza }}>Nenhum relatório ainda.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ textAlign: "left", borderBottom: `2px solid ${cores.borda}` }}>
                <ThOrdenavel titulo="Gerado" coluna="gerado" opcoes={OPC.gerado}
                             ativoOpcao={opcaoDe("gerado")} onEscolher={escolher} />
                <ThOrdenavel titulo="Empresa/Grupo" coluna="entidade" opcoes={OPC.entidade}
                             ativoOpcao={opcaoDe("entidade")} onEscolher={escolher}
                             texto={busca} onTexto={setBusca} />
                <ThOrdenavel titulo="Período" coluna="periodo" opcoes={OPC.periodo}
                             ativoOpcao={opcaoDe("periodo")} onEscolher={escolher} />
                <ThOrdenavel titulo="Status" coluna="status" opcoes={OPC.status}
                             ativoOpcao={opcaoDe("status")} onEscolher={escolher} />
                <th></th>
              </tr>
            </thead>
            <tbody>
              {lista.map((r) => (
                <tr key={r.id} style={{ borderBottom: `1px solid ${cores.suave}` }}>
                  <td style={{ padding: "6px 4px", whiteSpace: "nowrap", color: cores.cinza }}>
                    {fmtData(r.criado_em)}
                  </td>
                  <td>{r.entidade || r.grupo || "—"}</td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    {r.anual ? `Exercício ${r.ano}` : `${String(r.mes).padStart(2, "0")}/${r.ano}`}
                  </td>
                  <td style={{ minWidth: 160 }}>
                    <span style={{ color: CORES_ST[r.status] || cores.texto, fontWeight: 600 }}>{r.status}</span>
                    {(r.status === "GERANDO" || r.status === "FILA") && (
                      <>
                        <progress value={r.progresso} max={100} style={{ width: "100%" }} />
                        <small style={{ color: cores.cinza }}>{r.etapa}</small>
                      </>
                    )}
                    {r.status === "ERRO" && r.erro && (
                      <div style={{ color: cores.erro, fontSize: 12 }}>{r.erro}</div>
                    )}
                  </td>
                  <td>{r.pronto && <a href={`/api/reports/${r.id}/download`}>baixar</a>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </>
  );
}
