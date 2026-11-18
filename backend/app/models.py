"""Modelos do domínio.

Passo 2 entregou orgs/users. O Passo 3 acrescenta o núcleo de ingestão:
companies, documents, balance_lines, dre_lines, ai_calls e job_events.
Indicadores e grupos chegam nos Passos 4-5.

Os índices são declarados em `__table_args__` com os mesmos nomes e colunas das migrations,
que são a fonte de verdade do banco. Um teste de integração compara os dois lados.
"""

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# -- Status do documento no pipeline -----------------------------------------
# RECEBIDO -> TRIANDO -> EXTRAINDO -> PROCESSADO | ERRO
STATUS_RECEBIDO = "RECEBIDO"
STATUS_TRIANDO = "TRIANDO"
STATUS_EXTRAINDO = "EXTRAINDO"
STATUS_PROCESSADO = "PROCESSADO"
STATUS_ERRO = "ERRO"

TIPO_BALANCO = "BALANCO"
TIPO_DRE = "DRE"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class Org(Base):
    __tablename__ = "orgs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(200), unique=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Varredura automática da caixa rma@ (toggle pelo site).
    email_poll_ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_org", "org_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"))
    entra_oid: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str] = mapped_column(String(320))
    nome: Mapped[str] = mapped_column(String(200), default="")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Company(Base):
    """Cliente do escritório. `nome_canonico` (sem acentos/espaços) é único por org."""

    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("org_id", "nome_canonico", name="uq_company_org_canon"),
        Index("ix_companies_org", "org_id"),
        Index("ix_companies_canon", "nome_canonico"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"))
    nome: Mapped[str] = mapped_column(String(300))
    nome_canonico: Mapped[str] = mapped_column(String(300))
    cnpj: Mapped[str] = mapped_column(String(20), default="")
    email: Mapped[str] = mapped_column(String(320), default="")  # remetente conhecido (RF-47)
    grupo: Mapped[str] = mapped_column(String(200), default="")  # consolidação vem no Passo 4
    criado_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Document(Base):
    """Arquivo enviado (balancete ou DRE) de uma empresa num período.

    Chave de negócio: (company, mes, ano, tipo). A dedup do RF-03 garante
    unicidade lógica — vence o mais recente.
    """

    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_org", "org_id"),
        Index("ix_documents_company", "company_id"),
        Index("ix_documents_status", "status"),
        Index("ix_documents_sha256", "sha256"),
        Index("ix_documents_chave", "org_id", "company_id", "mes", "ano", "tipo"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"))
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id"), nullable=True
    )

    nome_arquivo: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str] = mapped_column(String(120), default="")
    tamanho: Mapped[int] = mapped_column(Integer, default=0)
    storage_key: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64), default="")
    origem: Mapped[str] = mapped_column(String(20), default="UPLOAD")  # UPLOAD | EMAIL
    remetente: Mapped[str] = mapped_column(String(320), default="")  # email do remetente (EMAIL)
    enviado_por: Mapped[str] = mapped_column(String(320), default="")  # quem subiu (UPLOAD)

    # Metadados de negócio (preenchidos pela triagem/extração)
    empresa_nome: Mapped[str] = mapped_column(String(300), default="")
    tipo: Mapped[str | None] = mapped_column(String(10), nullable=True)  # BALANCO | DRE
    mes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ano: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(String(20), default=STATUS_RECEBIDO)
    mensagem: Mapped[str] = mapped_column(Text, default="")
    aviso: Mapped[str] = mapped_column(Text, default="")  # observação não-fatal (abas ignoradas)

    criado_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    atualizado_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    company: Mapped["Company | None"] = relationship()


class BalanceLine(Base):
    """Linha de balancete (analítica ou sintética) vinculada ao documento."""

    __tablename__ = "balance_lines"
    __table_args__ = (
        Index("ix_balance_lines_document", "document_id"),
        Index("ix_balance_lines_periodo", "org_id", "company_id", "mes", "ano"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE")
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"))
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    mes: Mapped[int | None] = mapped_column(Integer)
    ano: Mapped[int | None] = mapped_column(Integer)

    ordem: Mapped[int] = mapped_column(Integer, default=0)
    conta: Mapped[str] = mapped_column(String(400), default="")
    categoria: Mapped[str | None] = mapped_column(String(60), nullable=True)  # categoria sintética
    is_sintetico: Mapped[bool] = mapped_column(Boolean, default=False)

    saldo_anterior: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    debito: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    credito: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    saldo_atual: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)

    av_atual: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    av_anterior: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    ah: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)


class DreLine(Base):
    """Linha de DRE por categoria sintética vinculada ao documento."""

    __tablename__ = "dre_lines"
    __table_args__ = (
        Index("ix_dre_lines_document", "document_id"),
        Index("ix_dre_lines_periodo", "org_id", "company_id", "mes", "ano"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE")
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"))
    company_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("companies.id"), nullable=True)
    mes: Mapped[int | None] = mapped_column(Integer)
    ano: Mapped[int | None] = mapped_column(Integer)

    ordem: Mapped[int] = mapped_column(Integer, default=0)
    conta: Mapped[str] = mapped_column(String(120), default="")  # categoria sintética
    is_sintetico: Mapped[bool] = mapped_column(Boolean, default=True)
    # DRE derivada do balancete (RF-19): substituída quando uma DRE real chega.
    derivada: Mapped[bool] = mapped_column(Boolean, default=False)

    valor_atual: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    valor_anterior: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)

    av_atual: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    av_anterior: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    ah: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)


class AiCall(Base):
    """Auditoria de toda chamada de IA (RF-14) com tokens e custo."""

    __tablename__ = "ai_calls"
    __table_args__ = (
        Index("ix_ai_calls_org", "org_id"),
        Index("ix_ai_calls_document", "document_id"),
        Index("ix_ai_calls_criado", "criado_em"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("orgs.id"), nullable=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    tipo: Mapped[str] = mapped_column(String(30), default="")  # triagem | extracao | texto
    modelo: Mapped[str] = mapped_column(String(60), default="")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    custo_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=0)
    duracao_ms: Mapped[int] = mapped_column(Integer, default=0)
    sucesso: Mapped[bool] = mapped_column(Boolean, default=True)
    erro: Mapped[str] = mapped_column(Text, default="")
    prompt: Mapped[str] = mapped_column(Text, default="")
    resposta: Mapped[str] = mapped_column(Text, default="")
    criado_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )


class JobEvent(Base):
    """Evento de progresso do pipeline, consumido pelo SSE do portal (RF-49/50)."""

    __tablename__ = "job_events"
    __table_args__ = (
        Index("ix_job_events_document", "document_id"),
        Index("ix_job_events_criado", "criado_em"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("orgs.id"), nullable=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=True
    )
    etapa: Mapped[str] = mapped_column(String(60), default="")
    progresso: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    status: Mapped[str] = mapped_column(String(20), default="info")  # info | ok | erro
    mensagem: Mapped[str] = mapped_column(Text, default="")
    criado_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )


class IndicatorDefinition(Base):
    """Definição de indicador (RF-27b). org_id NULL = padrão do sistema (seed das 23)."""

    __tablename__ = "indicator_definitions"
    __table_args__ = (
        UniqueConstraint("org_id", "key", name="uq_ind_def_org_key"),
        Index("ix_ind_def_org", "org_id"),
        Index("ix_ind_def_key", "key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("orgs.id"), nullable=True
    )
    key: Mapped[str] = mapped_column(String(60))
    label: Mapped[str] = mapped_column(String(120))
    formula: Mapped[str] = mapped_column(Text, default="")
    formato: Mapped[str] = mapped_column(String(10), default="rs")  # rs | pct | indice
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class IndicatorValue(Base):
    """Valor calculado de um indicador por entidade (empresa/grupo) e período (RF-30)."""

    __tablename__ = "indicator_values"
    __table_args__ = (
        UniqueConstraint(
            "org_id", "company_id", "grupo", "mes", "ano", "key", name="uq_ind_val_entidade"
        ),
        Index("ix_ind_val_org", "org_id"),
        Index("ix_ind_val_company", "company_id"),
        Index("ix_ind_val_periodo", "org_id", "mes", "ano"),
        Index("ix_ind_val_key", "key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"))
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=True
    )
    grupo: Mapped[str] = mapped_column(String(200), default="")  # consolidação (próximo passo)
    mes: Mapped[int] = mapped_column(Integer)
    ano: Mapped[int] = mapped_column(Integer)
    key: Mapped[str] = mapped_column(String(60))
    label: Mapped[str] = mapped_column(String(120), default="")
    formato: Mapped[str] = mapped_column(String(10), default="")
    valor: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    criado_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    atualizado_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


# ── Relatórios (Passo 5) ─────────────────────────────────────────────────────
REPORT_FILA = "FILA"
REPORT_GERANDO = "GERANDO"
REPORT_CONCLUIDO = "CONCLUIDO"
REPORT_ERRO = "ERRO"


class Template(Base):
    """Modelo docx (docxtpl) cadastrado pela org. `suporta_grupo` filtra a seleção."""

    __tablename__ = "templates"
    __table_args__ = (
        Index("ix_templates_org", "org_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"))
    nome: Mapped[str] = mapped_column(String(200))
    descricao: Mapped[str] = mapped_column(String(500), default="")
    suporta_grupo: Mapped[bool] = mapped_column(Boolean, default=False)
    storage_key: Mapped[str] = mapped_column(String(500))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Report(Base):
    """Relatório gerado de um template para uma entidade/período (fila + progresso — RF-38)."""

    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_reports_org", "org_id"),
        Index("ix_reports_company", "company_id"),
        Index("ix_reports_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"))
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("templates.id"))
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )
    grupo: Mapped[str] = mapped_column(String(200), default="")
    mes: Mapped[int] = mapped_column(Integer)
    ano: Mapped[int] = mapped_column(Integer)
    anual: Mapped[bool] = mapped_column(Boolean, default=False)  # exercício (ano) em vez de mês

    status: Mapped[str] = mapped_column(String(20), default=REPORT_FILA)
    progresso: Mapped[int] = mapped_column(Integer, default=0)
    etapa: Mapped[str] = mapped_column(String(60), default="")
    erro: Mapped[str] = mapped_column(Text, default="")

    nome_arquivo: Mapped[str] = mapped_column(String(300), default="")
    storage_key: Mapped[str] = mapped_column(String(500), default="")
    # RF-40: documento de origem ao qual a URL do relatório é vinculada (opcional).
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    criado_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    atualizado_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


# ── Recepção por email: fila de revisão (RF-47) ──────────────────────────────
EMAIL_PENDENTE = "PENDENTE"
EMAIL_PROCESSADO = "PROCESSADO"
EMAIL_IGNORADO = "IGNORADO"


class EmailMessage(Base):
    """Email recebido na caixa rma@, aguardando revisão antes de importar."""

    __tablename__ = "email_messages"
    __table_args__ = (
        Index("ix_email_msg_org", "org_id"),
        Index("ix_email_msg_status", "status"),
        Index("ix_email_msg_mid", "message_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"))
    message_id: Mapped[str] = mapped_column(String(800))  # id no Graph
    remetente: Mapped[str] = mapped_column(String(320), default="")
    assunto: Mapped[str] = mapped_column(String(500), default="")
    corpo: Mapped[str] = mapped_column(Text, default="")
    recebido_em: Mapped[str] = mapped_column(String(40), default="")
    status: Mapped[str] = mapped_column(String(20), default=EMAIL_PENDENTE)
    criado_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    anexos: Mapped[list["EmailAttachment"]] = relationship(
        back_populates="mensagem", cascade="all, delete-orphan"
    )


class EmailAttachment(Base):
    """Anexo de um email recebido (bytes no storage), selecionável para importação."""

    __tablename__ = "email_attachments"
    __table_args__ = (
        Index("ix_email_att_msg", "email_message_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email_message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("email_messages.id", ondelete="CASCADE")
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orgs.id"))
    nome: Mapped[str] = mapped_column(String(500))
    content_type: Mapped[str] = mapped_column(String(120), default="")
    tamanho: Mapped[int] = mapped_column(Integer, default=0)
    storage_key: Mapped[str] = mapped_column(String(500), default="")
    suportado: Mapped[bool] = mapped_column(Boolean, default=True)  # extensão de documento
    incluido: Mapped[bool] = mapped_column(Boolean, default=False)  # importado para o pipeline
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    criado_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    mensagem: Mapped["EmailMessage"] = relationship(back_populates="anexos")
