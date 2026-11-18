import { useEffect, useState } from "react";

import { api } from "./api";
import { ordenarBestMatch } from "./formato";
import {
  Aviso, btn, btnPrim, Card, cores, input, type OpcaoOrd, ThOrdenavel,
} from "./ui";

type Emp = { id: string; nome: string; cnpj: string; grupo: string };

const OPC_EMPRESA: OpcaoOrd[] = [
  { valor: "az", rotulo: "alfabética ↓" }, { valor: "za", rotulo: "alfabética ↑" },
  { valor: "nome", rotulo: "nome", digitar: true }, { valor: "grupo", rotulo: "grupo", digitar: true },
];
const OPC_GRUPO: OpcaoOrd[] = [
  { valor: "az", rotulo: "alfabética ↓" }, { valor: "za", rotulo: "alfabética ↑" },
];

export default function Empresas() {
  const [emps, setEmps] = useState<Emp[]>([]);
  const [erro, setErro] = useState("");
  const [grupos, setGrupos] = useState<Record<string, string>>({});
  const [salvo, setSalvo] = useState("");
  const [ord, setOrd] = useState<{ coluna: string; opcao: string } | null>(null);
  const [busca, setBusca] = useState("");

  async function carregar() {
    setErro("");
    try {
      const d = await api.get("/companies");
      setEmps(d.empresas);
      setGrupos(Object.fromEntries(d.empresas.map((e: Emp) => [e.id, e.grupo])));
    } catch (e) {
      setErro((e as Error).message);
    }
  }
  useEffect(() => {
    carregar();
  }, []);

  async function salvar(id: string) {
    setErro("");
    setSalvo("");
    try {
      await api.patchJson(`/companies/${id}`, { grupo: grupos[id] ?? "" });
      setSalvo("Grupo atualizado.");
      await carregar();
    } catch (e) {
      setErro((e as Error).message);
    }
  }

  function escolher(coluna: string, opcao: string) {
    setOrd({ coluna, opcao });
    setBusca("");
  }
  const opcaoDe = (coluna: string) => (ord?.coluna === coluna ? ord.opcao : null);

  function ordenar(lista: Emp[]): Emp[] {
    if (!ord) return lista;
    const arr = [...lista];
    if (ord.coluna === "empresa") {
      if (ord.opcao === "nome") return ordenarBestMatch(arr, busca, (e) => e.nome);
      if (ord.opcao === "grupo") return ordenarBestMatch(arr, busca, (e) => e.grupo);
      arr.sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
      return ord.opcao === "za" ? arr.reverse() : arr;
    }
    if (ord.coluna === "grupo") {
      arr.sort((a, b) => (a.grupo || "").localeCompare(b.grupo || "", "pt-BR"));
      return ord.opcao === "za" ? arr.reverse() : arr;
    }
    return arr;
  }

  const lista = ordenar(emps);

  return (
    <Card titulo={`Empresas (${emps.length})`} acao={<button style={btn} onClick={carregar}>Atualizar</button>}>
      <Aviso erro={erro} ok={salvo} />
      {emps.length === 0 ? (
        <p style={{ color: cores.cinza }}>Nenhuma empresa ainda — elas surgem ao processar documentos.</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: `2px solid ${cores.borda}` }}>
              <ThOrdenavel titulo="Empresa" coluna="empresa" opcoes={OPC_EMPRESA}
                           ativoOpcao={opcaoDe("empresa")} onEscolher={escolher}
                           texto={busca} onTexto={setBusca} />
              <th>CNPJ</th>
              <ThOrdenavel titulo="Grupo" coluna="grupo" opcoes={OPC_GRUPO}
                           ativoOpcao={opcaoDe("grupo")} onEscolher={escolher} />
              <th></th>
            </tr>
          </thead>
          <tbody>
            {lista.map((e) => (
              <tr key={e.id} style={{ borderBottom: `1px solid ${cores.suave}` }}>
                <td style={{ padding: "6px 4px" }}>{e.nome}</td>
                <td>{e.cnpj || "—"}</td>
                <td>
                  <input style={{ ...input, width: 180 }} value={grupos[e.id] ?? ""}
                         placeholder="(sem grupo)"
                         onChange={(ev) => setGrupos({ ...grupos, [e.id]: ev.target.value })} />
                </td>
                <td>
                  {(grupos[e.id] ?? "") !== e.grupo && (
                    <button style={btnPrim} onClick={() => salvar(e.id)}>Salvar</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p style={{ color: cores.cinza, fontSize: 12, marginTop: 8 }}>
        Empresas com o mesmo nome de grupo são consolidadas nos indicadores e relatórios de grupo.
      </p>
    </Card>
  );
}
