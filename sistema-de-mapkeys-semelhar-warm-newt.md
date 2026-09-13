# mapKeys, download do YouTube e corte de som

## Context

Hoje o nicoPad tem **uma única lista** de sons/teclas (`Settings.bindings`) e "perfil" significa apenas
exportar/importar tudo num `.zip` — não há troca rápida. Três lacunas:

1. **mapKeys** — conjuntos de teclas+sons nomeados, trocáveis por um dropdown, criados/editados/excluídos
   como os sons já são hoje. Vivem *dentro* do perfil: o `.zip` leva todos os mapas.
2. **YouTube** — hoje só dá para adicionar arquivos que já estão no disco. Falta baixar direto pela URL,
   com a música indo para a pasta própria dos sons.
3. **Corte** — um som baixado do YouTube quase sempre tem intro/final sobrando, e não há como aparar.

Decisões já tomadas com o usuário:
- Alternar mapKey troca **só sons e teclas**; dispositivos de áudio, volume geral e pasta dos sons continuam globais.
- Sem ffmpeg no PC, o modal do YouTube **avisa e abre o site** (não baixa ffmpeg nem salva formato ilegível).
- O corte é **não destrutivo**: início/fim em segundos no `nicopad.json`; o arquivo nunca é reescrito.
- O dropdown de mapKeys fica **acima da lista de sons**, dentro do quadro «Sons».

---

## 1. Modelo de dados — [config.py](src/nicopad/config.py)

Novo dataclass e dois campos novos em `Binding`:

```python
@dataclass
class Binding:
    ...                     # campos de hoje, sem mexer
    start: float = 0.0      # segundos aparados do começo
    end: float = 0.0        # segundo onde o som acaba; 0 = até o fim do arquivo

@dataclass
class KeyMap:
    name: str = "Padrão"
    bindings: list = field(default_factory=list)
```

`Settings` **perde o campo** `bindings` e ganha `maps: list` + `active: int`. Para não reescrever as ~25
chamadas `self.settings.bindings` espalhadas por [ui.py](src/nicopad/ui.py), `bindings` volta como
**property somente-leitura** do mapa ativo:

```python
@dataclass
class Settings:
    ...
    maps: list = field(default_factory=list)
    active: int = 0

    def __post_init__(self):
        if not self.maps:
            self.maps = [KeyMap()]
        self.active = max(0, min(int(self.active or 0), len(self.maps) - 1))

    @property
    def bindings(self) -> list:      # o mapa ativo; `maps` é o que vai para o JSON
        return self.maps[self.active].bindings
```

Property não é `field`, então `asdict(settings)` grava `maps`/`active` e **não** grava `bindings` — o
formato novo sai limpo. Os únicos pontos que *atribuíam* `settings.bindings` são `cfg.load` (L126) e
`profile.load`, ajustados abaixo.

**Migração** em `load()` (mesmo estilo tolerante do `LEGACY`): se o JSON traz `bindings` e não traz `maps`,
vira `[KeyMap("Padrão", <bindings migrados>)]`. Novo sanitizer `_keymap(raw)` ao lado de `_binding`,
reusando `_binding` para cada item e caindo em `KeyMap()` quando o registro está quebrado. `_binding`
passa `start`/`end` por um `_seconds(value)` novo (≥ 0, não-finito vira 0) — `_level` não serve porque
segundos não têm teto 1.0.

## 2. Corte aplicado na carga — [audio.py](src/nicopad/audio.py)

`load_sound(path, ..., start=0.0, end=0.0)` fatia logo após o `sf.read`, antes de normalizar canais:

```python
first = max(0, int(start * samplerate))
last = min(len(data), int(end * samplerate)) if end else len(data)
if last - first < 1:      # corte inválido (arquivo trocado, JSON editado à mão): toca inteiro
    first, last = 0, len(data)
data = data[first:last]
```

Como o corte entra na carga, `Sound.data` já nasce aparado — o mixer, o `_cache` por samplerate e o
`preview` continuam sem saber que corte existe. Mudar o corte = recarregar o `Sound` com `load_sound`.

Função nova para a onda, junto do resto do numpy:

```python
def peaks(data: np.ndarray, columns: int) -> np.ndarray:
    """(columns, 2) com o mínimo e o máximo de cada faixa: a silhueta da onda."""
```
Mono-mix (`data.mean(axis=1)`), particiona em `columns` blocos com `np.array_split` e devolve min/max.
É a única conta que o Canvas precisa.

## 3. Perfil leva todos os mapas — [profile.py](src/nicopad/profile.py)

`export` e `load` hoje varrem `payload["bindings"]`; passam a varrer `payload["maps"][i]["bindings"]`.
Em `export`, o laço atual vira um laço interno dentro de
`for raw_map, keymap in zip(payload["maps"], settings.maps):`, com `kept` por mapa e `raw_map["bindings"] = kept`.
Em `load`, idem, montando a lista de cada mapa. `used` (nomes dentro do zip) continua **global**: dois
mapas podem apontar para o mesmo arquivo e não pode virar duas cópias no zip nem no disco.
O resto — `_extract_sounds`, recusa de path traversal, `geometry` zerada — fica como está.

## 4. Interface — [ui.py](src/nicopad/ui.py)

### 4.1 Seletor de mapKeys (`_build`, quadro «Sons»)

Linha nova como `row=0` do LabelFrame; toolbar/busca/tree descem para 1/2/3 e
`sounds.rowconfigure(2, weight=1)` vira `rowconfigure(3, weight=1)`:

```
Mapa: [ Padrão ▾ ]  [Novo]  [Renomear]  [Excluir]
```
Combobox `state="readonly"`, `values` = nomes dos mapas, `bind(COMBO, ...)`. Os três botões ficam
compactos à direita do combo (`width=10`), como a toolbar de sons já faz.

Métodos novos, todos no padrão já existente (mexem em `self.settings`, chamam `_save()` e `_flash()`):

| Método | O que faz |
|---|---|
| `_sync_maps()` | Recarrega `values` do combo e seleciona `settings.active`. Chamado no boot, ao trocar/criar/excluir e em `_apply_settings`. |
| `_switch_map()` | `settings.active = combo.current()`; `self.sounds = {}`; `_load_bindings()` (já refaz keymap e linhas); `_save()`; flash com o nome. |
| `_new_map()` | Pede o nome, cria `cfg.KeyMap(name)` vazio, ativa, `_switch`-like. |
| `_rename_map()` | Pede o nome, grava em `maps[active].name`, `_sync_maps()`, `_save()`. |
| `_delete_map()` | `askyesno` avisando quantos sons saem da lista; recusa excluir o último mapa; **não apaga arquivo nenhum** do disco; ativa o vizinho. |

Os dois que pedem nome usam `tkinter.simpledialog.askstring` (stdlib, já disponível) envolvido por
`self.typing = True/False` — sem isso o que o usuário digitar dispara os sons, o mesmo cuidado que
`_quiet_while_typing` resolve nos campos da janela.

### 4.2 Remover som: não apagar arquivo usado por outro mapa

Correção de causa em `_remove_selected` (L473) — hoje ele apaga o arquivo da pasta própria sem olhar os
outros mapas, o que quebraria o mapa vizinho silenciosamente:

```python
elsewhere = any(_key(b.path) == _key(binding.path)
                for m in self.settings.maps for b in m.bindings if b is not binding)
own_copy = library.inside(binding.path, self._library_folder()) and not elsewhere
```

### 4.3 Modal do YouTube (`_youtube_dialog`)

Botão **«Baixar do YouTube»** na toolbar de sons. Modal no mesmo molde de `_sound_dialog` (Toplevel +
`transient` + `_center_on` + `grab_set` + `ESC_KEY`):

- `ttk.Entry` da URL (com `_quiet_while_typing`) + `ttk.Progressbar` + label de status + botões Baixar/Fechar.
- Sem ffmpeg: label em `#b00020` («o download precisa do ffmpeg…»), botão **Baixar desabilitado** e botão
  «Abrir site do ffmpeg» (`webbrowser.open`), exatamente como o app já trata o VB-Cable ausente.
- O download roda em `threading.Thread(daemon=True)`; o progresso volta por uma `queue.Queue` **local do
  modal**, drenada por `window.after(150, poll)`. Não encosta em `self.events`/`_pump`: quando o modal
  fecha, o polling morre com ele, e a fila global continua só com hook/bandeja.
- Terminou: `self._add_sound(path)` + `engine.prepare` + `_refresh_rows` + `_save` + flash — o mesmo
  caminho de `_add_sounds`, inclusive a dedupe de `_duplicate`.

### 4.4 Modal de corte (`_trim_dialog`)

Botão **«Cortar»** na toolbar e também no `_sound_dialog` (ao lado de «Definir tecla»). Exige um som
selecionado e o arquivo presente, como `_preview` já faz.

- Carrega o áudio **inteiro** com `load_sound(binding.path)` (sem start/end) só para desenhar.
- `tk.Canvas` (altura fixa ~120 px, largura acompanhando a janela via `<Configure>`), onde
  `audio.peaks(data, largura)` vira um `create_line` por coluna. Fora da seleção, retângulo cinza por cima.
- Duas alças arrastáveis (`<B1-Motion>` no Canvas: clique perto da alça esquerda/direita move ela). Labels
  mostram início/fim/duração em `m:ss.s`.
- Botões: **Ouvir trecho** (monta um `audio.Sound` temporário com a fatia e chama `engine.preview`),
  **Tudo** (zera o corte), **Salvar** e **Cancelar**.
- Salvar grava `binding.start/end`, recarrega `self.sounds[path] = load_sound(path, ..., start=, end=)`,
  `engine.prepare`, `_refresh_rows`, `_save`.
- A lista não ganha coluna nova para o corte: o flash ao salvar já informa («cortado: 0:03 → 1:12»).

## 5. Download — novo arquivo `src/nicopad/youtube.py`

Módulo fino no espírito de [cable.py](src/nicopad/cable.py) (lógica fora da tela):

```python
def has_ffmpeg() -> str | None          # shutil.which("ffmpeg") — o yt-dlp precisa dele para o mp3
def check_url(url: str) -> str | None   # devolve o motivo da recusa, ou None quando aceita
def download(url, folder, on_progress) -> Path
```
- `check_url` é o **limite de confiança**: só aceita `http://`/`https://`; recusa `file:`, caminhos locais
  e strings vazias — o yt-dlp aceitaria um caminho do disco e viraria "download" de arquivo local.
- `download` importa `yt_dlp` **dentro da função** (o app abre sem a dependência instalada e o modal mostra
  o erro), usa a API Python (nada de shell, nada de `subprocess` com string), com:
  `format="bestaudio/best"`, `postprocessors=[FFmpegExtractAudio → mp3]`, `paths={"home": folder}`,
  `outtmpl="%(title).80s.%(ext)s"`, `noplaylist=True`, `progress_hooks=[...]`, `quiet=True`.
  O caminho final sai do hook `finished`/`info["filepath"]`.
- MP3 é a escolha certa: o `soundfile` 0.14 desta máquina roda sobre **libsndfile 1.2.2, que lê MP3** —
  o arquivo baixado entra pelo `load_sound` de sempre, sem caso especial.
- Erro de rede/vídeo indisponível volta como exceção e o modal mostra a mensagem; nada é engolido.

## 6. Dependência e empacotamento

- [requirements.txt](requirements.txt): `yt-dlp>=2024.8.6`.
- [packaging/nicopad.spec](packaging/nicopad.spec): acrescentar `"yt_dlp"` ao loop de `collect_all`
  (os extractors são importados dinamicamente; sem isso o .exe baixa nada). Custo: ~10 MB no executável.
- Nada de ffmpeg no pacote: ele fica por conta do usuário, como o VB-Cable.

## 7. Documentação

[README.md](README.md): uma seção curta para mapKeys, uma para o download (incluindo «precisa do ffmpeg»)
e uma para o corte. Atualizar a lista de arquivos da seção «Estrutura» com `youtube.py`.

---

## Verificação

**Automática** — `task test` (`python -m nicopad --selftest`). Novos `check(...)` dentro de
`_extra_checks` em [selftest.py](src/nicopad/selftest.py), seguindo o padrão (função aninhada, `assert`
com mensagem, retorna a frase do relatório):

| Check | Prova |
|---|---|
| `mapas de teclas` | JSON no formato antigo (só `bindings`) vira um mapa «Padrão»; `save`+`load` com 2 mapas devolve os dois; `settings.bindings` é o do `active`; `active` fora do intervalo cai em 0. |
| `corte do som` | `load_sound(wav, start=0.05, end=0.15)` devolve ≈0.1 s de amostras; corte invertido/absurdo devolve o som inteiro em vez de vazio; `peaks(data, 100).shape == (100, 2)` e o pico bate com o do sinal. |
| `perfil (.zip)` | Estender o `profile_roundtrip` que já existe: dois mapas, um som compartilhado entre eles — o zip guarda **uma** cópia e os dois mapas voltam apontando para ela, com `start`/`end` preservados. |
| `download do youtube` | Só a parte pura, sem rede: `check_url` recusa `file:///c:/x.mp3`, caminho local e vazio, e aceita uma URL `https://` do YouTube. |

**Manual** — `task run`:
1. Criar «Jogos», adicionar um som, definir tecla; voltar para «Padrão» e confirmar que a tecla do outro
   mapa não toca mais; reabrir o app e conferir que o mapa ativo voltou.
2. Adicionar o mesmo arquivo em dois mapas, remover num deles, confirmar que o arquivo continua no disco
   e o outro mapa ainda toca.
3. Baixar uma música curta pelo modal, ver a barra andar e o som aparecer na lista já tocável.
4. Cortar esse som (arrastar as duas alças), «Ouvir trecho», salvar, tocar pela tecla e conferir o corte;
   reabrir o app e conferir que o corte persistiu.
5. Redimensionar a janela no mínimo (700×440) com o combo de mapas e o modal de corte abertos.

## Limitação conhecida (comentário `PONYTAIL:` no código)

Só o mapa ativo fica na memória — trocar de mapa recarrega. Ainda assim, uma música de 4 min ocupa
~80 MB de RAM em float32, e o download do YouTube torna isso comum. O corte reduz o consumo na origem.
Se listas grandes de músicas longas virarem rotina, o caminho é carregar sob demanda no primeiro toque;
não agora.
