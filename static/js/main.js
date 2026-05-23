// main.js - Core functionalities
document.addEventListener('DOMContentLoaded', () => {
    console.log('ECE Platform Initialized');
    
    // Auto-dismiss alerts after 5 seconds
console.log('ECE Platform Initialized');

// Auto-dismiss alerts after 5 seconds
const alerts = document.querySelectorAll('.alert');
alerts.forEach(alert => {
    setTimeout(() => {
        alert.style.opacity = '0';
        alert.style.transition = 'opacity 0.5s ease';
        setTimeout(() => alert.remove(), 500);
    }, 5000);
});

// Init microphones
loadMicrophones();

// Escudo de Teclado Multimedia y Atajos (Fallback)
document.addEventListener('keydown', function(event) {
    // Buscar el botón activo dependiendo de la vista (Transcriptor o Consulta)
    const targetBtn = document.getElementById('recordBtn') || document.getElementById('micBtnResumen');
    
    if (!targetBtn) return;

    // Prevenir que interfiera si el usuario está escribiendo texto normal
    if (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA') {
        // Solo permitir si usa Ctrl+Espacio explícitamente
        if (event.ctrlKey && event.code === 'Space') {
            event.preventDefault();
            targetBtn.click();
        }
        return;
    }

    // Atajos globales si no está escribiendo
    if ((event.ctrlKey && event.code === 'Space') || 
        ['MediaPlayPause', 'MediaTrackNext'].includes(event.code)) {
        event.preventDefault();
        targetBtn.click();
    }
});

// Voice dictation functionality
let dictationMediaRecorder = null;
let dictationAudioChunks = [];
let isDictationRecording = false;

const audioCtx = new (window.AudioContext || window.webkitAudioContext)();

function playBeep(action) {
    if (audioCtx.state === 'suspended') audioCtx.resume();

    const oscillator = audioCtx.createOscillator();
    const gainNode = audioCtx.createGain();

    oscillator.connect(gainNode);
    gainNode.connect(audioCtx.destination);

    // Tono agudo (800Hz) para INICIAR, Tono grave (400Hz) para DETENER
    oscillator.frequency.value = action === 'start' ? 800 : 400; 
    oscillator.type = 'sine';

    // Volumen discreto y desvanecimiento rápido (0.15 segundos)
    gainNode.gain.setValueAtTime(0.1, audioCtx.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.15);

    oscillator.start();
    oscillator.stop(audioCtx.currentTime + 0.15);
}

async function loadMicrophones() {
    const micSelector = document.getElementById('micSelector');
    if (!micSelector) return; // Salir silenciosamente si no estamos en la vista con el selector

    try {
        // Solicitar permiso rápido para leer los nombres de los dispositivos
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const devices = await navigator.mediaDevices.enumerateDevices();
        const audioInputs = devices.filter(device => device.kind === 'audioinput');

        // Apagar el stream temporal de inmediato para no secuestrar el hardware
        stream.getTracks().forEach(track => track.stop());

        micSelector.innerHTML = '';

        audioInputs.forEach((device, index) => {
            const option = document.createElement('option');
            option.value = device.deviceId;
            option.text = device.label || `Micrófono ${index + 1}`;
            micSelector.appendChild(option);
        });
        console.log("Hardware de audio cargado");
    } catch(e) {
        console.error("Error al cargar micrófonos:", e);
        micSelector.innerHTML = '<option value="">Error al detectar audio</option>';
    }
}

// Garantizar que el HTML exista antes de buscar el menú
document.addEventListener('DOMContentLoaded', function() {
    const micSelector = document.getElementById('micSelector');
    if (micSelector) {
        console.log("Iniciando carga de micrófonos...");
        loadMicrophones();
    }
});

async function setupDictationRecorder() {
    const micSelector = document.getElementById('micSelector');
    const selectedDeviceId = (micSelector && micSelector.value) ? micSelector.value : null;

    // Si hay un selector y tiene valor, usarlo. Si no, usar el por defecto del sistema.
    const constraints = {
        audio: selectedDeviceId ? { deviceId: { exact: selectedDeviceId } } : true
    };

    try {
        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        dictationMediaRecorder = new MediaRecorder(stream);

        dictationMediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                dictationAudioChunks.push(event.data);
            }
        };
        return true;
    } catch(e) {
        console.error("Error al acceder al micrófono:", e);
        alert('Permiso de micrófono denegado o dispositivo no disponible.');
        return false;
    }
}

async function iniciarTranscripcion(targetInputId, btnElement) {
    if (!dictationMediaRecorder) {
        const ok = await setupDictationRecorder();
        if(!ok) return;
    }

    const targetInput = document.getElementById(targetInputId);
    if(!targetInput) {
        console.error("Target input not found:", targetInputId);
        return;
    }

    if (isDictationRecording) {
        // Stop
        playBeep('stop');
        dictationMediaRecorder.onstop = () => processDictationAudio(targetInput, btnElement);
        dictationMediaRecorder.stop();
        isDictationRecording = false;
        
        btnElement.style.color = 'var(--accent-med)';
        btnElement.style.borderColor = 'var(--accent-med)';
        if (btnElement.dataset.originalHtml) {
            btnElement.innerHTML = btnElement.dataset.originalHtml;
        }
    } else {
        // Start
        playBeep('start');
        dictationAudioChunks = [];
        dictationMediaRecorder.start();
        isDictationRecording = true;
        
        btnElement.dataset.originalHtml = btnElement.innerHTML;
        btnElement.style.color = '#dc3545';
        btnElement.style.borderColor = '#dc3545';
        btnElement.innerHTML = '<i class="fas fa-microphone fa-fade"></i> Grabando...';
    }
}

async function processDictationAudio(targetInput, btnElement) {
    const audioBlob = new Blob(dictationAudioChunks, { type: 'audio/webm' });
    const formData = new FormData();
    formData.append('audio', audioBlob, 'record.webm');
    
    btnElement.disabled = true;
    btnElement.style.opacity = '0.7';
    let originalPlaceholder = targetInput.placeholder;
    targetInput.placeholder = "Procesando audio en la nube...";

    try {
        const res = await fetch('/api/assemblyai/transcribe', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        
        if(res.ok && data.text) {
            targetInput.value += (targetInput.value ? " " : "") + data.text;
        } else {
            throw new Error(data.error || "Fallo desconocido al transcribir");
        }
    } catch(e) {
        console.error(e);
        alert("Error al transcribir: " + e.message);
    } finally {
        btnElement.disabled = false;
        btnElement.style.opacity = '1';
        btnElement.style.color = 'var(--accent-med)';
        btnElement.style.borderColor = 'var(--accent-med)';
        btnElement.innerHTML = btnElement.dataset.originalHtml;
        targetInput.placeholder = originalPlaceholder;
    }
}


