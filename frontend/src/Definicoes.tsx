import { useEffect, useState } from "react";

import { api } from "./api";
import { Aviso, btn, btnPrim, Card, cores, input, type OpcaoOrd, ThOrdenavel } from "./ui";

type Def = { key: string; label: string; formula: string; formato: string };

const FMT_ROTULO: Record<string, string> = { rs: "R$", pct: "%", indice: "índice" };

const OPC_AZ: OpcaoOrd[] = [
  { valor: "az", rotulo: "alfabética ↓" }, { valor: "za", rotulo: "alfabética ↑" },
];
const OPC_FMT: OpcaoOrd[] = [
  { valor: "rs", rotulo: "R$" }, { valor: "pct", rotulo: "%" }, { valor: "indice", rotulo: "índice" },
];

export default function Definicoes() {
  const [defs, setDefs] = useState<Def[]>([]);
  const [erro, setErro] = useState("");
  const [ok, setOk] = useState("");
  const [nova, setNova] = useState<Def>({ key: "", label: "", formula: "", formato: "rs" });
  const [editKey, setEditKey] = useState<string | null>(null);
  const [draft, setDraft] = useState<Def | null>(null);
  const [ord, setOrd] = useState<{ coluna: string; opcao: string } | null>(null);

  async function carregar() {
    try {
      const d = await api.get("/indicators/definitions");
      setDefs(d.definicoes);
    } catch (e) {
      setErro((e as Error).message);
    }
  }
  useEffect(() => {
    carregar();
  }, []);

  async function salvar(d: Def) {
    setErro(""); setOk("");
    try {
      await api.postJson("/indicators/definitions", d);
      setOk(`Definição "${d.key}" salva (passa a valer da próxima geração).`);
      setEditKey(null); setDraft(null);
      await carregar();
    } catch (e) {
      setErro((e as Error).message);
    }
  }
  async function excluir(key: string) {
    setErro(""); setOk("");
    try {
      await api.del(`/indicators/definitions/${key}`);
      setOk(`Override "${key}" removido (volta ao padrão do sistema).`);
      setEditKey(null); setDraft(null);
      await carregar();
    } catch (e) {
      setErro((e as Error).message);
    }
  }

  function iniciarEdicao(d: Def) {
    setEditKey(d.key);
    setDraft({ ...d });
    setOk(""); setErro("");
  }
  function cancelar() {
    setEditKey(null);
    setDraft(null);
  }

  function escolher(coluna: string, opcao: string) {
    setOrd({ coluna, opcao });
  }
  const opcaoDe = (coluna: string) => (ord?.coluna === coluna ? ord.opcao : null);

  function ordenar(lista: Def[]): Def[] {
    if (!ord) return lista;
    const arr = [...lista];
    if (ord.coluna === "chave") {
      arr.sort((a, b) => a.key.localeCompare(b.key, "pt-BR"));
      return ord.opcao === "za" ? arr.reverse() : arr;
    }
    if (ord.coluna === "rotulo") {
      arr.sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));
      return ord.opcao === "za" ? arr.reverse() : arr;
    }
    if (ord.coluna === "formato") {
      return arr.sort((a, b) => (a.formato === ord.opcao ? 0 : 1) - (b.formato === ord.opcao ? 0 : 1));
    }
    return arr;
  }

  const lista = ordenar(defs);

  return (
    <Card titulo="Definições de indicadores" acao={<button style={btn} onClick={carregar}>Atualizar</button>}>
      <Aviso erro={erro} ok={ok} />
      <p style={{ color: cores.cinza, fontSize: 12 }}>
        Use apenas as <strong>chaves</strong> dos indicadores e contas (ex.: <code>lucro_liquido</code>,{" "}
        <code>passivo_circulante</code>), operações <code>+ − * /</code>, potência <code>x**y</code>,{" "}
        raiz <code>x/-y</code> e parênteses. Salvar cria um override da sua organização sobre o padrão do sistema.
      </p>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: `2px solid ${cores.borda}` }}>
            <ThOrdenavel titulo="Chave" coluna="chave" opcoes={OPC_AZ}
                         ativoOpcao={opcaoDe("chave")} onEscolher={escolher} />
            <ThOrdenavel titulo="Rótulo" coluna="rotulo" opcoes={OPC_AZ}
                         ativoOpcao={opcaoDe("rotulo")} onEscolher={escolher} />
            <th>Fórmula</th>
            <ThOrdenavel titulo="Formato" coluna="formato" opcoes={OPC_FMT}
                         ativoOpcao={opcaoDe("formato")} onEscolher={escolher} />
            <th></th>
          </tr>
        </thead>
        <tbody>
          {lista.map((d) => {
            const ed = editKey === d.key ? draft : null;
            return (
              <tr key={d.key} style={{ borderBottom: `1px solid ${cores.suave}` }}>
                <td style={{ padding: "4px", fontFamily: "monospace" }}>{d.key}</td>
                {ed ? (
                  <>
                    <td>
                      <input style={{ ...input, width: "100%" }} value={ed.label}
                             onChange={(e) => setDraft({ ...ed, label: e.target.value })} />
                    </td>
                    <td>
                      <input style={{ ...input, width: "100%", fontFamily: "monospace" }} value={ed.formula}
                             onChange={(e) => setDraft({ ...ed, formula: e.target.value })} />
                    </td>
                    <td>
                      <select style={input} value={ed.formato}
                              onChange={(e) => setDraft({ ...ed, formato: e.target.value })}>
                        <option value="rs">R$</option><option value="pct">%</option><option value="indice">índice</option>
                      </select>
                    </td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <button style={{ ...btnPrim, padding: "4px 8px" }} title="Salvar edições"
                              onClick={() => salvar(ed)}>✓</button>{" "}
                      <button style={{ ...btn, padding: "4px 8px" }} title="Cancelar"
                              onClick={cancelar}>✕</button>{" "}
                      <button style={{ ...btn, padding: "4px 8px", color: cores.erro, borderColor: "#fecaca" }}
                              title="Apagar indicador" onClick={() => excluir(d.key)}>🗑</button>
                    </td>
                  </>
                ) : (
                  <>
                    <td style={{ color: cores.texto }}>{d.label}</td>
                    <td style={{ fontFamily: "monospace", color: d.formula ? cores.texto : cores.cinza }}>
                      {d.formula || "— (calculado pelo motor)"}
                    </td>
                    <td>{FMT_ROTULO[d.formato] || d.formato}</td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <button style={{ ...btn, padding: "4px 8px" }} title="Editar"
                              onClick={() => iniciarEdicao(d)}>✏️</button>
                    </td>
                  </>
                )}
              </tr>
            );
          })}
          <tr>
            <td><input style={{ ...input, width: 110 }} placeholder="nova_chave" value={nova.key}
                       onChange={(e) => setNova({ ...nova, key: e.target.value })} /></td>
            <td><input style={{ ...input, width: "100%" }} placeholder="Rótulo" value={nova.label}
                       onChange={(e) => setNova({ ...nova, label: e.target.value })} /></td>
            <td><input style={{ ...input, width: "100%", fontFamily: "monospace" }} placeholder="fórmula"
                       value={nova.formula} onChange={(e) => setNova({ ...nova, formula: e.target.value })} /></td>
            <td>
              <select style={input} value={nova.formato} onChange={(e) => setNova({ ...nova, formato: e.target.value })}>
                <option value="rs">R$</option><option value="pct">%</option><option value="indice">índice</option>
              </select>
            </td>
            <td>
              <button style={btnPrim} disabled={!nova.key || !nova.label}
                      onClick={() => salvar(nova)}>Adicionar</button>
            </td>
          </tr>
        </tbody>
      </table>
    </Card>
  );
}
