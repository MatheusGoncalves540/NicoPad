# SoundPad Go — Plano de Implementação

**Escopo:** uma hotkey global → um som → sai no microfone virtual → você ouve também (opcional).
Nada além disso. MVP funcional em ~2 semanas de trabalho real, não 4.

---

## 1. Decisões (e o que mudou do rascunho original)

| Tema | Rascunho | Decisão | Porquê |
|---|---|---|---|
| Ring buffers lock-free | 2 ring buffers custom | **Removido** | O PCM inteiro já está na RAM. O callback lê direto do slice com um cursor. Ring buffer só faz sentido quando há um produtor gerando áudio em tempo real — aqui não há. |
| Sincronização trigger↔callback | mutex/atomics no callback | **Channel bufferizado** | `Play()` faz send não-bloqueante; o callback drena com `select/default` e é o **único dono** da lista de vozes. Zero lock na thread de áudio. |
| `faiface/beep` | v1.1.0 | **`gopxl/beep/v2`** | `faiface/beep` está arquivado. `gopxl` é o fork mantido, mesma API. |
| systray | getlantern/systray | **Fora do MVP** | Fase 4 opcional. Não é requisito. |
| `papipes` (auto-setup PulseAudio) | dependência | **Fora do MVP** | 3 linhas de `pactl` no README resolvem. Adicionar quando alguém reclamar. |
| Tela de wizard | tela dedicada | **Banner na tela principal** | "Dispositivo virtual não encontrado → [Baixar VB-Cable]". Uma linha, não uma tela. |
| Medidor de latência | exibido na UI | **Fora do MVP** | Mostrar `PeriodSizeInFrames / sampleRate` é honesto e grátis; medir latência real não é. |
| Versões pinadas no go.mod | fixas no plano | **`go get` resolve** | Não vou pinar versões que não verifiquei. Pinar depois do primeiro build verde. |
| 4 camadas de arquitetura | UI/App/Audio/Platform | **2 pacotes: `audio` e `ui`** | `platform` é uma função de 15 linhas. `hotkey` é um wrapper de 10. Não merecem pacote. |

**Stack final:**
- `golang.design/x/hotkey` — hotkeys globais
- `github.com/gen2brain/malgo` — I/O de áudio (MiniAudio)
- `github.com/gopxl/beep/v2` (+ `/mp3`, `/wav`, `/flac`, `/vorbis`) — decode + resample
- `github.com/AllenDang/giu` — GUI
- `encoding/json` + `os.UserConfigDir()` — config

---

## 2. Arquitetura

```
main.go
  └─ carrega config → cria audio.Engine → registra hotkey → abre UI

internal/audio/
  ├─ decode.go   arquivo → []float32 48kHz stereo interleaved (uma vez, no load)
  ├─ output.go   um malgo.Device + suas vozes ativas + canal de trigger
  └─ engine.go   dois outputs (virtual + monitor) + Play() + descoberta de devices

internal/ui/
  └─ app.go      giu: hotkey picker, file picker, volume, toggle, seletor de devices
```

Uma dependência entre pacotes: `ui → audio`. Só isso.

---

## 3. O núcleo de áudio

### 3.1 Formato canônico

Tudo é convertido no import para: **float32, 48000 Hz, 2 canais, interleaved**.
O callback de áudio nunca converte, nunca aloca, nunca faz syscall.

### 3.2 Decode (uma vez, no load)

```go
// decode.go
func Load(path string) ([]float32, error) {
    f, err := os.Open(path)
    if err != nil { return nil, err }
    defer f.Close()

    var s beep.StreamSeekCloser
    var format beep.Format
    switch strings.ToLower(filepath.Ext(path)) {
    case ".mp3":  s, format, err = mp3.Decode(f)
    case ".wav":  s, format, err = wav.Decode(f)
    case ".flac": s, format, err = flac.Decode(f)
    case ".ogg":  s, format, err = vorbis.Decode(f)
    default:      return nil, fmt.Errorf("formato não suportado: %s", filepath.Ext(path))
    }
    if err != nil { return nil, err }
    defer s.Close()

    var stream beep.Streamer = s
    if format.SampleRate != SampleRate {
        // resample uma única vez, aqui — nunca no callback
        stream = beep.Resample(4, format.SampleRate, SampleRate, s)
    }

    buf := make([][2]float64, 512)
    out := make([]float32, 0, SampleRate*Channels*3) // chute: 3s
    for {
        n, ok := stream.Stream(buf)
        for _, sm := range buf[:n] {
            out = append(out, float32(sm[0]), float32(sm[1]))
        }
        if !ok { break }
    }
    return out, nil
}
```

Guarda de sanidade: rejeitar arquivos acima de ~60 s (≈23 MB em RAM). Um soundpad não toca podcast.

### 3.3 Output — o callback

```go
// output.go
type voice struct {
    pcm []float32
    pos int
}

type Output struct {
    dev    *malgo.Device
    play   chan []float32 // buffered, cap 16 — trigger → callback
    voices []voice        // propriedade EXCLUSIVA do callback. Sem lock.
    gain   atomic.Uint32  // math.Float32bits
}

func (o *Output) Play(pcm []float32) {
    select {
    case o.play <- pcm:
    default: // fila cheia: descarta o trigger em vez de bloquear a UI
    }
}

// chamado pelo malgo na thread de áudio real-time.
// Regras: não alocar, não lockar, não chamar o runtime pesado.
func (o *Output) callback(out, _ []byte, frames uint32) {
    // 1. drena novos triggers (não-bloqueante)
    for drained := false; !drained; {
        select {
        case pcm := <-o.play:
            o.voices = append(o.voices, voice{pcm: pcm})
        default:
            drained = true
        }
    }

    // 2. mixa
    dst := unsafe.Slice((*float32)(unsafe.Pointer(&out[0])), int(frames)*Channels)
    for i := range dst { dst[i] = 0 }

    g := math.Float32frombits(o.gain.Load())
    live := o.voices[:0]
    for _, v := range o.voices {
        n := mixInto(dst, v.pcm[v.pos:], g)
        v.pos += n
        if v.pos < len(v.pcm) {
            live = append(live, v)
        }
    }
    o.voices = live // reusa o array — sem alocação em regime permanente
}

func mixInto(dst, src []float32, g float32) int {
    n := min(len(dst), len(src))
    for i := 0; i < n; i++ {
        dst[i] += src[i] * g
    }
    return n
}
```

**Notas de projeto:**
- `append` no drain aloca só até a capacidade estabilizar (poucos triggers simultâneos). O reuso de `o.voices[:0]` mantém em zero depois disso.
- Sem clipping por design. Se mixar 5 sons estourar, o `gain` do usuário resolve.
  `// ponytail: sem limiter — adicionar soft-clip (tanh) se distorcer com múltiplos sons`
- `unsafe.Slice` sobre o buffer do malgo é o idioma padrão da lib; não há cópia.

### 3.4 Engine — dois outputs

```go
type Engine struct {
    virtual   *Output
    monitor   *Output
    monitorOn atomic.Bool
    pcm       atomic.Pointer[[]float32] // som carregado; troca atômica no file picker
}

func (e *Engine) Play() {
    p := e.pcm.Load()
    if p == nil { return }
    e.virtual.Play(*p)
    if e.monitorOn.Load() && e.monitor != nil {
        e.monitor.Play(*p)
    }
}
```

O toggle do monitor é checado **fora** do callback. O callback não sabe que ele existe.

### 3.5 Config do device

```go
cfg := malgo.DefaultDeviceConfig(malgo.Playback)
cfg.Playback.Format    = malgo.FormatF32
cfg.Playback.Channels  = 2
cfg.SampleRate         = 48000
cfg.PeriodSizeInFrames = 240            // 5 ms
cfg.Periods            = 2
cfg.Playback.DeviceID  = deviceInfo.ID.Pointer()
```

240 frames é o alvo. Se houver xruns no Windows shared-mode, subir para 480 (10 ms) — ainda dentro do orçamento de <15 ms. **Campo de config, não constante**: hardware real precisa de ajuste.

---

## 4. Dispositivo virtual

```go
var virtualNames = map[string][]string{
    "windows": {"CABLE Input", "VoiceMeeter Input"},
    "darwin":  {"BlackHole"},
    "linux":   {"Null Output", "soundpad"},
}

func FindVirtual(ctx *malgo.AllocatedContext) (malgo.DeviceInfo, bool) {
    devs, err := ctx.Devices(malgo.Playback)
    if err != nil { return malgo.DeviceInfo{}, false }
    for _, d := range devs {
        for _, want := range virtualNames[runtime.GOOS] {
            if strings.Contains(d.Name(), want) {
                return d, true
            }
        }
    }
    return malgo.DeviceInfo{}, false
}
```

Um arquivo, sem build tags — `runtime.GOOS` num mapa faz o mesmo trabalho.
Se não achar: banner na UI com link. Se achar mais de um, o usuário escolhe no dropdown (que já existe de qualquer forma).

**Setup do usuário (vai pro README, não pro código):**
- Windows: instalar VB-Cable → no Discord, Input = `CABLE Output`
- macOS: `brew install blackhole-2ch`
- Linux: `pactl load-module module-null-sink sink_name=soundpad` + `module-remap-source`

---

## 5. UI — uma tela

```
┌──────────────────────────────────────────────┐
│  Hotkey:  [ Ctrl+Alt+1 ]  [Definir]          │
│  Som:     [ fart.mp3    ]  [Abrir...]        │
│                                              │
│           [  ▶  TOCAR  ]                     │
│                                              │
│  Volume   [████████░░] 80%                   │
│  ☑ Monitor local (você também ouve)          │
│                                              │
│  ▼ Dispositivos                              │
│    Saída virtual: [ CABLE Input        ▼]    │
│    Saída monitor: [ Fones (Realtek)    ▼]    │
│    Buffer:        [ 5 ms               ▼]    │
│                                              │
│  ● CABLE Input conectado · 5 ms              │
└──────────────────────────────────────────────┘
```

Duas telas viram uma: são 7 controles, cabem numa janela de 420×400. Um `giu.TreeNode("Dispositivos")` colapsável cobre a "tela de configurações" sem navegação e sem estado de roteamento.

**Captura de hotkey:** o botão "Definir" entra em modo de captura, lendo a próxima tecla + modificadores do ImGui. Enquanto ativo, a hotkey global fica **desregistrada** — senão o app dispara o som ao configurar.

**Config persistida** (`os.UserConfigDir()/soundpad/config.json`):

```json
{
  "sound_path": "C:/sounds/fart.mp3",
  "hotkey": {"mods": ["ctrl", "alt"], "key": "1"},
  "virtual_device": "CABLE Input (VB-Audio Virtual Cable)",
  "monitor_device": "Fones de ouvido (Realtek)",
  "monitor_enabled": true,
  "volume": 0.8,
  "buffer_ms": 5
}
```

Salva no `onChange` de cada controle. Sem botão "Salvar", sem estado sujo.

---

## 6. Estrutura de arquivos

```
soundpad-go/
├── go.mod
├── main.go              // ~80 linhas: wiring
├── README.md            // setup do VB-Cable + config do Discord
└── internal/
    ├── audio/
    │   ├── decode.go    // ~60 linhas
    │   ├── output.go    // ~90 linhas
    │   ├── engine.go    // ~110 linhas (inclui device discovery)
    │   └── audio_test.go
    ├── config/
    │   └── config.go    // ~50 linhas
    └── ui/
        └── app.go       // ~200 linhas
```

Alvo: **< 700 linhas de Go**. Se passar de 1000, algo entrou de contrabando.

---

## 7. Fases (marcos verificáveis)

### Fase 1 — CLI que toca som *(o risco todo está aqui)*
- [ ] `decode.go` — arquivo → `[]float32` 48 kHz stereo
- [ ] `output.go` — malgo device + callback com mixagem
- [ ] `main.go --list-devices` e `main.go --play fart.mp3 --device "CABLE Input"`
- [ ] **Verificação:** `--list-devices` mostra o CABLE Input; `--play` sai nele; o "Testar microfone" do Discord move a barra.
- [ ] **Teste:** `audio_test.go` — mixa 2 vozes num buffer conhecido, confere a soma amostra a amostra e o descarte da voz que terminou. `assert` puro, sem framework.

### Fase 2 — Hotkey + monitor
- [ ] Wrapper de `golang.design/x/hotkey`, goroutine consumindo `Keydown()`
- [ ] Segundo `Output` no device físico, toggle por flag
- [ ] **Verificação:** app em background, `Ctrl+Alt+1` dentro de um jogo em fullscreen → som sai nos dois devices, latência percebida indistinguível de instantânea.

### Fase 3 — GUI
- [ ] `ui/app.go` com os 7 controles + dropdowns de device
- [ ] Captura de hotkey (desregistra durante a captura)
- [ ] Persistência da config no change
- [ ] Banner de "dispositivo virtual não encontrado"
- [ ] **Verificação:** fechar e reabrir o app restaura tudo; trocar som e device sem reiniciar.

### Fase 4 — Opcional, sob demanda
Tray icon · minimize-to-tray · múltiplos slots · auto-setup PulseAudio · empacotamento (.exe assinado, .app, AppImage)

---

## 8. Riscos

| Risco | Mitigação |
|---|---|
| CGO no Windows (malgo + giu) | Documentar a toolchain (MSYS2/mingw-w64). CI `windows-latest` desde a **Fase 1** — descobrir cedo, não na semana 4. |
| Troca de device em runtime (fone desconectado) | `malgo` expõe `stopCallback`. MVP: mostrar o erro na UI com botão de reconectar. `// ponytail: sem re-enumeração automática` |
| Hotkey conflita com jogo/Discord | Config aceita qualquer combinação; sugerir F13–F24 no README. |
| macOS exige permissão de Accessibility | Detectar falha no `Register()` → banner com link para System Settings. |
| Sample rate do device ≠ 48 kHz | O data converter do MiniAudio resolve internamente. Se soar mal, expor o sample rate na config. |
| giu no Wayland | Documentar `GDK_BACKEND=x11`. Não codar fallback para um bug que talvez não exista. |

---

## 9. Fora de escopo

Biblioteca de sons com categorias · busca · playlists · editor de waveform · gravação · streaming pro OBS · driver de áudio próprio · múltiplas hotkeys.

A arquitetura já suporta múltiplos slots (`Engine.pcm` vira um `map[hotkey.Hotkey][]float32` e o callback já mixa N vozes) — mas isso é Fase 4, não MVP.

---

## 10. Primeiro commit

```bash
mkdir soundpad-go && cd soundpad-go
go mod init github.com/seuuser/soundpad-go
go get github.com/gen2brain/malgo
go get github.com/gopxl/beep/v2
go get golang.design/x/hotkey
# giu só na Fase 3 — não puxar CGO de GUI antes de precisar
```

Licença: MIT.
