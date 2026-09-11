# nicoPad

Painel simples para tocar sons do PC **no seu microfone**, para os outros jogadores ouvirem.
Cada som tem um atalho global: funciona com a janela minimizada ou atrás do jogo,
e a tecla **continua funcionando normalmente** no jogo.

- Sons ficam na memória: o som sai no mesmo instante em que você aperta a tecla.
- Cada som tem os próprios volumes (no mic e no fone) e decide se sai também no seu fone.
- O microfone de verdade pode ser misturado junto, para a sua voz não sumir.
- Um único `.exe`, sem instalar nada além do cabo de áudio virtual do Windows.
- Ao fechar a janela, o app pergunta: vai para a **bandeja do sistema** (Windows e Linux) e
  continua tocando os sons pelos atalhos, ou encerra de vez.

## Começando

```bash
task setup     # cria .venv e instala as dependências (uma vez)
task run       # abre o app pelo código-fonte
task build     # gera dist/nicopad.exe
task cable     # coloca o instalador oficial do cabo de áudio na sua pasta
task test      # verificação automática, sem abrir a interface
```

Se `py -3.12` não existir na sua máquina: `task setup PY=python`.
Precisa de Python 3.10+ (o projeto foi testado com 3.12).

## O único passo manual: o cabo virtual

Nenhum programa no Windows consegue "falar" direto dentro de um microfone: é preciso um
**cabo de áudio virtual**, que é um dispositivo de áudio falso. Instale uma vez o
[VB-Cable](https://vb-audio.com/Cable/) (grátis) e configure assim:

1. Instale o VB-Cable. Ele cria dois dispositivos chamados `CABLE Input` (saída) e
   `CABLE Output` (entrada).
2. No nicoPad, em **Tocar no mic (saída)**, escolha `CABLE Input (VB-Audio Virtual Cable)`.
   O app já seleciona isso sozinho quando encontra o cabo — o botão **Atualizar** recarrega a
   lista depois de instalar.
3. Marque **Misturar meu microfone** e escolha o seu microfone de verdade. Sem isso, a sua
   voz para de sair junto com os sons.
4. No Discord/jogo/gravador, troque o microfone de entrada para
   `CABLE Output (VB-Audio Virtual Cable)`.
5. Marque **Ouvir os sons também no meu fone** se quiser escutar o que você toca.

Tudo isso também está dentro do app: clique no **?**, no canto superior direito da janela.

> Sem o cabo virtual o app continua funcionando, mas os sons saem só no seu alto-falante:
> os outros não escutam. O app avisa isso em vermelho na barra de status.

## Usando

| Ação             | Como                                                                               |
| ---------------- | ---------------------------------------------------------------------------------- |
| Adicionar sons   | **Adicionar som** (aceita vários de uma vez): wav, mp3, ogg, opus, flac, aiff      |
| Configurar o som | Selecione o som e clique em **Configurar som** (ou duplo clique na linha da lista) |
| Escolher a tecla | Selecione o som e clique em **Definir tecla**; depois aperte a tecla (Esc cancela) |
| Ouvir um som     | **Ouvir** ou Enter (toca sempre no seu fone)                                       |
| Parar os sons    | **Parar tudo**                                                                     |
| Remover          | Selecione e clique em **Remover** (ou tecle Delete)                                |
| Volume geral     | Barra **Volume** (o volume de cada som fica em **Configurar som**)                 |
| Buscar           | Campo **Buscar**: aceita várias palavras; Esc limpa                                |
| Fechar           | O X da janela (ou Alt+F4) pergunta: bandeja do sistema ou encerrar o programa      |

Tecla já usada por outro som: o som anterior perde a tecla e o app avisa na barra de status.

## Fechar e a bandeja do sistema

O X da janela (ou Alt+F4) não encerra nada sem perguntar antes:

| Botão    | O que acontece                                                |
| -------- | ------------------------------------------------------------- |
| Sim      | A janela sai da frente e o nicoPad fica na bandeja do sistema |
| Não      | O programa é encerrado                                        |
| Cancelar | Está tudo como estava: a janela continua aberta               |

Na bandeja, o ícone do nicoPad tem **Abrir o nicoPad** (clicar nele também abre) e **Sair**.
Enquanto ele está lá, os atalhos globais continuam funcionando e os sons saem normalmente; a
bandeja ainda mostra um aviso, para você não pensar que o programa sumiu.

Se a bandeja não estiver disponível (Linux sem X11, por exemplo), o app avisa em vermelho na
barra de status e o X encerra o programa, sem perguntar.

## A barra de cima

A logo do **nicoPad** fica num canto e, no outro, três coisas:

- **Perfis** — exportar e importar os sons e a configuração em um `.zip`.
- **Configurações** — guardar cópia dos sons, escolher e abrir a pasta, preparar o instalador do
  cabo de áudio e abrir o site do VB-Cable.
- **?** — o guia de configuração do cabo (o mesmo texto que está aqui).

A tecla de cada som aparece com o nome dela (`Shift direito`, `F1`, `/`) — os atalhos antigos que
ficaram como `VK 0x…` são renomeados sozinhos ao abrir o app.

## Cada som tem a sua configuração

Duplo clique em um som (ou **Configurar som**) abre a janela daquele som:

- **Nome** — o nome que você quiser para o som. Se ele estiver na pasta própria, o arquivo é
  renomeado junto (o que não vale como nome de arquivo vira `_`); se não, só o rótulo muda.

- **Volume no microfone** — o quanto ESTE som sai no seu mic, sem mexer nos outros.
- **Tocar também no meu fone** — desmarcado, o som sai só para os outros.
- **Volume no meu fone** — o volume dele apenas no seu fone.

A coluna **No fone** da lista mostra a porcentagem (ou `—` quando o som não sai no seu fone).
A barra **Volume** continua sendo o volume geral. O volume por som vale para os próximos
toques daquele som, não para o que já está tocando.

## Guardar os sons em uma pasta do programa

Vem ligada por padrão: cada som adicionado é copiado para uma pasta chamada **`sons`**
(`%PROGRAMDATA%\nicoPad\sons` no Windows; `$XDG_DATA_HOME/nicopad/sons` ou
`~/.local/share/nicopad/sons` no Linux), ou para a pasta que você escolher em
**Escolher a pasta dos sons…**. O próprio item do menu mostra a pasta em uso.

A lista passa a apontar para as cópias, então mover, renomear ou apagar o arquivo original não
quebra mais o atalho. Arquivo idêntico não é copiado duas vezes e nada é sobrescrito: nome
repetido vira `nome (2).wav`. **Abrir a pasta dos sons** mostra a pasta no Explorer.

Remover um som da lista (**Remover** ou Delete) pergunta antes e **apaga o arquivo junto** — mas só
quando ele está nessa pasta. Os seus arquivos originais nunca são tocados, e desligar
**Guardar cópia dos sons** deixa tudo como está.

## Perfis: levar os sons para outra máquina

No menu **Perfis**:

- **Exportar perfil…** gera um `.zip` com a configuração (sons, teclas, volumes, dispositivos)
  e os arquivos de som. Sons cujo arquivo não existe mais ficam de fora e são avisados.
- **Importar perfil…** pergunta a pasta onde descompactar os sons e substitui a configuração
  atual pela do perfil — som, tecla e volumes voltam como estavam.

## Lista de dispositivos enxuta

A lista mostra cada aparelho **uma vez só** (o Windows repete o mesmo aparelho em WASAPI,
DirectSound e MME) e esconde atalhos que não são aparelhos de verdade, como
`Mapeador de som da Microsoft` e `Driver de som primário`. Se o aparelho escolhido falhar, o
app tenta as outras APIs de áudio sozinho.

**Tocar no mic (saída)** mostra só cabos virtuais (VB-Cable, Voicemeeter) quando algum está
instalado — é o único tipo de aparelho que faz os outros escutarem. Sem nenhum cabo, a lista
mostra todas as saídas, para você poder testar; a barra de status avisa em vermelho.

## O cabo de áudio já vem embutido

O app carrega dentro dele o pacote oficial do VB-Cable (1,3 MB, assinado digitalmente pela
VB-Audio, SHA-256 conferido a cada uso). No menu **Configurações** (lá dentro,
**Preparar instalador do cabo de áudio**) ou por
`task cable`, o nicoPad copia e descompacta esse pacote original em
`%LOCALAPPDATA%\nicoPad\cabo-de-audio` e abre a pasta com o instalador já selecionado.

Sobram dois cliques: **executar `VBCABLE_Setup_x64.exe` como administrador** e
**reiniciar o PC**. Depois clique em **Atualizar** e escolha `CABLE Input`.

Por que o app não instala sozinho: a licença do VB-Cable (dentro do próprio pacote) permite
"copiar e difundir o pacote AS IS sem nenhuma modificação", mas proíbe "integrar o pacote ao
procedimento de instalação de outro programa". Então o nicoPad entrega o pacote original,
íntegro, e a instalação do driver continua sendo um ato seu. Se o pacote embutido não existir
(rodando direto do código-fonte), o app baixa o mesmo arquivo do endereço oficial e confere o
SHA-256 antes de usar.

> VB-Cable é donationware de Vincent Burel (www.vb-cable.com). Se ele for útil para você,
> considere participar do projeto.

## Tarefas

| Tarefa       | O que faz                                                                                   |
| ------------ | ------------------------------------------------------------------------------------------- |
| `task setup` | Cria `.venv` e instala `requirements.txt`                                                   |
| `task run`   | Roda pelo código-fonte                                                                      |
| `task test`  | Verifica som, mistura, lista de aparelhos, pasta dos sons, perfil, motor de áudio e atalhos |
| `task cable` | Copia e descompacta o instalador oficial do cabo de áudio (VB-Cable) na sua pasta           |

| `task logo` | Redesenha a logo do app (`packaging/nicopad.png` e `packaging/nicopad.ico`) |
| `task build` | Gera `dist/nicopad.exe` (PyInstaller, arquivo único, sem console) |
| `task verify` | Roda a verificação dentro do `.exe` gerado |
| `task clean` | Apaga `.venv`, `build/`, `dist/` e caches |

`task build` roda `task logo` antes (para o ícone do `.exe`) e só recompila quando algum arquivo
de `src/` muda (ou use `task build --force`).
O build usa uma lista de exclusões (scipy, matplotlib, pytest, setuptools...) para o `.exe`
ficar enxuto, e embute as DLLs do PortAudio e do libsndfile.

## Onde ficam as coisas

- `nicopad.json` — configuração (dispositivos, volume, sons, teclas e o tamanho da janela), ao lado do
  `.exe` (ou na raiz do projeto quando roda pelo código-fonte). É texto simples, dá para
  editar à mão.
  Se ele ficar ilegível (edição manual), o app guarda uma cópia em `nicopad.json.invalido`
  antes de recomeçar do zero.
- a pasta **`sons`** (`%PROGRAMDATA%\nicoPad\sons` no Windows, `~/.local/share/nicopad/sons`
  no Linux) — cópias dos sons, já ligada por padrão e configurável em **Configurações**.
- `nicopad-selftest.txt` — relatório da última verificação automática.

## Problemas comuns

| Sintoma                      | Causa                                                                                                   |
| ---------------------------- | ------------------------------------------------------------------------------------------------------- |
| Os outros não escutam        | A saída não é o `CABLE Input`, ou o microfone do Discord ainda não é o `CABLE Output`                   |
| Microfonia/apitos            | **Misturar meu microfone** ligado na saída padrão (alto-falante). Escolha o `CABLE Input`               |
| Sua voz sumiu                | **Misturar meu microfone** desmarcado, ou o microfone errado selecionado                                |
| A tecla não toca no jogo     | Jogos em modo exclusivo/anti-cheat podem bloquear hooks. Teste em outro jogo ou use uma tecla diferente |
| Atalho repetindo sem parar   | Não acontece: segurar a tecla conta como um toque só                                                    |
| «Arquivo não encontrado»     | O original foi movido/apagado: remova o som e adicione de novo, ou use a pasta própria                  |
| Som saiu diferente no perfil | O volume por som ficou em 0% ou o som está sem «Tocar também no meu fone»                               |

O app não abre sozinho com o Windows. Para isso, crie um atalho de `dist\nicopad.exe` na
pasta `shell:startup` (Win+R → digite `shell:startup`).

## Estrutura

```
src/nicopad/
  __main__.py   ponto de entrada (e a flag --selftest)
  ui.py         janela do Tkinter: barra superior, lista de sons, busca e configuração por som
  audio.py      dispositivos, sons na memória, mistura e passa-voz do microfone
  library.py    pasta própria dos sons (cópia sem sobrescrever nada)
  profile.py    perfil: sons + configuração em um .zip
  hotkeys.py    hook global de teclado do Windows (só ctypes, sem dependências)
  tray.py       ícone na bandeja do sistema: abrir a janela e encerrar o app
  config.py     configuração em JSON
  selftest.py   verificação automática do app compilado ou não
packaging/logo.py        desenha a logo (.png e .ico), sem nenhuma dependência
packaging/nicopad.spec   receita do executável (embute a logo e o pacote do cabo)
Taskfile.yml             setup, logo, run, test, build, verify, clean
```
