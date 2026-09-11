# Graph Report - Nova pasta  (2026-09-11)

## Corpus Check
- 14 files · ~16,102 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 325 nodes · 593 edges · 12 communities
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS · INFERRED: 2 edges (avg confidence: 0.95)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `5370efd7`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- AGENTS.md
- NicoPadApp
- ui.py
- run
- config.py
- library.py
- profile.py
- nicoPad
- logo.py
- AudioEngine
- Tray
- KeyboardHook

## God Nodes (most connected - your core abstractions)
1. `NicoPadApp` - 57 edges
2. `AudioEngine` - 17 edges
3. `_key()` - 15 edges
4. `nicoPad` - 15 edges
5. `run()` - 14 edges
6. `KeyboardHook` - 12 edges
7. `Device` - 11 edges
8. `Mixer` - 11 edges
9. `Sound` - 10 edges
10. `load()` - 10 edges

## Surprising Connections (you probably didn't know these)
- `NicoPadApp` --uses--> `AudioEngine`  [INFERRED]
  src/nicopad/ui.py → src/nicopad/audio.py
- `NicoPadApp` --uses--> `KeyboardHook`  [INFERRED]
  src/nicopad/ui.py → src/nicopad/hotkeys.py
- `main()` --calls--> `load()`  [EXTRACTED]
  src/nicopad/__main__.py → src/nicopad/config.py
- `main()` --calls--> `NicoPadApp`  [EXTRACTED]
  src/nicopad/__main__.py → src/nicopad/ui.py
- `run()` --calls--> `Device`  [EXTRACTED]
  src/nicopad/selftest.py → src/nicopad/audio.py

## Import Cycles
- None detected.

## Communities (12 total, 0 thin omitted)

### Community 0 - "AGENTS.md"
Cohesion: 0.05
Nodes (40): 10. Concurrency and State, 11. Performance, 12. Validation and Testing, 13. Refactoring, 14. Desktop Applications, 15. Desktop Scrolling, 16. Desktop Data-Dense Interfaces, 17. Web Applications (+32 more)

### Community 1 - "NicoPadApp"
Cohesion: 0.07
Nodes (23): _key(), NicoPadApp, _percent(), Path, Tira a janela da frente sem encerrar nada: o programa segue pelos atalhos., Traz a janela de volta (pedido da bandeja)., Roda na thread da bandeja: quem mexe na janela é o Tk, no seu próprio laço., Caminho normalizado, igual ao que é gravado na configuração. (+15 more)

### Community 2 - "ui.py"
Cohesion: 0.08
Nodes (38): PhotoImage, Device, find_device(), guess_cable(), _input_channels(), _input_stream(), is_virtual_cable(), list_devices() (+30 more)

### Community 3 - "run"
Cohesion: 0.18
Nodes (18): bundled(), default_folder(), download(), _extract(), prepare(), Path, Pacote oficial do VB-Cable: entrega AS IS, sem instalar o driver por você. A…, Abre a pasta no Explorer já com o arquivo selecionado. (+10 more)

### Community 4 - "config.py"
Cohesion: 0.20
Nodes (16): Binding, config_path(), _device(), _keep_broken(), _level(), load(), Path, Configuração do nicoPad: um JSON simples ao lado do executável (portátil). (+8 more)

### Community 5 - "library.py"
Cohesion: 0.16
Nodes (19): _clean_stem(), copy_in(), default_folder(), _digest(), free_name(), inside(), Path, Pasta própria dos sons: o app deixa de depender dos arquivos originais. Cada… (+11 more)

### Community 6 - "profile.py"
Cohesion: 0.20
Nodes (13): nicoPad: toca sons do PC no seu microfone, um atalho global por som., export(), _extract_sounds(), _free_name(), load(), Path, Perfil: sons + configuração em um único .zip, para levar de uma máquina a…, Nome livre dentro do .zip: dois sons podem ter o mesmo nome em pastas… (+5 more)

### Community 7 - "nicoPad"
Cohesion: 0.12
Nodes (15): A barra de cima, Cada som tem a sua configuração, Começando, Estrutura, Fechar e a bandeja do sistema, Guardar os sons em uma pasta do programa, Lista de dispositivos enxuta, nicoPad (+7 more)

### Community 8 - "logo.py"
Cohesion: 0.26
Nodes (11): ico(), _in_bars(), main(), png(), Desenha a logo do nicoPad: packaging/nicopad.png e packaging/nicopad.ico.…, Ponto dentro de um retângulo de cantos arredondados (coordenadas de 0 a 1)., Linhas RGBA da logo, com superamostragem para as bordas ficarem lisas., PNG RGBA (8 bits por canal, sem compressão de linha extra). (+3 more)

### Community 9 - "AudioEngine"
Cohesion: 0.08
Nodes (17): ndarray, AudioEngine, MicBridge, Mixer, Ajusta a taxa por interpolação linear. PONYTAIL: interpolação linear é…, Um arquivo de som carregado na memória, pronto para tocar sem I/O., Amostras na taxa pedida (calculado uma vez por taxa)., Leva o que foi capturado do microfone para dentro do stream de saída. (+9 more)

### Community 10 - "Tray"
Cohesion: 0.12
Nodes (10): _image(), Path, A imagem do ícone; sem a logo, um quadrado escuro (melhor que ícone quebrado)., O ícone da bandeja, com «Abrir o nicoPad» e «Sair»., True depois que o ícone apareceu de verdade: antes disso não há para onde…, Põe o ícone na bandeja; devolve False (com o motivo em `error`) se não der., Tira o ícone da bandeja., Recado da bandeja, quando o sistema souber mostrar (o Linux não mostra). (+2 more)

### Community 11 - "KeyboardHook"
Cohesion: 0.18
Nodes (6): key_name(), _KeyboardEvent, KeyboardHook, Atalhos globais: hook de teclado de baixo nível do Windows, sem dependências. O…, Nome legível da tecla, no idioma do Windows (ex.: 'A', 'F1', 'Ctrl')., Chama handler(vk, extended, nome) a cada tecla nova, em qualquer lugar.

## Knowledge Gaps
- **48 isolated node(s):** `_KeyboardEvent`, `1. Before Writing Code`, `Question unnecessary requirements`, `Minimize the blast radius`, `4. Bug Fixes: Fix the Cause` (+43 more)
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `NicoPadApp` connect `NicoPadApp` to `KeyboardHook`, `AudioEngine`, `ui.py`, `run`?**
  _High betweenness centrality (0.231) - this node is a cross-community bridge._
- **Why does `AudioEngine` connect `AudioEngine` to `NicoPadApp`, `ui.py`, `run`?**
  _High betweenness centrality (0.071) - this node is a cross-community bridge._
- **Why does `Tray` connect `Tray` to `ui.py`?**
  _High betweenness centrality (0.061) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `NicoPadApp` (e.g. with `AudioEngine` and `KeyboardHook`) actually correct?**
  _`NicoPadApp` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `_KeyboardEvent`, `1. Before Writing Code`, `Question unnecessary requirements` to the rest of the system?**
  _48 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `AGENTS.md` be split into smaller, more focused modules?**
  _Cohesion score 0.04878048780487805 - nodes in this community are weakly interconnected._
- **Should `NicoPadApp` be split into smaller, more focused modules?**
  _Cohesion score 0.0684931506849315 - nodes in this community are weakly interconnected._