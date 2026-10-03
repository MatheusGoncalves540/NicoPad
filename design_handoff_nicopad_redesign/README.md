# Handoff: redesign do nicoPad (Modernist)

## Overview
Redesign completo da interface do nicoPad (repo `MatheusGoncalves540/NicoPad`, hoje em Tkinter/ttk em `src/nicopad/ui.py`). Toda a lógica atual continua: `audio.py`, `hotkeys.py`, `library.py`, `profile.py`, `youtube.py`, `cable.py`, `updater.py` e `config.py` **não mudam de comportamento**. O que muda é a camada de interface, que sai do Tkinter e passa para **PySide6 (Qt Widgets)**.

Telas: janela principal (com visualização **Pads** e **Lista**), **Tocando agora** (janela solta), assistente de primeiro uso (4 passos), Configurar som, Cortar som, Baixar do YouTube, guia do cabo (?), Fechar a janela. Tudo em tema **claro** e **escuro**.

## About the Design Files
Os arquivos em `design/` são **referências de design feitas em HTML**: protótipos que mostram a aparência e o comportamento esperados. **Não são código para produção e não devem ser embutidos no app** (nada de WebView, Electron, Tauri ou QtWebEngine — o dono do projeto quer um app desktop nativo, sem tecnologia web). A tarefa é **recriar essas telas em PySide6** seguindo este documento.

Para abrir os protótipos: sirva a pasta `design/` com um servidor local (`python -m http.server` dentro de `design/`) e abra `nicoPad Redesign.dc.html` no navegador. Abrir direto do disco com `file://` pode não funcionar. Todas as telas são clicáveis (veja "Interactions").

## Tecnologia escolhida: PySide6 + Qt Widgets + QSS
O dono pediu "o que for melhor para esse estilo continuar fiel". A escolha é PySide6 (Qt 6, LGPL), pelos motivos:
- **O estilo é plano**: retângulos sem arredondamento, bordas de 1px/2px, preenchimento sólido, uma fonte. O QSS (folha de estilos do Qt) faz isso 1:1, sem gambiarra. Tkinter/ttk não consegue (os temas nativos do ttk ignoram boa parte das cores e bordas), e o CustomTkinter arredonda tudo e tem poucos widgets.
- **Continua em Python**: os módulos de áudio, atalhos globais, bandeja, perfis e YouTube são reaproveitados sem reescrever.
- **Multiplataforma** (Windows, Linux e macOS), com diálogos nativos de arquivo.
- **`QPainter`** cobre as três peças que fogem do QSS: célula de pad (com barra de progresso), forma de onda do corte e a faixa de progresso das linhas.
- `QSystemTrayIcon` pode substituir o `tray.py` atual (opcional, mas reduz dependência).

Não use QML/Qt Quick. Ele também daria conta, mas obrigaria a reescrever a integração com Python e não traz ganho visual para este estilo.

Regras de implementação:
1. **Um arquivo de tokens** (`src/nicopad/theme.py`) com os dois dicionários de cores abaixo e uma função que gera o QSS a partir de um template (`nicopad.qss.tmpl`, que está neste pacote como ponto de partida). Trocar de tema = `app.setStyleSheet(build_qss(tokens))`, e repintar os widgets custom.
2. **Embutir a fonte Archivo** (Google Fonts, licença OFL) nos pesos 400, 600 e 800 em `packaging/fonts/` e carregar com `QFontDatabase.addApplicationFont`. Incluir no `.spec` do PyInstaller. Nunca deixar cair para Segoe UI/Arial.
3. **Ícones Lucide** (lucide.dev, ISC): baixar os SVGs listados em "Assets" para `packaging/icons/` e colorir em tempo de execução (trocar `currentColor` pela cor do token e gerar o `QIcon`), para que funcionem nos dois temas.
4. **Não usar o estilo nativo da plataforma**: `app.setStyle("Fusion")` e depois o QSS. Assim fica idêntico em Windows e Linux.
5. Nada de `border-radius` em lugar nenhum. Sombras só no diálogo (veja tokens).

## Fidelity
**Alta fidelidade.** Cores, tipografia, espaçamentos, bordas, estados e textos são finais. Recrie pixel a pixel. Medidas em px CSS = px lógicos no Qt (o Qt cuida do DPI).

Duas direções foram desenhadas:
- **1a "Painel"** — **implementar esta.** Barra lateral com mapas + áudio, abre na Lista.
- **1b "Mesa"** — alternativa (cabeçalho vermelho com mapas em abas, faixa de roteamento, abre nos Pads). Está documentada no fim; só implemente se o dono pedir. Diálogos, assistente, Pads e Lista são **os mesmos** nas duas.

---

## Design Tokens

### Cores — tema claro (padrão)
| Token | Hex | Uso |
|---|---|---|
| bg | `#f3f2f2` | fundo da janela, células de pad, campos dentro de diálogos |
| surface | `#eae9e9` | barra de título, campo de busca, selects, corpo dos diálogos |
| text | `#201e1d` | todo texto e ícones |
| divider | `#201e1d` a 40% → `rgba(32,30,29,0.40)` | todas as linhas/bordas |
| accent | `#ec3013` | ação primária, pad tocando, segmento ativo, alças do corte |
| accent-100 | `#fff2ef` | mapa ativo (fundo), tecla sendo gravada, avisos (fundo) |
| accent-600 | `#dd2b0f` | hover do primário |
| accent-700 | `#ae1800` | pressed do primário; **texto** de aviso em vermelho |
| accent-800 | `#7c1405` | texto sobre accent-100 |
| neutral-900 | `#2d2b2b` | véu atrás do diálogo (a 55%) |

### Cores — tema escuro
| Token | Hex |
|---|---|
| bg | `#181615` |
| surface | `#242221` |
| text | `#f3f2f2` |
| divider | `rgba(243,242,242,0.32)` |
| accent | `#ff563c` |
| accent-100 | `#4d170e` |
| accent-600 | `#ff9783` |
| accent-700 | `#ffc4b8` |
| accent-800 | `#ffe0d9` |
| neutral-900 | `#2d2b2b` |

Texto sobre fundo accent usa sempre a cor `bg` do tema.

### Tons derivados (mistura de `text` sobre transparente)
| Nome | Valor | Uso |
|---|---|---|
| muted | text a 60% | rótulos, metadados, caminhos de arquivo, cabeçalho da tabela |
| label | text a 70% | rótulo de campo ("Nome", "URL do vídeo") |
| hover | text a 7% | hover de botões secundários/ghost e itens de lista |
| hover-row | text a 4% | hover de linha da tabela |
| selected-row | text a 7% | linha selecionada |
| wave-off | text a 35% | barras da forma de onda fora do trecho |
| ghost-accent-hover | accent a 10% | hover de botões ghost vermelhos |

No Qt: calcular com `QColor` e passar `rgba(r,g,b,a)` para o QSS.

### Tipografia (Archivo)
| Papel | Tamanho | Peso | Extra |
|---|---|---|---|
| Marca no cabeçalho (1a) | 20px | 800 | letter-spacing -0.015em |
| Título do assistente | 32px | 800 | line-height 1.1 |
| Título do painel vermelho do assistente | 38px | 800 | line-height 1.05, -0.02em |
| Título de diálogo | 20px | 800 | |
| Tecla no pad (1a) | 28px | 800 | line-height 1, -0.02em |
| Valor grande (volume no diálogo) | 32px | 800 | |
| Valor médio (tempos do corte, número do guia) | 20–24px | 800 | |
| Corpo | 14px | 400 | line-height 1.45 |
| Botões | 14px | 800 | |
| Nome do som (pad) | 15px | 600 | |
| Nome do som (lista) | 14px | 600 | |
| Texto secundário | 12–13px | 400 | |
| Rótulo de seção (MAPAS, ÁUDIO, VOLUME GERAL, cabeçalho da tabela) | 11px | 400 | MAIÚSCULAS, letter-spacing 0.08em, cor muted |
| Tecla em chip (lista) | 12px | 800 | |

### Espaçamento, bordas, sombra
- Escala: 4, 8, 12, 16, 24, 32px. Padding padrão de seção: 16px horizontal.
- **Raio: 0 em tudo.**
- **Regra forte**: 2px `divider` entre seções principais (cabeçalho/corpo, sidebar/conteúdo, toolbar/conteúdo, conteúdo/rodapé, dentro dos diálogos entre cabeçalho/corpo/ações, contorno dos blocos em grade).
- **Regra fina**: 1px `divider` entre linhas da tabela, contorno de botões secundários, campos, selects e chips.
- Sombra só no diálogo: `0 12px 32px` com neutral-900 a 22% (`QGraphicsDropShadowEffect`, blur 32, offset 0,12).
- Foco por teclado: contorno de 2px `accent` com 2px de afastamento. Nunca o foco azul padrão.
- Desabilitado: opacidade 45%.

### Botões
| Tipo | Fundo | Texto | Borda | Hover | Pressed | Padding |
|---|---|---|---|---|---|---|
| Primário | accent | bg | — | accent-600 | accent-700 | 8px 14px |
| Secundário | transparente | text | 1px divider | hover (7%) | text a 14% | 8px 14px |
| Ghost (vermelho) | transparente | accent | — | accent a 10% | accent a 18% | 8px 10px |
| Ícone | transparente | text | — | text a 8% | | 32×32 ou 36×36 |

**O texto dos botões fica alinhado à esquerda** (quando o botão é mais largo que o texto, o texto começa no padding esquerdo). Ícone à esquerda do texto com 6px de espaço; seta "→" à direita fica no final.

---

## Screens / Views (direção 1a)

Janela: tamanho inicial 1180×728 (área do cliente), mínimo 900×600. Use a **barra de título nativa do sistema** (a barra cinza de 32px no protótipo representa o SO; não desenhe uma).

### 1. Janela principal
Layout (de cima para baixo):

**a) Cabeçalho** — altura ~62px, padding 12px 16px, borda inferior 2px divider, itens com 16px de espaço.
- Esquerda: quadrado branco `#ffffff` 36×36 com a logo `nicopad.png` 32×32 dentro (a logo tem fundo branco, por isso o quadrado branco nos dois temas) + "nicoPad" 20px/800, 10px de espaço.
- Direita, nesta ordem:
  - **Indicador de status** (botão): padding 7px 12px, 13px/600, ícone 14px + texto, 8px de espaço.
    - OK: borda 1px divider, fundo transparente, ícone check, texto "Microfone pronto".
    - Problema: fundo accent, borda accent, texto bg, ícone alert. Textos: "Os outros não escutam" (sem cabo virtual) ou "Sua voz não sai junto" (cabo ok, mic não misturado).
    - Clique: abre o guia do cabo.
  - "Perfis ▾" e "Configurações ▾" — botões de texto 14px/800 com chevron 14px, padding 8px 10px, hover 7%. Abrem `QMenu` com **os mesmos itens de hoje** (Exportar/Importar perfil…; Guardar cópia dos sons [check], Escolher a pasta dos sons…, Abrir a pasta dos sons, Ao fechar a janela ▸ [Perguntar sempre / Deixar na bandeja / Encerrar o programa], Preparar instalador do cabo de áudio, Abrir site do VB-Cable, Verificar atualizações…). Estilize o QMenu: fundo surface, borda 1px divider, itens 14px padding 8px 16px, hover accent-100 com texto accent-800, raio 0.
  - Botão ícone 36×36 de tema (lua no claro, sol no escuro).
  - Botão ícone 36×36 "?" (help-circle 18px): abre o guia.

**b) Corpo** — duas colunas.

*Barra lateral* — largura fixa 248px, borda direita 2px divider, coluna:
1. Rótulo "MAPAS" (padding 16px 16px 8px).
2. Lista de mapas: cada item é um botão de largura total, padding 9px 16px, nome à esquerda (14px) e contagem de sons à direita (12px, opacidade 70%). Ativo: fundo accent-100, texto accent-800, peso 800. Inativo: transparente, hover 6%.
3. "＋ Novo mapa" — ghost vermelho, 14px/800. Renomear e Excluir: **menu de contexto** (clique direito) no item do mapa — mesmos diálogos e regras de hoje (`_rename_map`, `_delete_map`, não excluir o único mapa).
4. Regra 2px (margem superior 12px).
5. Rótulo "ÁUDIO".
6. Três linhas (grade 20px + resto, 8px de espaço, 10px entre linhas). Ícone 14px à esquerda; rótulo 12px muted em cima; valor 13px/600 cortado com "…":
   - "Tocar no mic" → nome curto da saída ("CABLE Input (VB-Audio)"). Ícone check. Sem cabo: ícone alert e rótulo em accent-700, valor "Alto-falantes — sem cabo virtual".
   - "Sua voz" (ícone mic) → "Microfone (Realtek) misturado" ou "Não misturada".
   - "Seu fone" (ícone headphones) → nome do aparelho ou "Desligado".
7. Botão secundário de largura total "Configurar áudio →" (texto à esquerda, seta à direita): abre o assistente no passo 1.
8. Rodapé da barra (empurrado para baixo, borda superior 2px, padding 14px 16px, 10px de espaço):
   - Linha: "VOLUME GERAL" (rótulo) à esquerda, valor "80%" 14px/800 à direita.
   - Slider de volume geral (0–100), largura total.
   - Botão primário de largura total: ícone quadrado (parar) + "Parar tudo" + chip da tecla à direita ("Pause"; 11px/600, padding 1px 6px, borda 1px bg a 60%). Padding 10px 14px.

*Área principal* — coluna:
1. **Toolbar** — padding 12px 16px, borda inferior 2px, 8px de espaço:
   - Busca: até 340px de largura, altura 36px, fundo surface, borda 1px divider, ícone search 16px muted + campo sem borda, placeholder "Buscar sons, teclas ou arquivos". Esc limpa. Mesma regra de busca de hoje (`_matches`: todas as palavras precisam aparecer em nome+tecla+caminho).
   - Segmentado (borda 1px divider, separador 1px): "▦ Pads" | "☰ Lista", 13px, padding 7px 12px. Ativo: fundo accent, texto bg.
   - Espaço flexível.
   - Secundário "🔊 Tocando agora [N]" — abre/fecha a janela Tocando agora (seção 7). Chip com o número de vozes tocando (12px/800, padding 0 6px, mín. 20px): com vozes, fundo accent e texto bg; sem vozes, fundo text a 12%. Com a janela aberta, o botão fica com borda 1px **text** e fundo 7%.
   - Secundário "⤓ YouTube" (tooltip "Baixar do YouTube").
   - Primário "＋ Adicionar som" (abre o `QFileDialog` com os mesmos tipos de `AUDIO_TYPES`).
2. **Conteúdo** (rolagem vertical): Lista ou Pads (abaixo).
3. **Barra de status** — altura mínima 38px, padding 8px 16px, borda superior 2px, 13px:
   - Esquerda: ícone 14px + mensagem. Prioridade: (1) gravando tecla — "Aperte a tecla que vai tocar «Nome»  (Esc cancela)" / "Aperte a tecla para Parar tudo  (Esc cancela)", em accent-700, 800, ícone teclado; (2) recado temporário (`_flash`, some em 5–6 s), text 600; (3) "Tocando: Nome, Nome", ícone play, 600; (4) ocioso: "Pronto · 48000 Hz · aperte a tecla de um som, mesmo com a janela minimizada" em muted (sem cabo: "Os sons saem só no seu alto-falante").
   - Direita: avisos permanentes (os mesmos de `_warnings()`, mas com textos curtos), cada um com ícone alert 14px, 600, accent-700, 16px de espaço. Exemplos: "Sem cabo virtual: os outros não escutam", "Sua voz não sai junto", "1 arquivo não encontrado". Tooltip mostra a frase completa de hoje.

#### 1a. Visualização Lista (padrão na direção 1a)
Tabela custom (`QTableView` + delegate, ou `QListView` com delegate). Colunas: **130px** Tecla · **1,3fr** Som · **70px** Duração · **80px** No fone · **1,4fr** Arquivo · **176px** ações. Padding lateral 16px.
- Cabeçalho: altura 36px, borda inferior 2px, 11px maiúsculo, muted: "TECLA", "SOM", "DURAÇÃO", "NO FONE", "ARQUIVO".
- Linha: altura 48px, borda inferior 1px divider.
  - Tecla: chip 12px/800, padding 3px 8px, borda 1px divider; sem tecla mostra "—" em muted. Gravando: fundo accent, borda accent, texto bg, conteúdo "Aperte…"; e a linha inteira fica com fundo accent-100.
  - Som: 14px/600, cortado com "…". Arquivo ausente: tag "não encontrado" (11px, padding 2px 8px, fundo accent-100, texto accent-800).
  - Duração: "1,8 s" (vírgula decimal, considera o corte: `(end-start)`), 13px.
  - No fone: "80%" ou "—" se o som não toca no fone.
  - Arquivo: 12px muted, cortado com "…".
  - Ações (botões ícone 32×32, 2px de espaço, alinhados à direita): Ouvir (play; tocando vira stop com fundo accent e ícone bg) · Definir tecla (keyboard) · Cortar (scissors) · Configurar (sliders) · Remover (trash; hover fundo accent-100, ícone accent-800).
  - Progresso: faixa de 3px accent na base da linha, largura = fração tocada.
  - Selecionada: fundo text a 7%. Hover: 4%.
- Teclado: Enter = Ouvir, Delete = Remover (com a confirmação de hoje quando o arquivo está na pasta própria), duplo clique = Configurar som.

#### 1b. Visualização Pads
Grade de **3 colunas iguais** (direção 1b: 4 colunas). Separação de 2px na cor divider (grade visível: fundo divider + espaço de 2px entre células, ou desenhe as linhas). Borda inferior 2px. Células vazias no final da última linha são preenchidas com bg (nunca deixar buracos na cor da linha).
- Célula (min. 140px de altura, padding 14px 14px 16px, coluna com 6px de espaço):
  - Topo: tecla 28px/800 à esquerda ("—" em muted sem tecla); à direita dois botões ícone 28×28 com opacidade 75% (Definir tecla, Configurar som).
  - Base (empurrada para baixo): nome 15px/600 (pode quebrar em 2 linhas) e metadado 12px muted: "1,8 s  ·  fone 80%" ou "0,9 s  ·  só no mic" ou "arquivo não encontrado" (accent-700).
  - Barra de progresso: 4px na base, accent.
  - Estados: **tocando** = fundo accent, todo texto/ícone em bg, barra em bg. **Gravando tecla** = fundo accent-100, texto accent-800, contorno interno 2px accent, tecla mostra "Aperte…". **Selecionado** = contorno interno 2px text.
  - Clique = tocar (clicar de novo enquanto toca = parar aquele som). Duplo clique = Configurar som.
- Última célula: "Adicionar som" — ícone plus 26px, "Adicionar som" 15px/800 em accent, "wav, mp3, ogg, opus, flac, aiff" 12px muted, tudo alinhado embaixo à esquerda. Hover: accent a 8% sobre bg.
- Implementar a célula com `QPainter` (widget custom) dentro de um `QGridLayout` com espaçamento 2 sobre um container pintado de divider.

### 2. Configurar som (diálogo)
Substitui `_sound_dialog`. Abre com duplo clique, botão de configurar ou Enter+… Largura 520px.
Estrutura comum de **todos os diálogos**: véu neutral-900 a 55% sobre a janela (diálogo modal sem moldura centralizado; ou `QDialog` com moldura nativa — o importante é o conteúdo); caixa com fundo surface, sombra do token; cabeçalho padding 14px 16px com título 20px/800 e botão X 32×32, borda inferior 2px; corpo padding 16px com 16px de espaço; ações padding 12px 16px com borda superior 2px. Esc fecha.
- Campo "Nome" (rótulo 12px label; campo 36px, fundo bg, borda 1px divider, cursor accent; foco = borda accent). Enter confirma. Abaixo, o caminho do arquivo 12px muted, cortado com "…". Renomear segue `_rename` (renomeia o arquivo quando está na pasta própria).
- Bloco em duas células iguais, contorno 2px, divisória 2px:
  - "🎙 NO MICROFONE" (rótulo) / "100%" 32px/800 / slider 0–100 / "O que os outros escutam" 12px muted.
  - "🎧 NO MEU FONE" + checkbox à direita (= "Tocar também no meu fone") / "80%" 32px/800 (ou "—") / slider (desabilitado e célula a 55% quando desmarcado) / "Tocar também no meu fone" 12px muted.
- Linha da tecla: fundo bg, borda 1px, padding 10px 12px: ícone teclado + "Tecla" + chip com a tecla + ghost "Trocar" (fecha o diálogo e entra no modo gravar tecla).
- Ações: secundários "▶ Ouvir" e "✂ Cortar" à esquerda; primário "Pronto" à direita.
- Mudanças nos sliders salvam com atraso (como `_save_later`) e valem para os próximos toques.

### 3. Cortar som (diálogo)
Substitui `_trim_dialog`. Largura 720px.
- Texto 13px label: "Arraste as alças para marcar onde «Nome» começa e termina. O arquivo original não é alterado."
- Forma de onda (`QPainter`): altura 150px, fundo bg, contorno 2px divider, 96 barras verticais com 2px de espaço entre elas, centralizadas na vertical, altura proporcional ao pico (`audio.peaks`). Barras dentro do trecho: accent; fora: text a 35%. Regiões fora do trecho ganham um véu de bg a 55%.
  - Alças: linha vertical de 3px accent em `start` e em `end`, com uma "bandeira" accent de 14×18px — no topo à direita da linha de início e na base à esquerda da linha de fim. Clique/arraste em qualquer ponto move a alça mais próxima; distância mínima entre alças = 3% da duração. Cursor ↔.
- Três células iguais (contorno 2px, divisórias 2px): "INÍCIO" / "FIM" / "TRECHO" (rótulo 11px) com valor 20px/800 ("0,4 s"); TRECHO em accent-700.
- Ações: secundário "▶ Ouvir trecho", ghost "Tudo" (start=0, end=fim), primário "Salvar corte". Grava só `start`/`end` em segundos no `nicopad.json` (não destrutivo, como hoje).

### 4. Baixar do YouTube (diálogo)
Substitui `_youtube_dialog`. Largura 520px.
- "URL do vídeo" (rótulo) + linha com campo (placeholder "https://www.youtube.com/watch?v=…") e primário "⤓ Baixar" ao lado, 8px de espaço.
- Barra de progresso de 6px: trilho text a 12%, preenchimento accent, sem raio.
- Status 13px label (mín. 19px de altura): validação de `youtube.check_url` ("Cole a URL de um vídeo do YouTube."), "Baixando… 42%  ·  1,8 MB de 4,2 MB", ou "Erro: …".
- Nota 12px muted: "O áudio vai direto para a pasta dos sons e aparece na lista pronto para receber uma tecla."
- Durante o download: campo e botão desabilitados (45%). Ao terminar: fecha, adiciona o som, seleciona e mostra o recado "«Nome» baixado e adicionado — agora clique em «Definir tecla»."
- **Sem ffmpeg** (não desenhado; manter o comportamento de hoje no novo estilo): o corpo mostra um bloco com faixa accent-100/accent-800 "O download precisa do ffmpeg instalado, e ele não foi encontrado neste PC." e as ações "Abrir site do ffmpeg" (primário) e "Fechar".

### 5. Guia do cabo "?" (diálogo)
Substitui `_show_help`. Largura 620px.
- Frase de abertura (14px, padding 14px 16px, borda inferior 2px): "O microfone dos outros jogadores precisa de um cabo de áudio virtual (driver VB-Cable)."
- 5 linhas (grade 56px + resto, borda inferior 1px): número 24px/800 accent + texto 14px. Textos = os 5 passos do `HELP` atual.
- Rodapé 12px muted com a nota da licença e o crédito ao VB-Cable (texto do `HELP`).
- Ações: primário "🔌 Preparar instalador do cabo" (`_prepare_cable`), secundário "Abrir site do VB-Cable", e à direita ghost "Abrir assistente" (fecha e abre o assistente).

### 7. Tocando agora (janela solta, não modal)
Substitui `_active_window` / `_refresh_active` / `_on_active_click`. É uma **janela de verdade** (`QWidget` com `Qt.Window`, não um diálogo modal): os atalhos e a janela principal continuam funcionando com ela aberta. Abrir de novo traz a mesma janela para frente. Tamanho 600×~420, mínimo 560×240. No protótipo ela aparece flutuando no canto inferior direito da janela principal só para caber na maquete.
Usa a API que já existe: `engine.active()` → `(id, nome, fração, loop, nível)`, `engine.stop_voice(id)`, `engine.set_loop(id, bool)`, `engine.set_level(id, nível)`. Atualizar a cada `ACTIVE_REFRESH_MS` (200 ms) **sem recriar as linhas** (atualizar valores no lugar, para não piscar), como o código atual faz.
- Cabeçalho (padding 14px 16px, borda inferior 2px): "Tocando agora" 20px/800 + resumo 13px muted: "3 sons · 2 em loop" (sem vozes: vazio).
- Cabeçalho das colunas (altura 30px, borda inferior 1px, 11px maiúsculo muted): "SOM · TOCADO" | "VOLUME" | — | —. Colunas: **1fr** · **136px** · **88px** · **92px**, 12px de espaço, padding lateral 16px.
- Linha (padding 12px 16px, borda inferior 1px):
  - Coluna 1: nome 14px/600 (cortado com "…") e, à direita, a porcentagem tocada 12px/800 ("42%"); embaixo, barra de 4px (trilho text a 12%, preenchimento accent) com a fração tocada. Em loop, a barra volta a zero a cada volta.
  - Volume: controle com contorno 1px divider: botão "−" 34×32 | valor 13px/800 centralizado ("100%") | botão "+" 34×32 (divisórias 1px). Passo `LEVEL_STEP` (10%), de 0% a `LEVEL_MAX` (200%). Acima de 100% o valor fica em accent-700.
  - "⟲ Loop" (botão 34px de altura, 13px/800, ícone repeat 14px): desligado = secundário; ligado = fundo accent, borda accent, texto bg.
  - "■ Parar" (secundário 34px; hover fundo accent-100, texto accent-800): para só aquela voz.
- Lista rola depois de ~4 linhas (máx. 264px).
- Vazio: padding 28px 16px, "Nada tocando" 15px/800 + "Aperte a tecla de um som ou clique num pad. Ele aparece aqui enquanto toca." 13px muted.
- Rodapé (padding 12px 16px, borda superior 2px): primário "■ Parar tudo [Pause]" + nota 12px muted "Janela solta: os atalhos e a janela principal continuam valendo."
- O texto de ajuda atual ("Clique em «Loop» para repetir…") sai: os rótulos dos botões já dizem isso.

### 8. Fechar a janela (diálogo)
Substitui `_ask_close_action`. Largura 460px, estrutura comum dos diálogos, título "Fechar a janela".
- "Fechar o nicoPad ou deixá-lo na bandeja?" 15px; nota 13px label: "Na bandeja, os atalhos continuam funcionando e os sons saem normalmente."; checkbox "Lembrar minha escolha".
- Ações: primário "Deixar na bandeja", secundário "Encerrar o programa", e à direita ghost "Cancelar". Mesma lógica de hoje (`close_action`, sem bandeja encerra direto). Esc = Cancelar.

### 6. Assistente de primeiro uso
Novo. Abre sozinho **na primeira execução** (sem `nicopad.json`) e quando não há cabo virtual e o usuário nunca concluiu o assistente (gravar `setup_done: true` no `Settings`). Também abre por "Configurar áudio" e por "Abrir assistente". Cobre a janela toda (é uma página da janela, ex. `QStackedWidget`, não um diálogo).
Grade de 2 colunas: **400px** + resto.
- **Coluna esquerda** (fundo accent, texto bg, padding 32px, 24px de espaço): quadrado branco 112×112 com a logo 100×100; título "Seus sons no microfone dos outros." 38px/800; embaixo, lista de passos com borda superior e inferior de 2px (bg a 45%) em cada linha, padding 11px 0, grade 40px | texto | 20px: "01 Cabo de áudio virtual", "02 Seus aparelhos", "03 No Discord ou no jogo", "04 Pronto". Atual em 800; futuros com opacidade 70%; concluídos com check à direita.
- **Coluna direita**: conteúdo com padding 40px 48px, largura máx. 680px, 20px de espaço; rótulo "PASSO N DE 4" 11px/600 accent-700; título 32px/800.
  - **Passo 1 — Cabo de áudio virtual.** Texto: "Nenhum programa consegue «falar» direto dentro de um microfone: é preciso um cabo de áudio virtual, um dispositivo de áudio falso. Instale o VB-Cable uma vez e o nicoPad usa ele sozinho."
    - Encontrado (`audio.is_virtual_cable`): bloco contorno 2px, fundo surface, grade 48px | resto; célula esquerda fundo text com check bg 20px; "Cabo encontrado" 800 + "CABLE Input (VB-Audio Virtual Cable)" 13px label.
    - Não encontrado: bloco contorno 2px; faixa accent-100/accent-800 800 com alert "Nenhum cabo virtual neste PC"; duas linhas numeradas ("Prepare o instalador oficial (vem dentro do app)." / "Execute VBCABLE_Setup_x64.exe como administrador e reinicie o PC."); botões primário "Preparar instalador do cabo" e secundário "↻ Já instalei — procurar de novo" (recarrega aparelhos = `_reload_devices`).
  - **Passo 2 — Seus aparelhos.** Bloco contorno 2px com 3 linhas (grade 200px | resto, padding 14px, separadas por 1px):
    - "Tocar no mic" / "saída — o cabo virtual" → select de saída (mesma lista filtrada de hoje: só cabos se houver).
    - checkbox "Misturar meu microfone" / "sua voz sai junto" → select de entrada (desabilitado se desmarcado).
    - checkbox "Ouvir no meu fone" / "você escuta o que toca" → select de saída (desabilitado se desmarcado).
    - Mic desmarcado: aviso accent-700 600 com alert: "Sem o microfone misturado, sua voz para de sair junto com os sons."
    - Selects: altura 36px, fundo surface, borda 1px divider, raio 0, 14px. Estilizar o popup do `QComboBox` (fundo surface, item hover accent-100).
  - **Passo 3 — No Discord ou no jogo.** "Troque o microfone de entrada para:" + caixa com contorno 2px **text**, padding 16px, ícone mic 22px + "CABLE Output (VB-Audio Virtual Cable)" 22px/800. Texto: "Toque um som de teste e confira no Discord se o indicador de voz acende." Botão secundário "▶ Tocar som de teste" (enquanto toca: fundo accent, texto bg, "Tocando…"; depois "Tocar de novo"). Precisa de um som curto de teste embutido em `packaging/`.
  - **Passo 4 — Pronto.** "Adicione um som e dê uma tecla para ele. O atalho funciona com a janela minimizada ou atrás do jogo, e a tecla continua funcionando normalmente no jogo." + três células iguais (contorno 2px, divisórias 2px), cada uma com ícone, título 800 e nota 12px: "Adicionar som / ou baixar do YouTube", "Definir tecla / aperte a tecla; Esc cancela", "Parar tudo / tecla própria, sempre ativa".
- **Rodapé** (padding 16px 48px, borda superior 2px): secundário "Voltar" (desabilitado no passo 1), ghost "Pular", espaço, primário "Continuar →" (mín. 180px, texto à esquerda e seta à direita, 15px/800, padding 10px 16px). No passo 4 o primário diz "Abrir o nicoPad".

---

## Interactions & Behavior
- **Atalhos globais**: iguais aos de hoje (`KeyboardHook`). Enquanto um campo de texto tem foco, as teclas não tocam sons (`typing`).
- **Definir tecla**: botão teclado na linha/pad ou "Trocar" no diálogo → modo gravação (estados visuais acima + status). A próxima tecla vira o atalho; Esc cancela ("Nenhuma tecla foi definida."). Tecla repetida tira a tecla do outro som e avisa: "«A» agora toca com F1.  (a tecla saiu de «B»)". Mesma regra para a tecla de Parar tudo. **Gravar a tecla de Parar tudo**: clique direito no botão "Parar tudo" → "Definir tecla…" (substitui o botão "Tecla p/ parar tudo").
- **Tocar**: clique no pad, botão ▶ da linha, atalho global. Vários sons podem tocar juntos; cada um mostra o próprio progresso (atualizar a ~16–30 fps com `QTimer` só enquanto algo toca; o motor precisa expor posição/duração de cada voz — se não expuser, estimar com o tempo desde o disparo e a duração do trecho).
- **Parar tudo**: botão ou tecla → limpa todos os progressos (e a lista do Tocando agora), recado "Sons interrompidos."
- **Loop e volume ao vivo**: definidos por voz na janela Tocando agora; o progresso dos pads/linhas usa a mesma fração de `engine.active()` (resolve o "se o motor não expuser" acima: ele já expõe).
- **Trocar mapa**: clique na barra lateral → recado "Mapa «X» ativo."; cancela gravação de tecla pendente.
- **Remover**: mesmo fluxo de confirmação de `_remove_selected`.
- **Tema**: botão lua/sol alterna e salva (`theme: "claro"|"escuro"` no `Settings`). Padrão: seguir o sistema (`QGuiApplication.styleHints().colorScheme()`) na primeira execução.
- **Pads/Lista**: salvar a escolha (`view: "pads"|"lista"`).
- **Fechar a janela**: igual a hoje (perguntar bandeja / encerrar / cancelar, conforme `close_action`). O `QMessageBox` deve seguir o mesmo estilo (fundo surface, botões no estilo acima).
- **Atualizações**: igual a hoje; a janelinha de progresso usa a barra de 6px do YouTube.
- Sem animações além do progresso. Hover/pressed trocam a cor na hora (sem transição).

## State Management
Novos campos no `Settings` (`config.py`, com padrão e leitura tolerante como os atuais): `theme`, `view`, `setup_done`. O resto do estado é o de hoje (`maps`, `active`, dispositivos, `volume`, `stop_*`, `library*`, `close_action`). Estado só de interface: som selecionado, modo gravação (`pending`), sons tocando + início/duração, diálogo aberto, passo do assistente, recado temporário.

## Direção 1b "Mesa" (alternativa, só se pedirem)
Mesmo conteúdo, chrome diferente:
- **Cabeçalho vermelho** 64px (fundo accent, texto bg): bloco da marca (quadrado branco 40×40 com logo 36, "nicoPad" 26px/800, borda direita 2px bg a 40%); **mapas como abas** (padding 0 18px, 15px/800 + contagem 11px/600, borda direita 2px bg a 40%; ativa = fundo bg, texto accent; hover accent-600); botão "+" 56px; à direita "Perfis ▾", configurações, tema, "?" em bg.
- **Faixa de roteamento**: 4 células iguais com divisórias 2px e borda inferior 2px, padding 10px 16px: "TOCAR NO MIC" / "SUA VOZ" / "SEU FONE" (rótulo 11px com ícone + valor 13px/600; clicáveis, abrem o assistente; sem cabo a primeira célula fica com fundo accent-100 e rótulo accent-700) e "VOLUME GERAL" com valor e slider.
- Sem barra lateral. Pads em 4 colunas, 150px de altura, tecla 34px. Toolbar ganha à direita "■ Parar tudo [Pause]" com fundo text e texto bg.
- Abre nos Pads.

## Assets
- `design/packaging/nicopad.png` — a logo atual (`packaging/nicopad.png` do repo). Sempre sobre um quadrado `#ffffff`, nunca em escala de cinza.
- **Fonte Archivo** 400/600/800 — Google Fonts (OFL). Embutir.
- **Ícones Lucide** (24×24, traço 2, pontas arredondadas; play e stop preenchidos): `play`, `square` (parar), `plus`, `x`, `minus`, `search`, `sliders-horizontal`/`settings-2` (configurar), `scissors`, `keyboard`, `trash-2`, `download`, `layout-grid`, `list`, `circle-help`, `mic`, `headphones`, `check`, `triangle-alert`, `moon`, `sun`, `chevron-down`, `plug`, `arrow-right`, `refresh-cw`, `volume-1`, `repeat`. Tamanhos: 14–16px em botões e linhas, 18px no cabeçalho, 22–26px nos destaques.

## Files
- `design/nicoPad Redesign.dc.html` — página com todas as telas lado a lado (1a, 1b e a referência atual). **Comece por aqui.**
- `design/nicoPad App.dc.html` — o protótipo interativo. A lógica está no `<script>` no fim do arquivo: estados, textos, regras de tecla, corte e download simulado. Parâmetros: `direction` (A/B), `theme`, `screen` (principal/tocando/onboarding/config/cortar/youtube/guia/fechar), `semCabo`.
- `design/nicoPad Atual.dc.html` — a janela de hoje em Tkinter, como referência do que está sendo substituído.
- `design/_ds/.../styles.css` — tokens do sistema Modernist (fonte dos hex acima).
- `nicopad.qss.tmpl` — QSS inicial com os tokens como `{placeholders}`.
- `tokens.json` — tokens dos dois temas em formato de máquina.

## Ordem sugerida
1. `theme.py` + QSS + fonte + ícones; janela vazia com cabeçalho, barra lateral, toolbar e status nos dois temas.
2. Lista (com delegate) ligada ao `Settings` atual; Definir tecla; busca; mapas.
3. Pads (widget custom) + progresso.
4. Tocando agora (janela solta) e diálogos: Configurar, Cortar (waveform), YouTube, Guia, Fechar.
5. Assistente + `setup_done`.
6. Remover o Tkinter; atualizar `ui.py` → `ui/` (pacote), `requirements.txt` (`PySide6`), `.spec` do PyInstaller (fontes, ícones, plugins Qt), `selftest.py` (rodar sem abrir janela com `QT_QPA_PLATFORM=offscreen`) e o README do repo.
