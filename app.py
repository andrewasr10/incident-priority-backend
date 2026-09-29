from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_swagger_ui import get_swaggerui_blueprint
import sqlite3
from datetime import datetime
from pathlib import Path

app = Flask(__name__)
CORS(app)
DB = Path(__file__).with_name("mvp.db")
STATUS_VALIDOS = ["ABERTO", "EM ANÁLISE", "CONTIDO", "RESOLVIDO"]


def conectar():
    banco = sqlite3.connect(DB)
    banco.row_factory = sqlite3.Row
    banco.execute("PRAGMA foreign_keys = ON")
    return banco


def agora():
    return datetime.now().isoformat(timespec="seconds")


def init_db():
    banco = conectar()
    banco.executescript("""
    CREATE TABLE IF NOT EXISTS ativos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL UNIQUE,
        criticidade INTEGER NOT NULL CHECK (criticidade BETWEEN 1 AND 5)
    );

    CREATE TABLE IF NOT EXISTS incidentes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo TEXT NOT NULL,
        descricao TEXT NOT NULL,
        tipo TEXT NOT NULL,
        severidade INTEGER NOT NULL CHECK (severidade BETWEEN 1 AND 5),
        ativo_id INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'ABERTO',
        risk_score INTEGER NOT NULL,
        prioridade TEXT NOT NULL,
        criado_em TEXT NOT NULL,
        atualizado_em TEXT NOT NULL,
        FOREIGN KEY (ativo_id) REFERENCES ativos(id)
    );

    CREATE TABLE IF NOT EXISTS historico (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        incidente_id INTEGER NOT NULL,
        status_anterior TEXT,
        status_novo TEXT NOT NULL,
        data TEXT NOT NULL,
        FOREIGN KEY (incidente_id) REFERENCES incidentes(id) ON DELETE CASCADE
    );
    """)
    banco.commit()
    banco.close()


def calcular_risco(severidade, criticidade):
    score = int(severidade) * int(criticidade) * 4
    if score >= 80:
        prioridade = "CRÍTICO"
    elif score >= 48:
        prioridade = "ALTO"
    elif score >= 24:
        prioridade = "MÉDIO"
    else:
        prioridade = "BAIXO"
    return score, prioridade


@app.get("/api/ativos")
def listar_ativos():
    banco = conectar()
    linhas = banco.execute("SELECT * FROM ativos ORDER BY criticidade DESC, nome").fetchall()
    banco.close()
    return jsonify([dict(linha) for linha in linhas])


@app.post("/api/ativos")
def cadastrar_ativo():
    dados = request.get_json(silent=True) or {}
    nome = str(dados.get("nome", "")).strip()
    try:
        criticidade = int(dados.get("criticidade"))
    except (TypeError, ValueError):
        return jsonify(erro="Criticidade deve ser um número entre 1 e 5."), 400
    if not nome or criticidade not in range(1, 6):
        return jsonify(erro="Nome e criticidade de 1 a 5 são obrigatórios."), 400
    try:
        banco = conectar()
        cursor = banco.execute("INSERT INTO ativos(nome, criticidade) VALUES (?, ?)", (nome, criticidade))
        banco.commit()
        novo_id = cursor.lastrowid
        banco.close()
        return jsonify(id=novo_id, mensagem="Ativo cadastrado com sucesso."), 201
    except sqlite3.IntegrityError:
        return jsonify(erro="Já existe um ativo com esse nome."), 409


@app.get("/api/incidentes")
def listar_incidentes():
    banco = conectar()
    linhas = banco.execute("""
        SELECT i.*, a.nome AS ativo_nome, a.criticidade AS ativo_criticidade
        FROM incidentes i JOIN ativos a ON a.id = i.ativo_id
        ORDER BY i.risk_score DESC, i.id DESC
    """).fetchall()
    banco.close()
    return jsonify([dict(linha) for linha in linhas])


@app.get("/api/incidentes/<int:incidente_id>")
def buscar_incidente(incidente_id):
    banco = conectar()
    linha = banco.execute("""
        SELECT i.*, a.nome AS ativo_nome, a.criticidade AS ativo_criticidade
        FROM incidentes i JOIN ativos a ON a.id = i.ativo_id
        WHERE i.id = ?
    """, (incidente_id,)).fetchone()
    banco.close()
    if not linha:
        return jsonify(erro="Incidente não encontrado."), 404
    return jsonify(dict(linha))


@app.post("/api/incidentes")
def cadastrar_incidente():
    dados = request.get_json(silent=True) or {}
    obrigatorios = ["titulo", "descricao", "tipo", "severidade", "ativo_id"]
    if any(dados.get(campo) in (None, "") for campo in obrigatorios):
        return jsonify(erro="Preencha todos os campos obrigatórios."), 400
    try:
        severidade = int(dados["severidade"])
        ativo_id = int(dados["ativo_id"])
    except (TypeError, ValueError):
        return jsonify(erro="Severidade e ativo devem ser numéricos."), 400
    if severidade not in range(1, 6):
        return jsonify(erro="Severidade deve estar entre 1 e 5."), 400

    banco = conectar()
    ativo = banco.execute("SELECT * FROM ativos WHERE id = ?", (ativo_id,)).fetchone()
    if not ativo:
        banco.close()
        return jsonify(erro="Ativo não encontrado."), 404

    score, prioridade = calcular_risco(severidade, ativo["criticidade"])
    data = agora()
    cursor = banco.execute("""
        INSERT INTO incidentes
        (titulo, descricao, tipo, severidade, ativo_id, status, risk_score, prioridade, criado_em, atualizado_em)
        VALUES (?, ?, ?, ?, ?, 'ABERTO', ?, ?, ?, ?)
    """, (str(dados["titulo"]).strip(), str(dados["descricao"]).strip(),
          str(dados["tipo"]).strip(), severidade, ativo_id, score, prioridade, data, data))
    incidente_id = cursor.lastrowid
    banco.execute("""
        INSERT INTO historico(incidente_id, status_anterior, status_novo, data)
        VALUES (?, NULL, 'ABERTO', ?)
    """, (incidente_id, data))
    banco.commit()
    banco.close()
    return jsonify(id=incidente_id, risk_score=score, prioridade=prioridade,
                   mensagem="Incidente analisado e registrado."), 201


@app.patch("/api/incidentes/<int:incidente_id>/status")
def atualizar_status(incidente_id):
    dados = request.get_json(silent=True) or {}
    novo_status = dados.get("status")
    if novo_status not in STATUS_VALIDOS:
        return jsonify(erro="Status inválido.", permitidos=STATUS_VALIDOS), 400
    banco = conectar()
    atual = banco.execute("SELECT status FROM incidentes WHERE id = ?", (incidente_id,)).fetchone()
    if not atual:
        banco.close()
        return jsonify(erro="Incidente não encontrado."), 404
    data = agora()
    banco.execute("UPDATE incidentes SET status = ?, atualizado_em = ? WHERE id = ?",
                  (novo_status, data, incidente_id))
    banco.execute("""
        INSERT INTO historico(incidente_id, status_anterior, status_novo, data)
        VALUES (?, ?, ?, ?)
    """, (incidente_id, atual["status"], novo_status, data))
    banco.commit()
    banco.close()
    return jsonify(mensagem="Status atualizado.", status=novo_status)


@app.get("/api/incidentes/<int:incidente_id>/historico")
def listar_historico(incidente_id):
    banco = conectar()
    existe = banco.execute("SELECT 1 FROM incidentes WHERE id = ?", (incidente_id,)).fetchone()
    if not existe:
        banco.close()
        return jsonify(erro="Incidente não encontrado."), 404
    linhas = banco.execute("""
        SELECT * FROM historico WHERE incidente_id = ? ORDER BY id DESC
    """, (incidente_id,)).fetchall()
    banco.close()
    return jsonify([dict(linha) for linha in linhas])


@app.delete("/api/incidentes/<int:incidente_id>")
def excluir_incidente(incidente_id):
    banco = conectar()
    existe = banco.execute("SELECT 1 FROM incidentes WHERE id = ?", (incidente_id,)).fetchone()
    if not existe:
        banco.close()
        return jsonify(erro="Incidente não encontrado."), 404
    banco.execute("DELETE FROM incidentes WHERE id = ?", (incidente_id,))
    banco.commit()
    banco.close()
    return jsonify(mensagem="Incidente excluído com sucesso.")


@app.get("/api/dashboard")
def obter_dashboard():
    banco = conectar()
    total = banco.execute("SELECT COUNT(*) n FROM incidentes").fetchone()["n"]
    abertos = banco.execute("SELECT COUNT(*) n FROM incidentes WHERE status != 'RESOLVIDO'").fetchone()["n"]
    criticos = banco.execute("SELECT COUNT(*) n FROM incidentes WHERE prioridade = 'CRÍTICO'").fetchone()["n"]
    resolvidos = banco.execute("SELECT COUNT(*) n FROM incidentes WHERE status = 'RESOLVIDO'").fetchone()["n"]
    ativos = banco.execute("SELECT COUNT(*) n FROM ativos").fetchone()["n"]
    banco.close()
    return jsonify(total=total, abertos=abertos, criticos=criticos, resolvidos=resolvidos, ativos=ativos)


SWAGGER_URL = "/swagger"
API_URL = "/static/openapi.json"
app.register_blueprint(
    get_swaggerui_blueprint(SWAGGER_URL, API_URL, config={"app_name": "Incident Priority API"}),
    url_prefix=SWAGGER_URL
)

init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
