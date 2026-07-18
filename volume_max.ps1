
# Criar objeto COM de controle de teclas de mídia
$wscript = New-Object -ComObject Wscript.Shell

# Pressionar a tecla Volume_Up (caractere 175) 50 vezes
# Isso remove o Mute automaticamente no Windows e aumenta o volume ate 100%
for ($i = 0; $i -lt 50; $i++) {
    $wscript.SendKeys([char]175)
    Start-Sleep -Milliseconds 20
}

# Iniciar sintese de voz para alertar
try {
    Add-Type -AssemblyName System.Speech
    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
    
    # Loop de alerta falado 5 vezes
    for ($i = 0; $i -lt 5; $i++) {
        $synth.Speak("Atencao! Chave encontrada no Bitcoin Puzzle! Acorda!")
        Start-Sleep -Seconds 1
    }
} catch {
    # Fallback caso falte biblioteca de voz (tocar bipes sonoros do sistema)
    for ($i = 0; $i -lt 15; $i++) {
        [System.Console]::Beep(1500, 300)
        [System.Console]::Beep(2000, 300)
        Start-Sleep -Milliseconds 200
    }
}
