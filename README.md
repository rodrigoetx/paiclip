# 🎬 PaiClip (Reframe-AI)

**PaiClip** é uma ferramenta desktop local, gratuita e sem marcas d'água que converte vídeos horizontais (16:9) em verticais (9:16) prontos para **TikTok, Instagram Reels e YouTube Shorts** com apenas 1 clique.

Projetada com interface simples e moderna, ela oferece adaptação inteligente para **gameplays sem cortar o HUD nem as laterais** e rastreamento facial para **podcasts e vlogs**.

---

## ✨ Principais Recursos

- **🎮 Modo 1: OpusClip Fit & Blur (100% Sem Cortes - Padrão)**:
  - Mantém o vídeo 16:9 completo na tela sem cortar nenhum pixel lateral.
  - Placar, radar, mira, vida e times (como no Rainbow Six, CS, Valorant) continuam 100% nítidos e visíveis.
  - Preenche o topo e a base com o fundo dinâmico desfocado (*Gaussian Bokeh*) e sombra estética.
- **🕹️ Modo 2: Streamer Split (Webcam + Gameplay)**:
  - Mostra o close do jogador/webcam no topo e a gameplay inteira em 16:9 embaixo.
- **🎯 Modo 3: Smart Tracker 9:16 (Zoom Facial com IA)**:
  - Zoom 9:16 seguindo o locutor com inteligência artificial (MediaPipe BlazeFace), zona morta de 50px e suavização cinemática para podcasts/vlogs.
- **👥 Modo 4: Dividir Tela (2 Locutores)**:
  - Divisão 50/50 superior e inferior para entrevistas e bate-papos.
- **⚡ Aceleração por Placa de Vídeo (GPU)**:
  - Suporte de alta performance para placas **NVIDIA GeForce RTX (3060, 4060, 5060, etc.)** via NVENC, renderizando em mais de 150-200 FPS.
  - Compatível também com placas AMD e processadores (CPU).

---

## 📋 Pré-requisitos

Antes de iniciar, certifique-se de ter o **Python** instalado no computador:

1. Acesse o site oficial do Python: [python.org/downloads](https://www.python.org/downloads/)
2. Baixe o instalador do **Python 3.10 ou superior**.
3. **⚠️ IMPORTANTE NA INSTALAÇÃO:**
   Na primeira tela do instalador, **marque a caixa:**
   ☑️ **`Add python.exe to PATH`** (ou *"Adicionar Python às variáveis de ambiente"*).
4. Clique em **Install Now** e aguarde concluir.

---

## 🚀 Como Instalar e Executar (Passo a Passo)

### Método 1: No Windows com 2 Cliques (Mais Fácil)

1. Baixe este projeto (clicando no botão verde **Code** > **Download ZIP** no GitHub e extraia a pasta, ou via `git clone`).
2. Abra a pasta do projeto.
3. Dê um **duplo clique** no arquivo:
   ```text
   run.bat
   ```
4. Na primeira vez que abrir, o sistema irá instalar automaticamente todas as bibliotecas necessárias.
5. A tela do aplicativo abrirá em seguida!

---

### Método 2: Via Linha de Comando (Windows / Linux / Mac)

Caso prefira iniciar pelo terminal:

```bash
# 1. Clone o repositório
git clone https://github.com/rodrigoetx/paiclip.git
cd paiclip

# 2. Instale as dependências
pip install -r requirements.txt

# 3. Inicie o aplicativo
python app.py
```

---

## 📖 Como Usar a Ferramenta

1. **Carregar o Vídeo**:
   - Clique em **`📂 Selecionar Vídeo`** e escolha qualquer gravação horizontal (`.mp4`, `.mov`, `.mkv`, `.avi`, etc.).
2. **Escolher o Modo de Layout**:
   - Para **Gameplays** (jogos, tutoriais): use o **Modo 1 (OpusClip Fit & Blur)** para não cortar nenhuma informação da tela.
   - Para **Podcasts / Pessoas Falando**: use o **Modo 3 (Smart Tracker)** para focar no rosto.
3. **Pré-visualizar**:
   - Arraste a barra de linha do tempo (*Preview*) na esquerda para ver exatamente como o corte ficará antes de processar.
4. **Gerar o Vídeo**:
   - Clique no botão verde **`🚀 GERAR SHORT VERTICAL`**.
5. **Pronto**:
   - Ao concluir, clique em **`📁 Abrir Vídeo na Pasta`** ou **`▶️ Reproduzir Vídeo`** para assistir ao resultado!

---

## ❓ Perguntas Frequentes (FAQ)

- **O vídeo de jogo ficou cortado nas pontas?**
  - Verifique se selecionou o **Modo 1 (OpusClip Fit & Blur)**. Ele foi feito justamente para manter 100% da largura original visível.
- **Preciso baixar o FFmpeg separadamente?**
  - Não. A aplicação já localiza ou baixa os componentes necessários automaticamente.
- **Funciona sem internet?**
  - Sim! Todo o processamento de vídeo e IA de reconhecimento facial roda 100% offline no seu próprio computador.

---

## 📄 Licença
Distribuído sob a licença MIT. Livre para uso pessoal e comercial.
