import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "./api";
import {
  emAndamento, fmtBytes, fmtDataHora, MESES, ordenarBestMatch, periodoCurto,
} from "./formato";
import {
  Badge, btn, btnPrim, cores, fonteSerif, Modal, type OpcaoOrd,
  tabelaWrap, ThOrdenavel, thPlain,
} from "./ui";

type Doc = {
  id: string;
  nome_arquivo: string;
  empresa: string;
  tipo: string | null;
  mes: number | null;
  ano: number | null;
  status: string;
  mensagem: string;
  aviso?: string;
  tamanho: number;
  content_type?: string;
  origem?: string;
  metodo_envio?: string;
  enviado_por?: string;
  remetente?: string;
  criado_em?: string | null;
  atualizado_em?: string | null;
};

type Evento = { etapa: string; progresso: number; status: string; mensagem: string };
type Detalhe = Doc & { eventos?: Evento[] };
type Progresso = { etapa: string; progresso: number; status: string };
type Emp = { id: string; nome: string; grupo: string };

const CORES: Record<string, string> = {
  RECEBIDO: cores.headMuted, TRIANDO: cores.infoFg, EXTRAINDO: cores.infoFg,
  PROCESSADO: cores.primariaEscura, ERRO: cores.erro,
};
type BadgeTipo = "ok" | "alerta" | "erro" | "info" | "neutro";
const TIPO_STATUS: Record<string, BadgeTipo> = {
  RECEBIDO: "neutro", TRIANDO: "info", EXTRAINDO: "info",
  PROCESSADO: "ok", ERRO: "erro",
};

const OPC: Record<string, OpcaoOrd[]> = {
  submetido: [{ valor: "recente", rotulo: "mais recente" }, { valor: "antigo", rotulo: "mais antigo" }],
  arquivo: [{ valor: "az", rotulo: "alfabética ↓" }, { valor: "za", rotulo: "alfabética ↑" }],
  empresa: [
    { valor: "az", rotulo: "alfabética ↓" }, { valor: "za", rotulo: "alfabética ↑" },
    { valor: "nome", rotulo: "nome", digitar: true }, { valor: "grupo", rotulo: "grupo", digitar: true },
  ],
  periodo: [{ valor: "recente", rotulo: "mais recente" }, { valor: "antigo", rotulo: "mais antigo" }],
  tipo: [{ valor: "balanco", rotulo: "balanço" }, { valor: "dre", rotulo: "DRE" }],
  status: [{ valor: "proc", rotulo: "processado" }, { valor: "naoproc", rotulo: "não-processado" }],
};

export default function Documentos() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [grupoPorNome, setGrupoPorNome] = useState<Record<string, string>>({});
  const [carregando, setCarregando] = useState(true);
  const [enviando, setEnviando] = useState(false);
  const [arraste, setArraste] = useState(false);
  const [erroUpload, setErroUpload] = useState<string>("");
  const [prog, setProg] = useState<Record<string, Progresso>>({});
  const [ord, setOrd] = useState<{ coluna: string; opcao: string } | null>(null);
  const [busca, setBusca] = useState("");
  const [abertoId, setAbertoId] = useState<string | null>(null);
  const [detalhe, setDetalhe] = useState<Detalhe | null>(null);
  const [confirmaExcluir, setConfirmaExcluir] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const carregar = useCallback(async () => {
    try {
      const r = await fetch("/api/documents");
      if (!r.ok) throw new Error(`${r.status}`);
      const data = await r.json();
      setDocs(data.documentos || []);
    } catch {
      /* mantém lista atual */
    } finally {
      setCarregando(false);
    }
    try {
      const d = await api.get("/companies");
      setGrupoPorNome(Object.fromEntries((d.empresas as Emp[]).map((e) => [e.nome, e.grupo])));
    } catch {
      /* opcional */
    }
  }, []);

  useEffect(() => {
    carregar();
    const es = new EventSource("/api/events/stream");
    es.onmessage = (ev) => {
      try {
        const d = JSON.parse(ev.data);
        if (!d.document_id) return;
        setProg((p) => ({ ...p, [d.document_id]: { etapa: d.etapa, progresso: d.progresso, status: d.status } }));
        if (d.status === "ok" || d.status === "erro") carregar();
      } catch {
        /* heartbeat */
      }
    };
    es.onerror = () => {};
    return () => es.close();
  }, [carregar]);

  async function enviar(files: FileList | File[]) {
    const lista = Array.from(files);
    if (lista.length === 0) return;
    setEnviando(true);
    setErroUpload("");
    try {
      const fd = new FormData();
      lista.forEach((f) => fd.append("arquivos", f));
      const r = await fetch("/api/documents/upload", { method: "POST", body: fd });
      if (!r.ok) throw new Error(`Falha no upload (${r.status})`);
      await carregar();
    } catch (e) {
      setErroUpload(e instanceof Error ? e.message : "Falha no upload");
    } finally {
      setEnviando(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function reprocessar(id: string) {
    await fetch(`/api/documents/${id}/reprocess`, { method: "POST" });
    await carregar();
    if (abertoId === id) abrirDetalhe(id);
  }

  async function excluir(id: string) {
    await api.del(`/documents/${id}`);
    fecharModal();
    await carregar();
  }

  async function abrirDetalhe(id: string) {
    setAbertoId(id);
    setConfirmaExcluir(false);
    const base = docs.find((d) => d.id === id) || null;
    setDetalhe(base);
    try {
      const det = await api.get(`/documents/${id}`);
      setDetalhe(det);
    } catch {
      /* mantém o resumo já exibido */
    }
  }
  function fecharModal() {
    setAbertoId(null);
    setDetalhe(null);
    setConfirmaExcluir(false);
  }

  function escolher(coluna: string, opcao: string) {
    setOrd({ coluna, opcao });
    setBusca("");
  }
  const grupoDe = (nome: string) => grupoPorNome[nome] || "";

  function ordenar(lista: Doc[]): Doc[] {
    if (!ord) return lista;
    const arr = [...lista];
    switch (ord.coluna) {
      case "submetido":
        return arr.sort((a, b) => {
          const c = (a.criado_em || "").localeCompare(b.criado_em || "");
          return ord.opcao === "recente" ? -c : c;
        });
      case "periodo": {
        const k = (d: Doc) => (d.ano || 0) * 100 + (d.mes || 0);
        return arr.sort((a, b) => (ord.opcao === "recente" ? k(b) - k(a) : k(a) - k(b)));
      }
      case "arquivo": {
        arr.sort((a, b) => a.nome_arquivo.localeCompare(b.nome_arquivo, "pt-BR"));
        return ord.opcao === "za" ? arr.reverse() : arr;
      }
      case "empresa":
        if (ord.opcao === "nome") return ordenarBestMatch(arr, busca, (d) => d.empresa || "");
        if (ord.opcao === "grupo") return ordenarBestMatch(arr, busca, (d) => grupoDe(d.empresa));
        arr.sort((a, b) => (a.empresa || "").localeCompare(b.empresa || "", "pt-BR"));
        return ord.opcao === "za" ? arr.reverse() : arr;
      case "tipo": {
        const alvo = ord.opcao === "balanco" ? "BALANCO" : "DRE";
        return arr.sort((a, b) => (a.tipo === alvo ? 0 : 1) - (b.tipo === alvo ? 0 : 1));
      }
      case "status": {
        const proc = (d: Doc) => (d.status === "PROCESSADO" ? 1 : 0);
        return arr.sort((a, b) =>
          ord.opcao === "proc" ? proc(b) - proc(a) : proc(a) - proc(b));
      }
      default:
        return arr;
    }
  }

  const opcaoDe = (coluna: string) => (ord?.coluna === coluna ? ord.opcao : null);
  const lista = ordenar(docs);

  return (
    <section>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ margin: "0 0 4px", fontFamily: fonteSerif, fontWeight: 600, fontSize: 28, color: cores.heading, letterSpacing: "-0.01em", lineHeight: 1.12 }}>
          Documentos
        </h1>
        <p style={{ margin: 0, color: cores.cinza, fontSize: 14 }}>
          Envie balancetes e DREs para processamento automático.
        </p>
      </div>

      <div
        onDragOver={(e) => { e.preventDefault(); setArraste(true); }}
        onDragLeave={() => setArraste(false)}
        onDrop={(e) => { e.preventDefault(); setArraste(false); enviar(e.dataTransfer.files); }}
        onClick={() => inputRef.current?.click()}
        style={{
          border: `1.5px dashed ${arraste ? cores.primaria : "#c2d2c6"}`, borderRadius: 10,
          padding: "32px 24px", textAlign: "center", cursor: "pointer",
          background: arraste ? cores.ativo : "#f7faf7", transition: "border-color .15s, background .15s",
        }}
      >
        <div style={{ width: 44, height: 44, borderRadius: 10, background: cores.chipBg, display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 12px" }}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke={cores.primariaEscura}
               strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" />
          </svg>
        </div>
        <div style={{ fontWeight: 600, color: cores.heading, fontSize: 15, marginBottom: 2 }}>
          {enviando ? "Enviando…" : "Arraste arquivos aqui ou clique para selecionar"}
        </div>
        <div style={{ color: cores.cinza, fontSize: 13 }}>PDF, Excel (.xlsx, .xlsm), CSV ou imagem</div>
        <input ref={inputRef} type="file" multiple accept=".pdf,.xlsx,.xlsm,.csv,image/*"
               style={{ display: "none" }}
               onChange={(e) => e.target.files && enviar(e.target.files)} />
      </div>
      {erroUpload && <p style={{ color: cores.erro }}>⚠️ {erroUpload}</p>}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", margin: "28px 0 12px" }}>
        <strong style={{ color: cores.heading, fontSize: 15 }}>{docs.length} documento(s)</strong>
        <button style={btn} onClick={carregar}>Atualizar</button>
      </div>

      {carregando ? (
        <p>Carregando…</p>
      ) : docs.length === 0 ? (
        <p style={{ color: cores.cinza }}>Nenhum documento ainda. Envie o primeiro acima.</p>
      ) : (
        <div style={tabelaWrap}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13.5 }}>
          <thead>
            <tr>
              <ThOrdenavel titulo="Submetido" coluna="submetido" opcoes={OPC.submetido}
                           ativoOpcao={opcaoDe("submetido")} onEscolher={escolher} />
              <ThOrdenavel titulo="Arquivo" coluna="arquivo" opcoes={OPC.arquivo}
                           ativoOpcao={opcaoDe("arquivo")} onEscolher={escolher} />
              <ThOrdenavel titulo="Empresa" coluna="empresa" opcoes={OPC.empresa}
                           ativoOpcao={opcaoDe("empresa")} onEscolher={escolher}
                           texto={busca} onTexto={setBusca} />
              <ThOrdenavel titulo="Tipo" coluna="tipo" opcoes={OPC.tipo}
                           ativoOpcao={opcaoDe("tipo")} onEscolher={escolher} />
              <ThOrdenavel titulo="Período" coluna="periodo" opcoes={OPC.periodo}
                           ativoOpcao={opcaoDe("periodo")} onEscolher={escolher} />
              <ThOrdenavel titulo="Status" coluna="status" opcoes={OPC.status}
                           ativoOpcao={opcaoDe("status")} onEscolher={escolher} />
              <th style={{ ...thPlain, textAlign: "center" }}>Detalhes</th>
            </tr>
          </thead>
          <tbody>
            {lista.map((d) => {
              const p = prog[d.id];
              const mostrarBarra = emAndamento(d.status) && p && p.progresso < 100;
              return (
                <tr key={d.id} style={{ borderBottom: `1px solid ${cores.suave}`, verticalAlign: "top" }}>
                  <td style={{ padding: "11px 16px", whiteSpace: "nowrap", color: cores.cinza }}>
                    {fmtDataHora(d.criado_em)}
                  </td>
                  <td style={{ padding: "11px 16px", maxWidth: 220, wordBreak: "break-word", color: cores.heading, fontWeight: 500 }}>{d.nome_arquivo}</td>
                  <td style={{ padding: "11px 16px", color: cores.texto }}>{d.empresa || "—"}</td>
                  <td style={{ padding: "11px 16px", color: cores.texto }}>{d.tipo || "—"}</td>
                  <td style={{ padding: "11px 16px", color: cores.texto }}>{periodoCurto(d)}</td>
                  <td style={{ padding: "11px 16px", minWidth: 150 }}>
                    <Badge tipo={TIPO_STATUS[d.status] || "neutro"}>{d.status}</Badge>
                    {mostrarBarra && (
                      <>
                        <progress value={p.progresso} max={100} style={{ width: "100%", marginTop: 6 }} />
                        <small style={{ color: cores.cinza }}>{p.etapa}</small>
                      </>
                    )}
                    {d.status === "ERRO" && d.mensagem && (
                      <div style={{ color: cores.erro, fontSize: 12, marginTop: 4 }}>{d.mensagem}</div>
                    )}
                  </td>
                  <td style={{ padding: "11px 16px", textAlign: "center" }}>
                    <button style={{ ...btn, padding: "6px 9px" }} title="Ver detalhes"
                            onClick={() => abrirDetalhe(d.id)}>🔍</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>
      )}

      {abertoId && detalhe && (
        <Modal titulo="Detalhes do documento" onFechar={fecharModal}>
          <dl style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: "6px 16px", margin: 0, fontSize: 14 }}>
            <Linha rotulo="Arquivo" valor={detalhe.nome_arquivo} />
            <Linha rotulo="Método de envio" valor={detalhe.metodo_envio || (detalhe.origem === "EMAIL" ? "E-mail" : "Upload manual")} />
            <Linha rotulo="Quem enviou" valor={detalhe.enviado_por || "—"} />
            <Linha rotulo="Empresa" valor={detalhe.empresa || "—"} />
            <Linha rotulo="Tipo" valor={detalhe.tipo || "—"} />
            <Linha rotulo="Período" valor={detalhe.mes && detalhe.ano ? `${MESES[detalhe.mes]}/${detalhe.ano}` : "—"} />
            <Linha rotulo="Status" valor={detalhe.status} cor={CORES[detalhe.status]} />
            <Linha rotulo="Tamanho" valor={fmtBytes(detalhe.tamanho)} />
            <Linha rotulo="Submetido em" valor={fmtDataHora(detalhe.criado_em)} />
            <Linha rotulo="Atualizado em" valor={fmtDataHora(detalhe.atualizado_em)} />
          </dl>

          {detalhe.aviso && (
            <p style={{
              color: "#b45309", background: "#fef3c7", border: "1px solid #fde68a",
              borderRadius: 6, padding: "6px 10px", fontSize: 13, marginTop: 10,
            }}>
              ⚠️ {detalhe.aviso}
            </p>
          )}

          {detalhe.status === "ERRO" && detalhe.mensagem && (
            <p style={{ color: cores.erro, fontSize: 13, marginTop: 10 }}>{detalhe.mensagem}</p>
          )}

          {detalhe.eventos && detalhe.eventos.length > 0 && (
            <details style={{ marginTop: 12 }}>
              <summary style={{ cursor: "pointer", color: cores.cinza, fontSize: 13 }}>Histórico de processamento</summary>
              <ul style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 13, color: cores.texto }}>
                {detalhe.eventos.map((e, i) => (
                  <li key={i}>{e.etapa} — {e.status}{e.mensagem ? ` (${e.mensagem})` : ""}</li>
                ))}
              </ul>
            </details>
          )}

          <div style={{ display: "flex", gap: 8, marginTop: 18, flexWrap: "wrap", alignItems: "center" }}>
            {(detalhe.status === "ERRO" || detalhe.status === "PROCESSADO") && (
              <button style={btn} onClick={() => reprocessar(detalhe.id)} title="Reprocessar">↻ Reprocessar</button>
            )}
            <a href={`/api/documents/${detalhe.id}/download`} style={{ ...btn, textDecoration: "none", color: cores.texto }}>⬇ Baixar</a>
            {!confirmaExcluir ? (
              <button style={{ ...btn, color: cores.erro, borderColor: "#fecaca", marginLeft: "auto" }}
                      onClick={() => setConfirmaExcluir(true)} title="Excluir">🗑 Excluir</button>
            ) : (
              <span style={{ marginLeft: "auto", display: "inline-flex", gap: 8, alignItems: "center" }}>
                <span style={{ fontSize: 12, color: cores.erro }}>Apaga o documento e todos os registros derivados.</span>
                <button style={btn} onClick={() => setConfirmaExcluir(false)}>Cancelar</button>
                <button style={{ ...btnPrim, background: cores.erro }} onClick={() => excluir(detalhe.id)}>Confirmar exclusão</button>
              </span>
            )}
          </div>
        </Modal>
      )}
    </section>
  );
}

function Linha({ rotulo, valor, cor }: { rotulo: string; valor: string; cor?: string }) {
  return (
    <>
      <dt style={{ color: cores.cinza }}>{rotulo}</dt>
      <dd style={{ margin: 0, color: cor || cores.texto, fontWeight: cor ? 600 : 400 }}>{valor}</dd>
    </>
  );
}
