# Conversor de Vídeo 16:9 para 9:16 (Shorts, Reels, TikTok)

Aplicação desktop para conversão de vídeos horizontais (16:9) em verticais (9:16), com suporte a aceleração por hardware (GPU) e diferentes formatos de enquadramento.

---

## Modos de Enquadramento

1. **Fit com Fundo Desfocado (Padrão / Gameplays)**:
   - Mantém o vídeo 16:9 completo na largura da tela sem cortar nada das laterais (placar, mapa, HUD e mira continuam 100% visíveis).
   - Preenche as áreas superior e inferior com o próprio vídeo ampliado e desfocado.
2. **Streamer Split (Webcam + Jogo)**:
   - Posiciona o corte da webcam na parte superior e a tela do jogo completa na parte inferior.
3. **Rastreamento Facial (Smart Tracker)**:
   - Aplica zoom 9:16 e acompanha o locutor automaticamente via detecção facial. Indicado para vlogs e podcasts (corta as laterais).
4. **Dividir Tela (2 Pessoas)**:
   - Divide a tela vertical em duas partes iguais (50/50), enquadrando dois locutores diferentes.

---

## Pré-requisitos

1. Ter o **Python 3.10 ou superior** instalado: [python.org/downloads](https://www.python.org/downloads/)
2. Na instalação do Python, marque a opção obrigatória:
   **"Add python.exe to PATH"** (ou "Adicionar Python às variáveis de ambiente").

---

## Como Executar

### Windows (Execução Rápida)
Dê um duplo clique no arquivo:
```text
run.bat
```
O script verifica o ambiente, instala as dependências necessárias automaticamente na primeira execução e abre a aplicação.

### Linha de Comando (Windows / Linux / Mac)
```bash
pip install -r requirements.txt
python app.py
```

---

## Como Usar

1. Clique em **Selecionar Vídeo** e escolha o arquivo horizontal.
2. Escolha o modo de layout desejado (para jogos ou vídeos com informações nas laterais, mantenha o modo padrão **Fit**).
3. Use a barra de pré-visualização para conferir o enquadramento.
4. Clique em **Gerar Short Vertical**.
5. Ao concluir, use os botões para abrir a pasta ou reproduzir o arquivo final.

---

## Aceleração por Hardware

O programa detecta automaticamente encoders de GPU disponíveis:
- **NVIDIA**: `h264_nvenc` (placas GTX / RTX)
- **AMD**: `h264_amf`
- **Intel**: `h264_qsv`
- **CPU**: `libx264` (fallback por software)
