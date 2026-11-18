# Ponto Fácil

Aplicação de controle de jornada com perfis de funcionário, RH e administrador. Funcionários acessam os próprios dados; RH e administração também podem consultar os dados dos funcionários conforme suas permissões.

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
| `APP_TIMEZONE` | Não | Fuso usado para registros e relatórios; padrão `America/Sao_Paulo`. |
| `SESSION_SECRET` | Recomendada | Chave aleatória persistente para assinar a sessão lembrada. Gere com `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Sem ela, sessões serão invalidadas ao reiniciar o processo ou trocar de instância. |
| `APP_BASE_URL` | Para redefinição | URL pública do app, sem query string; use HTTPS em produção. Usada nos links de redefinição. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM` | Para e-mails | Servidor, porta e remetente usados na recuperação de senha e nos relatórios automáticos. |
| `SMTP_USER`, `SMTP_PASSWORD` | Opcional | Credenciais SMTP; configure ambas ou nenhuma. |
| `SMTP_USE_SSL`, `SMTP_STARTTLS` | Opcional | Transporte SMTP seguro. Use SSL ou STARTTLS; TLS é exigido fora de localhost. |

Em produção no Streamlit Community Cloud, configure `DATABASE_URL` e, opcionalmente, `APP_TIMEZONE` em **App settings → Secrets**, em formato TOML:

```toml
DATABASE_URL = "postgresql+psycopg://usuario:senha@host:5432/ponto_facil"
APP_TIMEZONE = "America/Sao_Paulo"
SESSION_SECRET = "cole-aqui-uma-chave-gerada-aleatoriamente"
APP_BASE_URL = "https://seu-dominio.example"
SMTP_HOST = "smtp.seu-provedor.example"
SMTP_PORT = 587
SMTP_USER = "usuario-smtp"
SMTP_PASSWORD = "defina-como-secret"
SMTP_FROM = "Ponto Fácil <nao-responda@seu-dominio.example>"
SMTP_USE_SSL = false
SMTP_STARTTLS = true
```

O arquivo `.env` é apenas para desenvolvimento local e não deve ser enviado ao controle de versão. Use TLS e credenciais com privilégios mínimos no serviço PostgreSQL de produção.

## Criar a conta administrativa inicial

Configure `DATABASE_URL` para o banco correto e aplique as migrações com `alembic upgrade head`. Em seguida, execute `python create_admin.py`. O comando solicita nome e e-mail e pede a senha sem exibi-la no terminal. Ele cria uma conta separada com perfil `admin`; o cadastro público continua criando apenas funcionários e não promove contas existentes.

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

Na tela **Histórico**, funcionários podem solicitar correções e inclusões esquecidas em dias anteriores a hoje do mês atual. Os pedidos exigem justificativa, ficam pendentes até decisão do RH e não alteram as marcações antes da aprovação. A decisão e o responsável ficam auditados; registros originais são preservados.

As contas têm perfil `admin`, `rh` ou `funcionario`. Funcionários veem somente os próprios dados; RH e administração podem selecionar funcionários no **Dashboard**, **Histórico** e **Calendário**. Histórico e Calendário de outros funcionários são somente leitura; pedidos de alteração continuam sendo enviados pelo próprio funcionário. A tela **Administração** gerencia perfis e ativações, sem permitir desativar o último administrador. A tela **Gestão de RH** mostra jornadas e marcações dos funcionários e exporta a planilha de jornadas.

Após entrar, o navegador mantém a sessão por 10 minutos desde a última interação com o app, renovando esse prazo enquanto você navega. O cookie contém somente um token assinado, nunca a senha. RH e admin não têm acesso à página **Registrar ponto**.

Antes de entrar ou criar uma conta, é necessário aceitar os **Termos de Uso** e a **Política de Cookies**. O aceite é lembrado no navegador até a versão dos documentos mudar; a recusa bloqueia o acesso e remove o cookie de sessão. A página não consegue fechar a aba do navegador automaticamente. Os documentos em `docs/` são modelos: substitua todos os campos entre colchetes pelos dados corretos e obtenha revisão jurídica antes de publicar. Ao alterar os documentos, atualize `CONSENT_VERSION` em `app.py` para solicitar novo aceite.

## Notificações, recuperação de senha e auditoria

Novos pedidos de ajuste geram notificações internas para RH/admin; a decisão gera uma notificação para o funcionário. O contador de não lidas aparece na navegação, e a página **Notificações** permite marcar itens individualmente ou todos de uma vez.

Na tela de login, **Esqueci a senha** envia um link de uso único, válido por 30 minutos, somente para contas ativas. O banco guarda apenas o hash do token. A recuperação por e-mail fica indisponível até configurar `APP_BASE_URL` e `SMTP_HOST`/`SMTP_FROM`; configure usuário e senha SMTP juntos e use TLS em produção. RH pode gerar um link para funcionário; admin pode gerar para qualquer conta ativa. O link assistido é mostrado uma única vez na sessão e deve ser compartilhado por um canal seguro. Aplique `alembic upgrade head` antes de usar as novas funções.

RH/admin podem consultar e exportar a **Auditoria** em Excel, por período, com limite de 5.000 eventos por consulta. A trilha registra criação e alterações de acesso a contas, logins bem-sucedidos e falhos, marcações, solicitações/decisões e redefinições de senha; não armazena senhas nem tokens em texto. Falhas de login registram o e-mail tentado. Defina e documente um prazo de retenção adequado para os registros de auditoria.

As páginas usam os layouts responsivos do Streamlit e ajustes de espaçamento e alvos de toque em telas estreitas; tabelas largas podem exigir rolagem horizontal.

Em **Configurações pessoais**, tema (claro, escuro ou conforme o dispositivo), alto contraste, tamanho do texto e redução de animações são salvos por conta.

## Relatórios e exportação Excel

A tela **Relatórios mensais** apresenta horas trabalhadas e previstas, saldo, horas extras diárias e semanais, resumo semanal, detalhamento diário, marcações incompletas e histórico de ajustes. O Excel exportado contém as abas **Resumo**, **Detalhamento diário** e **Histórico de ajustes**.

O cálculo usa a jornada diária e semanal configurada, considera as folgas planejadas/realizadas e os feriados cadastrados por conta como dias sem jornada prevista, inclui o intervalo entre entrada e saída final na duração e atribui turnos que passam da meia-noite ao dia da entrada. Horas extras semanais adicionais descontam as extras diárias já contabilizadas. Se a jornada for de 8 horas por dia e uma folga semanal, configure 48 horas semanais em **Configurações pessoais**. Dias sem as quatro marcações esperadas são sinalizados como incompletos e não entram nas horas trabalhadas.

Os relatórios são gerados após confirmar o período e ficam disponíveis durante a sessão. Quando RH/admin aprova uma inclusão ou correção, o relatório em cache é recalculado na próxima abertura ou atualização da página, e o Excel também é renovado. As consultas limitam as marcações à janela do mês e às semanas envolvidas, com margem para turnos noturnos; o arquivo Excel é reutilizado ao baixar. O dashboard consulta a última marcação diretamente, sem carregar todo o histórico da conta.

## Envio automático mensal ao RH

O workflow `.github/workflows/monthly-reports.yml` verifica os relatórios no início de cada mês, gera um ZIP com um Excel por funcionário e envia aos e-mails de todas as contas RH ativas. O período é o mês anterior. O processamento é idempotente: uma entrega confirmada não é enviada novamente em execuções posteriores.

As marcações não são apagadas nem reiniciadas no banco; somente o período dos relatórios muda. Contas de funcionário criadas até o fim do mês entram no envio, mesmo que estejam inativas no momento da execução. Se o funcionário tiver uma sequência válida de marcações ainda aberta no último dia do mês, o relatório dele fica pendente até a saída final ser registrada. Não há prazo automático para essa espera; os relatórios dos demais funcionários são enviados sem aguardar. O job volta a verificar pendências diariamente.

Para habilitar:

1. Aplique a migração no banco de produção com `alembic upgrade head`.
2. No GitHub, habilite **Actions** e configure, em **Settings → Secrets and variables → Actions**, estes **Secrets**: `DATABASE_URL`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, `SMTP_USER` e `SMTP_PASSWORD`. `SMTP_USER` e `SMTP_PASSWORD` devem ser ambos definidos ou ambos vazios.
3. Configure estas **Variables**: `APP_TIMEZONE` como `America/Sao_Paulo` (ou o fuso que corresponda ao cron) e, para STARTTLS padrão, `SMTP_STARTTLS` como `true`. Se usar SSL direto, defina `SMTP_USE_SSL` como `true` e `SMTP_STARTTLS` como `false`.

Os Secrets do Streamlit Community Cloud não são compartilhados automaticamente com o GitHub Actions; configure-os também no repositório. O workflow verifica a cada 15 minutos durante os dias 1 e 2 UTC e faz uma verificação diária de recuperação. O cron do GitHub usa UTC e é de melhor esforço: pode atrasar e não garante execução exatamente às 00:00. A janela foi ajustada para `America/Sao_Paulo`; se usar outro fuso, revise os horários em `.github/workflows/monthly-reports.yml`. A execução manual do workflow serve para reprocessar relatórios pendentes.

## Testes

```powershell
pytest
```

## Escopo atual

Inclui cadastro/login, sessão autenticada, isolamento por conta, painel inicial, configuração de jornada, registros com sequência validada, planejamento e atualização de folgas, correções retroativas auditadas, relatórios mensais e exportação Excel. Cálculos financeiros de folha, adicionais legais e regras específicas de convenções coletivas não fazem parte do sistema.
