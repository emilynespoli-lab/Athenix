# ATHENIX — Contexto e instruções para agentes

## Identidade
A Athenix é uma startup B2B de inteligência regulatória com IA, em fase de validação de mercado e desenvolvimento do MVP.

## Missão
Ajudar empresas reguladas a compreender mudanças normativas, identificar obrigações, acompanhar sua conformidade e avaliar riscos e impactos operacionais e financeiros.

## Mercado inicial
Empresas de transmissão e distribuição de energia elétrica no Brasil, com foco inicial nas equipes de Assuntos Regulatórios.

Expansão para telecomunicações, petróleo e gás é uma possibilidade futura, não o escopo atual do MVP.

## Visão de longo prazo
O produto é organizado em quatro pilares:

1. Monitoramento regulatório.
2. Interpretação de normas e identificação de obrigações.
3. Gestão da conformidade, prazos e evidências.
4. Análise de riscos e impactos financeiros e operacionais.

## Estado atual
O projeto ainda não é um SaaS validado comercialmente.
O MVP técnico não deve ser confundido com um produto comercialmente validado.

O foco é validar a qualidade das extrações, a rastreabilidade das evidências, a revisão humana e o valor para o cliente.

## Princípios inegociáveis
- Priorizar confiabilidade regulatória sobre funcionalidades vistosas.
- Nunca inventar obrigações, citações ou dispositivos legais.
- Distinguir texto normativo de interpretação da IA.
- Garantir rastreabilidade até a fonte documental.
- Preservar revisão humana para conclusões regulatórias.
- Evitar complexidade técnica sem benefício comprovado.
- Não confundir hipóteses de negócio com fatos validados.
- Considerar custo operacional, segurança e manutenção.

## Documentos de referência
A documentação oficial do projeto está em docs/.

Antes de propor uma mudança importante, consultar os documentos relevantes.

Em caso de conflito, informar a divergência ao usuário em vez de escolher silenciosamente uma versão.

## Ferramentas de navegação e edição

- Aplicar o estilo Ponytail abaixo em toda alteração; ele orienta o trabalho e não exige um serviço em execução.
- Quando o MCP Serena estiver disponível, ativar explicitamente este diretório e ler suas instruções iniciais. Preferir visão geral de símbolos, busca de símbolos e referências para compreender código e localizar chamadores antes de editar.
- Usar `rg` para texto e arquivos e o terminal para testes, lint e migrações. Usar edição por símbolo quando reduzir o escopo da alteração; conferir o resultado e executar as verificações pertinentes.
- Não indexar ambientes de dependências, bancos locais, artefatos de execução ou caches. Sugestões do MCP não comprovam aprovação de testes nem validade regulatória.
- Se o Serena não estiver conectado, informar a limitação e continuar com as ferramentas disponíveis, sem declarar uso do MCP.

## Desenvolvimento e revisão
Uma IA pode implementar e a outra revisar.

A IA revisora deve:
- Verificar código, testes e evidências independentemente.
- Questionar hipóteses e identificar riscos.
- Comparar a solução com os objetivos da Athenix.
- Separar defeitos comprovados de sugestões opcionais.
- Não aprovar uma solução apenas porque outra IA a produziu.

## Gestão das decisões
Não modificar a visão de negócio ou ampliar o escopo do MVP sem aprovação explícita do fundador.

Toda mudança arquitetural relevante deve incluir justificativa, alternativas e trade-offs.

## Estilo de código (Ponytail)
Adaptado de [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) (MIT). **Os princípios inegociáveis da Athenix prevalecem sobre a economia de código:** nunca cortar rastreabilidade, citações da fonte, distinção entre texto normativo e interpretação da IA, nem revisão humana.

Resolva o problema inteiro com o mínimo de código novo. Termine a resposta com uma ou duas linhas: o que foi pulado ou não verificado e qualquer risco que o usuário precise saber.

**Antes de escrever:** leia a tarefa e o código que ela toca. Liste tudo que a mudança deve alcançar (chamadores, testes, fixtures, config, exports) e o que ela pode quebrar (dados destruídos ou expostos, chamadores que param de funcionar). Isso é escopo; funcionalidades extras não são.

**A menor mudança completa — use a primeira opção que resolve de verdade:**
1. Precisa existir? Pule funcionalidades, opções e flexibilidade que ninguém pediu, e cite-as em uma linha. Pedido vago recebe a menor versão que cumpre o essencial.
2. Já existe no código (helper, componente, serviço, padrão)? Use como o código ao redor usa.
3. Biblioteca padrão ou recurso da plataforma? Use, salvo se o projeto tiver o seu.
4. Dependência já instalada? Use. Nunca adicione dependência para poucas linhas.
5. Cabe em uma linha clara? Uma linha.
6. Senão: o mínimo de código que funciona.

- Seja preguiçoso na solução, nunca na mudança: complete tudo que a tarefa exige, incluindo chamadores, testes e fixtures que a mudança quebra.
- Sem abstração, wrapper, opção, config, boilerplate ou código "para depois" que ninguém pediu. Apagar vale mais que adicionar. Mantenha a estrutura e as convenções existentes.
- Comente só o porquê que o código não mostra, em uma linha.
- Correção de bug: antes de editar, busque todos os chamadores da função e corrija a causa raiz uma vez, no código compartilhado.
- Código movido ou unificado mantém seu tratamento de erro e validação.
- Entre opções de mesmo tamanho, escolha a correta nos casos de borda.
- Lógica nova não trivial (ramo, laço, parser, dinheiro, segurança, script novo) leva um teste pequeno ou assert de verificação.
- Atalho com limite conhecido ganha comentário: `shortcut: <limite>, <quando evoluir>`.

**Nunca cortar:** validação em fronteiras de confiança, tratamento de erro que evita perda de dados, segurança, acessibilidade, rastreabilidade regulatória e tudo que o usuário pediu.
