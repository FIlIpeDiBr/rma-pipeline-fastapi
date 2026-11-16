import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "./api";
import {
  Aviso, btn, btnPrim, Card, cores, GraficoBarras, input, type Periodo, SeletorPeriodos,
} from "./ui";

type Emp = { id: string; nome: string; grupo: string };
type Ind = { key: string; label: string; valor: number | null; valor_formatado: string };
type PeriodosData = { empresas: Record<string, Periodo[]>; grupos: Record<string, Periodo[]> };

export default function Indicadores() {
  const [emps, setEmps] = useState<Emp[]>([]);
  const [periodos, setPeriodos] = useState<PeriodosData>({ empresas: {}, grupos: {} });
  const [modo, setModo] = useState<"empresa" | "grupo">("empresa");
  const [companyId, setCompanyId] = useState("");
  const [grupo, setGrupo] = useState("");
  const [per, setPer] = useState<Periodo | null>(null);
  const [inds, setInds] = useState<Ind[]>([]);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [erro, setErro] = useState("");
  const [msg, setMsg] = useState("");
  const [carregando, setCarregando] = useState(false);
  const [recalculando, setRecalculando] = useState(false);

  useEffect(() => {
    api.get("/companies").then((d) => setEmps(d.empresas)).catch(() => {});
    api.get("/companies/periodos").then(setPeriodos).catch(() => {});
  }, []);

  const grupos = useMemo(
    () => Array.from(new Set(emps.map((e) => e.grupo).filter(Boolean))),
    [emps],
  );
  const periodosDisp = useMemo<Periodo[]>(
    () => (modo === "grupo" ? periodos.grupos[grupo] : periodos.empresas[companyId]) || [],
    [modo, grupo, companyId, periodos],
  );
  const entidadeOk = modo === "grupo" ? !!grupo : !!companyId;

  // Ao trocar de entidade, seleciona o período mais recente disponível (ou nenhum).
  useEffect(() => {
    setInds([]);
    setSel(new Set());
    setMsg("");
    setErro("");
    setPer(periodosDisp.length ? periodosDisp[periodosDisp.length - 1] : null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modo, companyId, grupo, periodosDisp.length]);

  const buscar = useCallback(async () => {
    if (!entidadeOk || !per) return;
    setErro(""); setMsg(""); setCarregando(true);
    try {
      const params = modo === "grupo"
        ? { grupo, mes: per.mes, ano: per.ano }
        : { company_id: companyId, mes: per.mes, ano: per.ano };
      const d = await api.get("/indicators", params);
      setInds(d.indicadores);
      if (d.indicadores.length === 0) setMsg("Sem indicadores calculados para este período. Use 'Recalcular'.");
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setCarregando(false);
    }
  }, [entidadeOk, per, modo, grupo, companyId]);

  // Carrega automaticamente quando entidade + período estão definidos.
  useEffect(() => { buscar(); }, [buscar]);

  async function recalcular() {
    if (!entidadeOk || !per) return;
    setErro(""); setMsg(""); setRecalculando(true);
    try {
      if (modo === "grupo") await api.post("/indicators/generate-group", { grupo, mes: per.mes, ano: per.ano });
      else await api.post("/indicators/generate", { company_id: companyId, mes: per.mes, ano: per.ano });
      await buscar();
      setMsg("Indicadores recalculados.");
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setRecalculando(false);
    }
  }

  function toggleSel(key: string) {
    setSel((s) => {
      const n = new Set(s);
      if (n.has(key)) n.delete(key); else n.add(key);
      return n;
    });
  }

  const dadosGrafico = inds
    .filter((i) => sel.has(i.key) && i.valor !== null)
    .map((i) => ({ rotulo: i.label, valor: i.valor as number, texto: i.valor_formatado }));

  return (
    <Card titulo="Indicadores">
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
        <select style={input} value={modo} onChange={(e) => setModo(e.target.value as "empresa" | "grupo")}>
          <option value="empresa">Empresa</option>
          <option value="grupo">Grupo</option>
        </select>
        {modo === "empresa" ? (
          <select style={{ ...input, minWidth: 240 }} value={companyId} onChange={(e) => setCompanyId(e.target.value)}>
            <option value="">— selecione a empresa —</option>
            {emps.map((e) => <option key={e.id} value={e.id}>{e.nome}</option>)}
          </select>
        ) : (
          <select style={{ ...input, minWidth: 240 }} value={grupo} onChange={(e) => setGrupo(e.target.value)}>
            <option value="">— selecione o grupo —</option>
            {grupos.map((g) => <option key={g} value={g}>{g}</option>)}
          </select>
        )}
        <SeletorPeriodos
          periodos={periodosDisp}
          valor={per}
          onChange={setPer}
          vazio={entidadeOk ? "— sem documentos —" : "— período —"}
        />
        <button style={btn} disabled={!entidadeOk || !per || recalculando} onClick={recalcular}>
          {recalculando ? "Recalculando…" : "Recalcular"}
        </button>
      </div>

      {entidadeOk && periodosDisp.length === 0 && (
        <p style={{ color: cores.cinza, fontSize: 13 }}>
          Esta {modo} ainda não possui documentos cadastrados — envie balancetes/DREs na aba Documentos.
        </p>
      )}
      <Aviso erro={erro} ok={msg} />

      {carregando ? (
        <p>Carregando…</p>
      ) : inds.length > 0 ? (
        <>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <tbody>
              {inds.map((i) => (
                <tr key={i.key} style={{ borderBottom: `1px solid ${cores.suave}` }}>
                  <td style={{ padding: "5px 4px", color: cores.texto }}>{i.label}</td>
                  <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{i.valor_formatado}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div style={{ marginTop: 20, borderTop: `1px solid ${cores.borda}`, paddingTop: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
              <strong style={{ fontSize: 14 }}>Gráfico do período</strong>
              <span style={{ display: "flex", gap: 6 }}>
                <button style={{ ...btn, padding: "3px 8px", fontSize: 12 }}
                        onClick={() => setSel(new Set(inds.filter((i) => i.valor !== null).map((i) => i.key)))}>
                  Selecionar todos
                </button>
                <button style={{ ...btn, padding: "3px 8px", fontSize: 12 }} onClick={() => setSel(new Set())}>
                  Limpar
                </button>
              </span>
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, margin: "10px 0 14px" }}>
              {inds.map((i) => {
                const ativo = sel.has(i.key);
                const ok = i.valor !== null;
                return (
                  <button
                    key={i.key}
                    disabled={!ok}
                    onClick={() => toggleSel(i.key)}
                    title={ok ? i.label : "Sem valor neste período"}
                    style={{
                      ...btn, padding: "3px 9px", fontSize: 12, opacity: ok ? 1 : 0.4,
                      background: ativo ? cores.primaria : "white",
                      color: ativo ? "white" : cores.texto,
                      border: ativo ? "none" : `1px solid ${cores.borda}`,
                    }}
                  >
                    {i.label}
                  </button>
                );
              })}
            </div>
            <GraficoBarras dados={dadosGrafico} />
          </div>
        </>
      ) : null}
    </Card>
  );
}
