// Helpers de chamada à API (mesma origem; envia o cookie de sessão do login).
async function handle(r: Response) {
  if (!r.ok) {
    let msg = `Erro ${r.status}`;
    try {
      const j = await r.json();
      if (j.detail) msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* sem corpo JSON */
    }
    throw new Error(msg);
  }
  const ct = r.headers.get("content-type") || "";
  return ct.includes("application/json") ? r.json() : r.text();
}

function qs(params?: Record<string, unknown>): string {
  if (!params) return "";
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

export const api = {
  get: (path: string, params?: Record<string, unknown>) =>
    fetch(`/api${path}${qs(params)}`).then(handle),
  post: (path: string, params?: Record<string, unknown>) =>
    fetch(`/api${path}${qs(params)}`, { method: "POST" }).then(handle),
  postJson: (path: string, body: unknown) =>
    fetch(`/api${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(handle),
  patchJson: (path: string, body: unknown) =>
    fetch(`/api${path}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(handle),
  del: (path: string) => fetch(`/api${path}`, { method: "DELETE" }).then(handle),
  postForm: (path: string, form: FormData) =>
    fetch(`/api${path}`, { method: "POST", body: form }).then(handle),
};

export const MESES = [
  "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];
