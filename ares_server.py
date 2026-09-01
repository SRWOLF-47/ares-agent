<script>
    const orbContainer = document.getElementById('orbContainer');
    const statusEl = document.getElementById('status');
    const player = document.getElementById('player');

    const WAKE_PHRASES = [
        "hey ares", "oye ares", "ok ares", "okay ares",
        "hola ares", "ares", "ei ares", "ey ares"
    ];

    let recognition = null;
    let mode = "wake";          // wake | command
    let isProcessing = false;
    let restartTimeout = null;
    let commandTimeout = null;

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
        statusEl.textContent = "Tu navegador no soporta reconocimiento de voz. Usa Chrome o Edge.";
    } else {
        initRecognition();
        startWakeListening();
    }

    function initRecognition() {
        recognition = new SpeechRecognition();
        recognition.lang = "es-MX";
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.maxAlternatives = 1;

        recognition.onresult = (event) => {
            let transcript = "";
            for (let i = event.resultIndex; i < event.results.length; i++) {
                transcript += event.results[i][0].transcript;
            }
            transcript = transcript.toLowerCase().trim();
            console.log("Escuchado:", transcript, "| Modo:", mode);

            if (mode === "wake") {
                const detected = WAKE_PHRASES.some(p => transcript.includes(p));
                if (detected) {
                    onWakeWord();
                }
            } 
            else if (mode === "command") {
                // Mostramos lo que va entendiendo
                statusEl.textContent = transcript || "Te escucho...";

                // Si es resultado final, procesamos
                if (event.results[event.results.length - 1].isFinal) {
                    const finalText = event.results[event.results.length - 1][0].transcript.trim();
                    if (finalText.length > 2) {
                        clearTimeout(commandTimeout);
                        recognition.stop();
                        processCommand(finalText);
                    }
                }
            }
        };

        recognition.onerror = (e) => {
            console.error("Error reconocimiento:", e.error);
            if (e.error === "not-allowed") {
                statusEl.textContent = "Permiso de micrófono denegado. Actívalo en el navegador.";
                return;
            }
            if (e.error === "no-speech") {
                statusEl.textContent = "No detecté voz. Di 'Hey Ares' de nuevo.";
            }
            scheduleRestart();
        };

        recognition.onend = () => {
            console.log("Reconocimiento terminó. Modo:", mode);
            if (!isProcessing && mode === "wake") {
                scheduleRestart();
            }
        };
    }

    function scheduleRestart() {
        clearTimeout(restartTimeout);
        restartTimeout = setTimeout(() => {
            if (!isProcessing && mode === "wake") {
                startWakeListening();
            }
        }, 400);
    }

    function startWakeListening() {
        mode = "wake";
        setState("idle");
        statusEl.textContent = 'Di "Hey Ares" o "Oye Ares"';
        try {
            recognition.continuous = true;
            recognition.interimResults = true;
            recognition.start();
        } catch (e) {
            console.log("Ya estaba iniciado");
        }
    }

    function onWakeWord() {
        mode = "command";
        recognition.stop();
        setState("wake");
        statusEl.textContent = "Sí, Señor...";

        setTimeout(() => {
            setState("listening");
            statusEl.textContent = "Te escucho... habla ahora";

            // Configuramos para capturar el comando
            recognition.continuous = false;
            recognition.interimResults = true;

            try {
                recognition.start();
            } catch (e) {
                console.error(e);
            }

            // Seguridad: si en 9 segundos no dice nada, volvemos
            clearTimeout(commandTimeout);
            commandTimeout = setTimeout(() => {
                if (mode === "command" && !isProcessing) {
                    statusEl.textContent = "No escuché el comando. Di 'Hey Ares' de nuevo.";
                    mode = "wake";
                    setState("idle");
                    startWakeListening();
                }
            }, 9000);

        }, 700);
    }

    async function processCommand(texto) {
        isProcessing = true;
        clearTimeout(commandTimeout);
        setState("thinking");
        statusEl.textContent = `"${texto}"`;

        try {
            const formData = new FormData();
            formData.append("prompt", texto);

            statusEl.textContent = "Procesando con ARES...";

            const response = await fetch("/preguntar", {
                method: "POST",
                body: formData
            });

            if (!response.ok) {
                throw new Error("Error del servidor: " + response.status);
            }

            const contentType = response.headers.get("content-type") || "";

            if (contentType.includes("audio")) {
                const blob = await response.blob();
                const url = URL.createObjectURL(blob);
                player.src = url;

                setState("speaking");
                statusEl.textContent = "ARES respondiendo...";

                player.onended = () => {
                    URL.revokeObjectURL(url);
                    isProcessing = false;
                    startWakeListening();
                };

                player.onerror = () => {
                    statusEl.textContent = "Error al reproducir audio";
                    isProcessing = false;
                    startWakeListening();
                };

                await player.play();
            } else {
                // Fallback texto
                const data = await response.json();
                statusEl.textContent = data.texto || data.error || "Sin respuesta";
                isProcessing = false;
                setTimeout(() => startWakeListening(), 4000);
            }
        } catch (err) {
            console.error("Error en processCommand:", err);
            statusEl.textContent = "Error de conexión con el servidor";
            isProcessing = false;
            setTimeout(() => startWakeListening(), 3000);
        }
    }

    function setState(state) {
        orbContainer.className = "orb-container " + state;
    }

    // Click de emergencia
    orbContainer.addEventListener("click", () => {
        if (isProcessing) return;
        if (mode === "wake") {
            onWakeWord();
        }
    });
</script>
