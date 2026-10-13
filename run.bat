@echo off
setlocal enabledelayedexpansion
title REFRAME-AI - Automação Local de Shorts & Reels
color 0B

echo ================================================================
echo               REFRAME-AI (Clone Local OpusClip)
echo     Conversao Inteligente 16:9 em 9:16 com Rastreamento Facial
echo ================================================================
echo.

:: 1. Verificar instalacao do Python
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    color 0C
    echo [ERRO] Python nao foi encontrado no sistema!
    echo Por favor, instale o Python 3.10 ou superior a partir de:
    echo https://www.python.org/downloads/
    echo.
    echo IMPORTANTE: Marque a opcao "Add python.exe to PATH" durante a instalacao.
    echo.
    pause
    exit /b 1
)

:: 2. Verificar dependencias do projeto
echo [1/2] Verificando dependencias do sistema...
python -c "import customtkinter, cv2, mediapipe, PIL, imageio_ffmpeg" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [AVISO] Dependencias ausentes ou primeira execucao detectada.
    echo Instalando pacotes necessarios de requirements.txt...
    echo Aguarde alguns instantes...
    echo.
    python -m pip install -r requirements.txt
    if !ERRORLEVEL! neq 0 (
        color 0C
        echo.
        echo [ERRO] Falha ao instalar as dependencias via pip.
        echo Verifique sua conexao com a internet e tente novamente.
        echo.
        pause
        exit /b 1
    )
    echo [OK] Dependencias instaladas com sucesso!
) else (
    echo [OK] Todas as dependencias estao prontas!
)

:: 3. Iniciar aplicacao
echo.
echo [2/2] Iniciando REFRAME-AI Desktop...
echo.
python app.py

if %ERRORLEVEL% neq 0 (
    echo.
    echo [AVISO] O aplicativo encerrou com codigo de erro %ERRORLEVEL%.
    pause
)
