import { describe, expect, it } from "vitest";

import {
  chavePeriodo, emAndamento, fmtBytes, fmtDataHora, grupoStatus, iniciais, normalizar,
  ordenarBestMatch, periodoCurto, pontuarBusca, qs, rotuloPeriodo,
} from "./formato";

describe("qs", () => {
  it("devolve vazio sem parâmetros", () => {
    expect(qs()).toBe("");
    expect(qs({})).toBe("");
  });

  it("deixa de fora undefined, null e texto vazio, mas mantém zero e false", () => {
    expect(qs({ mes: 3, ano: 2025, grupo: "", empresa: undefined, x: null })).toBe("?mes=3&ano=2025");
    expect(qs({ limite: 0, anual: false })).toBe("?limite=0&anual=false");
  });

  it("codifica acentos e espaços", () => {
    expect(qs({ grupo: "Grupo São João" })).toBe("?grupo=Grupo+S%C3%A3o+Jo%C3%A3o");
  });
});

describe("fmtDataHora", () => {
  it("formata em pt-BR", () => {
    // Sem fuso na string: é lida como hora local, então o resultado não depende da máquina.
    expect(fmtDataHora("2025-03-07T14:05:00")).toMatch(/^07\/03\/2025,? 14:05$/);
  });

  it("usa o texto de vazio quando não há data", () => {
    expect(fmtDataHora(null)).toBe("—");
    expect(fmtDataHora(undefined)).toBe("—");
    expect(fmtDataHora("", "")).toBe("");
  });

  it("devolve o texto original quando não é uma data", () => {
    expect(fmtDataHora("ontem à tarde")).toBe("ontem à tarde");
  });
});

describe("fmtBytes", () => {
  it("escolhe a unidade pelo tamanho", () => {
    expect(fmtBytes(0)).toBe("—");
    expect(fmtBytes(512)).toBe("512 B");
    expect(fmtBytes(1536)).toBe("1.5 KB");
    expect(fmtBytes(5 * 1024 * 1024)).toBe("5.0 MB");
  });
});

describe("períodos", () => {
  it("periodoCurto preenche o mês com zero e aceita documento sem período", () => {
    expect(periodoCurto({ mes: 3, ano: 2025 })).toBe("03/2025");
    expect(periodoCurto({ mes: null, ano: 2025 })).toBe("—");
    expect(periodoCurto({ mes: 3, ano: null })).toBe("—");
  });

  it("chavePeriodo ordena como texto na ordem do calendário", () => {
    const chaves = [{ mes: 11, ano: 2024 }, { mes: 2, ano: 2025 }, { mes: 10, ano: 2025 }]
      .map(chavePeriodo);
    expect(chaves).toEqual(["2024-11", "2025-02", "2025-10"]);
    expect([...chaves].sort()).toEqual(chaves);
  });

  it("rotuloPeriodo usa o nome do mês e cai no número se o mês for inválido", () => {
    expect(rotuloPeriodo({ mes: 3, ano: 2025 })).toBe("Março/2025");
    expect(rotuloPeriodo({ mes: 13, ano: 2025 })).toBe("13/2025");
  });
});

describe("status", () => {
  it("emAndamento só enquanto o documento está no pipeline", () => {
    expect(["RECEBIDO", "TRIANDO", "EXTRAINDO"].every(emAndamento)).toBe(true);
    expect(emAndamento("PROCESSADO")).toBe(false);
    expect(emAndamento("ERRO")).toBe(false);
  });

  it("grupoStatus junta FILA e GERANDO em andamento", () => {
    expect(grupoStatus("CONCLUIDO")).toBe("concluido");
    expect(grupoStatus("ERRO")).toBe("erro");
    expect(grupoStatus("FILA")).toBe("andamento");
    expect(grupoStatus("GERANDO")).toBe("andamento");
  });
});

describe("iniciais", () => {
  it("usa a primeira e a última palavra do nome", () => {
    expect(iniciais("Maria da Silva Souza", "m@exemplo.com")).toBe("MS");
  });

  it("com uma palavra só, usa as duas primeiras letras", () => {
    expect(iniciais("Maria", "")).toBe("MA");
  });

  it("sem nome, usa o e-mail; sem nada, um ponto de interrogação", () => {
    expect(iniciais("", "joao@exemplo.com")).toBe("JO");
    expect(iniciais("", "")).toBe("?");
  });

  it("não quebra com nome só de espaços", () => {
    expect(iniciais("   ", "ana@exemplo.com")).toBe("AN");
    expect(iniciais("   ", "")).toBe("?");
  });
});

describe("busca", () => {
  it("normalizar tira acentos e caixa", () => {
    expect(normalizar("São João Comércio")).toBe("sao joao comercio");
  });

  it("pontua igual > começa com > contém > aproximada > nada", () => {
    const igual = pontuarBusca("Padaria", "padaria");
    const comeca = pontuarBusca("Padaria Central", "padaria");
    const contem = pontuarBusca("Grande Padaria", "padaria");
    const aproximada = pontuarBusca("Padaria", "pdr");
    const nada = pontuarBusca("Oficina", "padaria");
    expect(igual).toBeGreaterThan(comeca);
    expect(comeca).toBeGreaterThan(contem);
    expect(contem).toBeGreaterThan(aproximada);
    expect(aproximada).toBeGreaterThan(0);
    expect(nada).toBe(0);
  });

  it("ignora acento dos dois lados", () => {
    expect(pontuarBusca("Comércio São João", "comercio sao")).toBeGreaterThan(0);
    expect(pontuarBusca("Comercio Sao Joao", "Comércio")).toBeGreaterThan(0);
  });

  it("busca vazia casa com tudo", () => {
    expect(pontuarBusca("Qualquer", "  ")).toBe(1);
  });
});

describe("ordenarBestMatch", () => {
  const nomes = ["Oficina Zeta", "Padaria Central", "Grande Padaria", "Ábaco Contábil", "Padaria"];
  const ordenar = (q: string) => ordenarBestMatch(nomes, q, (x) => x);

  it("sem busca, ordem alfabética em pt-BR (acento não vai para o fim)", () => {
    expect(ordenar("")).toEqual([
      "Ábaco Contábil", "Grande Padaria", "Oficina Zeta", "Padaria", "Padaria Central",
    ]);
  });

  it("com busca, o que casa melhor vem primeiro e o resto fica no fim em ordem alfabética", () => {
    expect(ordenar("padaria")).toEqual([
      "Padaria", "Padaria Central", "Grande Padaria", "Ábaco Contábil", "Oficina Zeta",
    ]);
  });

  it("não altera a lista original", () => {
    const copia = [...nomes];
    ordenar("padaria");
    expect(nomes).toEqual(copia);
  });
});
