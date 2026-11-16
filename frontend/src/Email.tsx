import { useCallback, useEffect, useState } from "react";

import { api } from "./api";
import { Aviso, btn, btnPrim, Card, cores, input } from "./ui";

type St = { configurado: boolean; caixa: string | null; auto: boolean; pendentes: number };
type Anexo = {
  id: string; nome: string; tamanho: number; content_type: string;
  suportado: boolean; incluido: boolean;
};
type Msg = {
  id: string; remetente: string; assunto: string; corpo: string;
  recebido_em: string; anexos: Anexo[];
};

const LIMITE_CORPO = 280;

function kb(n: number): string {
  return n < 1024 ? `${n} B` : `${(n / 1024).toFixed(0)} KB`;
}
function fmtData(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString("pt-BR", {
    day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export default function Email() {
  const [st, setSt] = useState<St | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [sel, setSel] = useState<Record<string, Set<string>>>({});
  const [expandido, setExpandido] = useState<Set<string>>(new Set());
  const [erro, setErro] = useState("");
  const [aviso, setAviso] = useState("");
  const [buscando, setBuscando] = useState(false);

  const carregarStatus = useCallback(() => {
    api.get("/email/status").then(setSt).catch((e) => setErro((e as Error).message));
  }, []);

  const carregarMsgs = useCallback(async () => {
    try {
      const d = await api.get("/email/messages");
      setMsgs(d.mensagens);
      setSel((prev) => {
        const novo: Record<string, Set<string>> = {};
        for (const m of d.mensagens as Msg[]) {
          novo[m.id] = prev[m.id] ?? new Set(m.anexos.filter((a) => a.suportado).map((a) => a.id));
        }
        return novo;
      });
    } catch (e) {
      setErro((e as Error).message);
    }
  }, []);

  useEffect(() => {
    carregarStatus();
    carregarMsgs();
  }, [carregarStatus, carregarMsgs]);

  async function toggleAuto() {
    if (!st) return;
    try {
      await api.patchJson("/email/settings", { auto: !st.auto });
      carregarStatus();
    } catch (e) {
      setErro((e as Error).message);
    }
  }

  async function buscar() {
    setErro(""); setAviso(""); setBuscando(true);
    try {
      await api.post("/email/sync");
      setAviso("Busca disparada — atualizando em instantes…");
      setTimeout(() => { carregarMsgs(); carregarStatus(); }, 3000);
      setTimeout(() => { carregarMsgs(); carregarStatus(); setBuscando(false); }, 7000);
    } catch (e) {
      setErro((e as Error).message);
      setBuscando(false);
    }
  }

  function toggleAnexo(msgId: string, attId: string) {
    setSel((prev) => {
      const s = new Set(prev[msgId] ?? []);
      if (s.has(attId)) s.delete(attId); else s.add(attId);
      return { ...prev, [msgId]: s };
    });
  }

  async function importar(m: Msg) {
    setErro(""); setAviso("");
    const ids = Array.from(sel[m.id] ?? []);
    if (ids.length === 0) {
      setErro("Selecione ao menos um anexo para importar.");
      return;
    }
    try {
      const r = await api.postJson(`/email/messages/${m.id}/import`, { attachment_ids: ids });
      setAviso(`${r.importados} documento(s) importado(s) — acompanhe na aba Documentos.`);
      await carregarMsgs();
      carregarStatus();
    } catch (e) {
      setErro((e as Error).message);
    }
  }

  async function ignorar(m: Msg) {
    try {
      await api.post(`/email/messages/${m.id}/ignore`);
      await carregarMsgs();
      carregarStatus();
    } catch (e) {
      setErro((e as Error).message);
    }
  }

  return (
    <>
      <Card
        titulo="Recepção por email"
        acao={
          <button style={btnPrim} disabled={!st?.configurado || buscando} onClick={buscar}>
            {buscando ? "Buscando…" : "Buscar e-mails agora"}
          </button>
        }
      >
        {st && (
          <div style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap", alignItems: "center", color: cores.texto }}>
            <span>Integração: {st.configurado ? "✅ configurada" : "⚠️ não configurada"}</span>
            <span>Caixa: {st.caixa || "—"}</span>
            <span>Pendentes de revisão: <strong>{st.pendentes}</strong></span>
            <label style={{ display: "inline-flex", gap: 6, alignItems: "center", cursor: "pointer" }}>
              <input type="checkbox" checked={st.auto} onChange={toggleAuto} />
              Varredura automática (a cada ~5 min)
            </label>
          </div>
        )}
        <Aviso erro={erro} ok={aviso} />
        <p style={{ color: cores.cinza, fontSize: 12, marginTop: 8 }}>
          Os e-mails ficam aqui para revisão — nada é importado automaticamente. Escolha os anexos
          e clique em importar para enviá-los ao processamento.
        </p>
      </Card>

      {msgs.length === 0 ? (
        <p style={{ color: cores.cinza }}>Nenhum e-mail pendente de revisão.</p>
      ) : (
        msgs.map((m) => {
          const aberto = expandido.has(m.id);
          const longo = m.corpo.length > LIMITE_CORPO;
          const corpo = aberto || !longo ? m.corpo : m.corpo.slice(0, LIMITE_CORPO) + "…";
          return (
            <Card key={m.id} titulo={m.assunto || "(sem assunto)"}>
              <div style={{ fontSize: 13, color: cores.cinza, marginBottom: 6 }}>
                De <strong style={{ color: cores.texto }}>{m.remetente || "—"}</strong>
                {m.recebido_em && <> · {fmtData(m.recebido_em)}</>}
              </div>
              {m.corpo && (
                <p style={{ whiteSpace: "pre-wrap", margin: "0 0 8px", color: cores.texto }}>
                  {corpo}{" "}
                  {longo && (
                    <button
                      onClick={() =>
                        setExpandido((prev) => {
                          const s = new Set(prev);
                          if (s.has(m.id)) s.delete(m.id); else s.add(m.id);
                          return s;
                        })}
                      style={{ border: "none", background: "none", color: cores.primaria, cursor: "pointer", padding: 0 }}
                    >
                      {aberto ? "ler menos" : "ler mais"}
                    </button>
                  )}
                </p>
              )}
              <div style={{ borderTop: `1px solid ${cores.borda}`, paddingTop: 8 }}>
                <strong style={{ fontSize: 13 }}>Anexos</strong>
                {m.anexos.map((a) => (
                  <label key={a.id} style={{
                    display: "flex", gap: 8, alignItems: "center", padding: "3px 0",
                    color: a.suportado ? cores.texto : cores.cinza,
                  }}>
                    <input type="checkbox" disabled={!a.suportado}
                           checked={sel[m.id]?.has(a.id) ?? false}
                           onChange={() => toggleAnexo(m.id, a.id)} />
                    {a.nome} <span style={{ color: cores.cinza, fontSize: 12 }}>({kb(a.tamanho)})</span>
                    {!a.suportado && <span style={{ fontSize: 12 }}>— formato não suportado</span>}
                  </label>
                ))}
              </div>
              <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
                <button style={btnPrim} onClick={() => importar(m)}>Importar selecionados</button>
                <button style={btn} onClick={() => ignorar(m)}>Ignorar e-mail</button>
              </div>
            </Card>
          );
        })
      )}
    </>
  );
}
