# Ponto Fácil

Aplicação individual para registro de jornada, folgas e relatórios pessoais. Cada conta tem acesso somente aos próprios dados; não existem perfis de empresa ou de administrador.

## Requisitos

- Python 3.13 ou superior
- PostgreSQL 14 ou superior

## Instalação local

1. Crie e ative um ambiente virtual:

   ```powershell
   py -3.13 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Instale as dependências:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Crie um banco PostgreSQL e copie `.env.example` para `.env`. Configure `DATABASE_URL` com suas credenciais.

4. Aplique as migrações e inicie a aplicação:

   ```powershell
   alembic upgrade head
   streamlit run app.py
   ```

O primeiro acesso permite criar uma conta individual. Não há usuário ou dados fictícios pré-cadastrados.

## Configuração

| Variável | Obrigatória | Descrição |
|---|---|---|
| `DATABASE_URL` | Sim | URL SQLAlchemy do PostgreSQL, por exemplo `postgresql+psycopg://usuario:senha@localhost:5432/ponto_facil`. |
| `APP_TIMEZONE` | Não | Fuso usado para registros; padrão `America/Sao_Paulo`. |

Em produção no Streamlit Community Cloud, configure `DATABASE_URL` e, opcionalmente, `APP_TIMEZONE` em **App settings → Secrets**, em formato TOML:

```toml
DATABASE_URL = "postgresql+psycopg://usuario:senha@host:5432/ponto_facil"
APP_TIMEZONE = "America/Sao_Paulo"
```

O arquivo `.env` é apenas para desenvolvimento local e não deve ser enviado ao controle de versão. Use TLS e credenciais com privilégios mínimos no serviço PostgreSQL de produção.

## Migrações

Após alterar os modelos, gere e revise a migração:

```powershell
alembic revision --autogenerate -m "descricao"
alembic upgrade head
```

Migrações apontam para PostgreSQL via `DATABASE_URL`. Os testes usam SQLite em memória somente como banco efêmero de teste; SQLite não é banco de produção.

Ao atualizar uma instalação existente, aplique as novas migrações antes de iniciar o app:

```powershell
alembic upgrade head
```

## Ajustes retroativos e acessibilidade

Na tela **Histórico**, é possível corrigir marcações e adicionar marcações esquecidas em dias anteriores a hoje do mês atual. Toda mudança exige justificativa; registros originais são preservados e o horário corrigido passa a ser o horário efetivo exibido. A sequência de marcações é validada e os dados continuam limitados à conta autenticada.

Em **Configurações pessoais**, tema (claro, escuro ou conforme o dispositivo), alto contraste, tamanho do texto e redução de animações são salvos por conta.

## Relatórios e exportação Excel

A tela **Relatórios mensais** apresenta horas trabalhadas e previstas, saldo, horas extras diárias e semanais, resumo semanal, detalhamento diário, marcações incompletas e histórico de ajustes. O Excel exportado contém as abas **Resumo**, **Detalhamento diário** e **Histórico de ajustes**.

O cálculo usa a jornada diária e semanal configurada, considera as folgas planejadas/realizadas e os feriados cadastrados por conta como dias sem jornada prevista, inclui o intervalo entre entrada e saída final na duração e atribui turnos que passam da meia-noite ao dia da entrada. Horas extras semanais adicionais descontam as extras diárias já contabilizadas. Se a jornada for de 8 horas por dia e uma folga semanal, configure 48 horas semanais em **Configurações pessoais**. Dias sem as quatro marcações esperadas são sinalizados como incompletos e não entram nas horas trabalhadas.

Os relatórios são gerados somente após confirmar o período e ficam disponíveis durante a sessão até uma nova solicitação. As consultas limitam as marcações à janela do mês e às semanas envolvidas, com margem para turnos noturnos; o arquivo Excel é reutilizado ao baixar. O dashboard consulta a última marcação diretamente, sem carregar todo o histórico da conta.

## Testes

```powershell
pytest
```

## Escopo atual

Inclui cadastro/login, sessão autenticada, isolamento por conta, painel inicial, configuração de jornada, registros com sequência validada, planejamento e atualização de folgas, correções retroativas auditadas, relatórios mensais e exportação Excel. Cálculos financeiros de folha, adicionais legais e regras específicas de convenções coletivas não fazem parte do sistema.
