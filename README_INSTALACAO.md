# Gestor de Horários Docentes — kit para gerar EXE Windows

## Sobre este kit
Contém o projeto Python enviado, uma janela inicial para abrir o sistema, os arquivos estáticos e um **backup consolidado dos dados existentes no ZIP original**. O banco é SQLite local, não MySQL, e não requer servidor de banco de dados.

**Atenção:** o ZIP entregue aqui é um *kit para compilar um `.exe` no Windows*, não um `.exe` já compilado. O ambiente de preparação não é Windows e não gera nativamente um executável Windows testado.

## Como gerar o EXE (uma única vez, em um computador Windows)
1. Extraia este ZIP em uma pasta local.
2. Instale o Python 3.10+ no computador de compilação (marque `Add python.exe to PATH`).
3. Com internet, clique duas vezes em `GERAR_EXE_WINDOWS.bat`. O script instala o PyInstaller.
4. O arquivo resultante estará em `dist\GestorHorariosDocentes.exe`.
5. Copie **somente o EXE** para o computador de destino. Nesse computador não será preciso instalar Python ou MySQL.
6. Dê dois cliques no executável; uma pequena janela inicia o servidor local e abre o navegador com a grade.

**Para encerrar corretamente:** feche a janela do Gestor, além da aba do navegador.

## Onde os dados são salvos
Em `%LOCALAPPDATA%\GestorHorariosDocentes\horarios.sqlite3`.

O primeiro uso instala um backup dos dados contidos no ZIP original (professores, turmas, disciplinas e alocações). Usos posteriores mantêm as alterações: a base **não é sobrescrita** ao atualizar o EXE. Para levar os dados a outro computador, feche o programa e copie esse arquivo para o mesmo local no PC de destino. Para backup, feche o programa antes de copiar.

## Funcionalidades preservadas
- Aulas de manhã 07:00–13:20, tarde 13:40–20:00.
- Cadastro de professores, turmas, disciplinas e salas.
- Disponibilidades por dia e turno.
- Prevenção de choque de professor, turma e sala.
- Limite individual de 42 horas-relógio, inclusive atividades adicionais.
- Sugestão heurística de grade e exportação CSV.

## Limitações
- Interface em navegador, apesar de abrir a partir de um aplicativo desktop.
- Não requer internet para uso; só para instalar PyInstaller na compilação.
- **SQLite é um banco embutido**, e ainda é necessário para persistir os dados. “Sem banco de dados” aqui significa “sem instalar ou administrar um servidor de banco de dados”.
- Não há login nem sincronização entre computadores. Para uso simultâneo por várias pessoas, é indicada uma versão servidor/multiusuário.
- Disponibilidade é por turno integral; horários parciais requerem evolução do modelo.
- A montagem não possui drag-and-drop nesta versão Python original.

## Teste técnico
`py -3 -m unittest discover -s tests -v`


## Novidades da versão profissional

- **Menu recolhível:** clique em «☰ Recolher menu» para liberar espaço na tela; clique novamente para expandir.
- **Horário completo:** uma página do menu reúne todas as turmas lado a lado; selecione um dia ou «Semana completa». Ao clicar no símbolo +, abre-se o formulário de alocação com turma e período preenchidos.
- **Validação da grade:** página com conferência dos choques, disponibilidade, carga horária e demandas ainda pendentes. É uma validação sobre registros existentes; não substitui a conferência da distribuição pedagógica.
- **Verificações adicionais:** impede cadastro duplicado de professor (diferenças de maiúsculas/minúsculas), impede demandas repetidas para mesmo professor/turma/disciplina e acusa somatório de demandas acima dos 70 períodos semanais da turma.
- A impressão do horário completo pode ser feita pelo botão Imprimir; para impressão de apenas um dia selecione-o antes.

### Preservação do banco de dados
O executável preserva o banco SQLite instalado na pasta de dados local. Antes de atualizar, realize uma cópia do arquivo SQLite em `%LOCALAPPDATA%\GestorHorariosDocentes`.

**Limitação:** este kit é compilável no Windows, mas não é um `.exe` já compilado.

## Novidade — Turmas e horários (versão 3)

No menu lateral, abra **Turmas e horários**.

**Nova turma:** clique **+ Nova turma**, informe nome, curso e unidade. A turma aparece imediatamente em Grade semanal, Horário completo e nos formulários de demandas e de alocação.

**Períodos de aula:** clique **+ Novo período**, selecione manhã/tarde-noite, descrição, início e término. Para alterar um horário sem aulas, use **Editar**. Períodos padrão não podem ser excluídos; os horários adicionais podem ser excluídos se não tiverem aulas.

Os horários padrão permanecem: manhã de 07:00 a 13:20, pausa de 09:30 a 10:00; tarde de 13:40 a 20:00, pausa de 16:10 a 16:40. Para horários adicionais, o sistema admite extensões da manhã desde 06:00 ou do turno da tarde/noite até 22:30, sem sobreposição com outros períodos. Os períodos precisam ter duração entre 15 e 180 minutos. Como os 14 períodos padrão preenchem o expediente original, para criar um período *dentro* desse expediente, primeiro edite horários livres existentes para abrir espaço, ou acrescente horários nas extensões permitidas. Horários já ocupados não podem ser editados; antes, remaneje as respectivas aulas.

**Validação:** o servidor impede períodos que se sobreponham a outros, invadam os intervalos ou saiam dos limites; a carga horária considera a duração real de cada aula, inclusive nos períodos personalizados. O gerador de horários passa a incluir os novos períodos cadastrados.

**Atualização sem perda de dados:** faça backup do arquivo `%LOCALAPPDATA%\GestorHorariosDocentes\horarios.sqlite3` com o programa fechado. A nova versão cria automaticamente a tabela de períodos na primeira inicialização e conserva as aulas e turmas existentes. Não apague essa pasta de dados ao atualizar o executável.

**Testes:** execute `py -3 -m unittest discover -s tests -v`. O código foi verificado no ambiente de desenvolvimento, mas a interface final e o EXE precisam ser validados em um computador Windows.

## Atualização V4 — turno por turma

- Em **Turmas e horários → Nova turma**, escolha **Manhã**, **Tarde/noite** ou **Integral**.
- Na lista de turmas, clique em **Editar** para ajustar o turno de turmas antigas.
- Na **Grade semanal**, ao selecionar uma turma, aparecem apenas os horários associados ao turno cadastrado. Ao selecionar um professor, aparecem ambos os turnos para permitir visualizar toda a carga docente.
- Na tela **Horário completo**, células fora do turno de uma turma são assinaladas com um travessão e não permitem novas aulas.
- No formulário de alocação, o campo **Aula / período** é ajustado quando a turma é alterada.
- O gerador de propostas só sugere períodos do turno da turma; a validação no servidor impede qualquer alocação fora do turno.
- **Compatibilidade:** turmas cadastradas em versões anteriores ficam inicialmente como **Integral**, preservando horários existentes. Se existirem aulas em outro turno, o sistema impedirá mudar o turno até remanejá-las.
- **Backup obrigatório:** copie o banco SQLite em `%LOCALAPPDATA%\GestorHorariosDocentes` antes de atualizar.
- Os períodos (07h00–13h20 e 13h40–20h00) permanecem globais, mas cada turma usa somente o turno escolhido.
