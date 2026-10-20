# Manuale di Esecuzione per CLAUDE

## Recap dei Task Sintetico e Strutturato

### Ruolo
Il ruolo di CLAUDE è quello di supportare l'equipe di sviluppo, fornendo assistenza tecnica e risolvendo problemi emergenti.

### Protocollo d'Attacco
1. **Ricezione dei Comandi**: CLAUDE riceve i comandi tramite il bot Telegram.
2. **Esecuzione dei Task**: CLAUDE esegue i task richiesti utilizzando Aider e altri strumenti.
3. **Feedback e Correzioni**: CLAUDE fornisce feedback e correzioni basate sulle istruzioni in "orchestrator_summary.md".

### Uso Strumenti (Swarm)
- **Aider**: Strumento principale per l'esecuzione dei task.
- **Telegram Bot**: Interfaccia per la ricezione dei comandi e la comunicazione con l'equipe.
- **Orchestrator Summary**: Documento che contiene le istruzioni dettagliate per l'esecuzione dei task.

### Regole di Chiusura
- **Chiusura della Chat**: CLAUDE chiude la chat con Qwen quando l'utente preme il pulsante "Termina Chat / Torna al Menu".
- **Rigenerazione della Sintesi**: CLAUDE può rigenerare la sintesi direttiva utilizzando il comando "Rigenera Sintesi Direttive".
- **Torna al Menu**: CLAUDE torna al menu principale dei progetti quando l'utente preme il pulsante "Torna al Menu".

## Rotella di Caricamento Dinamica durante l'Esecuzione

Durante l'esecuzione dei task, CLAUDE visualizza una rotella di caricamento dinamica per indicare lo stato dell'operazione.

## Chat Persistente con Qwen

La chat con Qwen rimane attiva finché l'utente non preme il pulsante "Termina Chat / Torna al Menu". L'utente può continuare a scrivere comandi o chiudere la chat.
