# Incident Priority API

Backend do MVP da disciplina de Desenvolvimento Full Stack Básico. API REST para cadastro de ativos, registro e priorização de incidentes de segurança e histórico de tratamento.

## Tecnologias
- Python 3
- Flask
- SQLite
- Swagger / OpenAPI

## Instalação e execução
```powershell
python -m pip install -r requirements.txt
python app.py
```
A API ficará em `http://127.0.0.1:5000` e o Swagger em `http://127.0.0.1:5000/swagger/`. O banco `mvp.db` é criado automaticamente.

## Rotas
- GET/POST `/api/ativos`
- GET/POST `/api/incidentes`
- GET/DELETE `/api/incidentes/{id}`
- PATCH `/api/incidentes/{id}/status`
- GET `/api/incidentes/{id}/historico`
- GET `/api/dashboard`

## Risk Score
O score é calculado no backend: `severidade × criticidade do ativo × 4`, resultando em 4 a 100. A faixa obtida define a prioridade Baixo, Médio, Alto ou Crítico.
