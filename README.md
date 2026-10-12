# LAB/HP Python Logger

Script Python per impostare un alimentatore ET System LAB/HP via TCP/IP e registrare tensione e corrente misurate in un file CSV. 

## Requisiti

- Python 3.9 o successivo; non sono richiesti pacchetti esterni.
- Alimentatore LAB/HP con interfaccia Ethernet raggiungibile dal computer.
- Indirizzo IP dell'alimentatore e accesso alla porta TCP 10001 (porta predefinita indicata dal manuale).

Durante il controllo via TCP, tenere chiusa l'interfaccia web dell'alimentatore, come richiesto dal manuale.

## Avvio

```bash
python labhp_logger.py --host 192.168.1.50 --voltage 10 --current 1 --output misure.csv
```

Sostituire l'indirizzo IP e i valori con quelli adatti al proprio alimentatore e al carico. Il comando imposta 10 V e un limite di corrente di 1 A. Per usare una porta TCP diversa da quella predefinita, aggiungere `--port NUMERO`.

Se la protezione da sovratensione (OVP) già impostata non supera la tensione richiesta, specificarne una maggiore, ad esempio:

```bash
python labhp_logger.py --host 192.168.1.50 --voltage 10 --current 1 --ovp 12
```

Senza `--output`, il CSV viene creato nella directory corrente con un nome come `labhp_20261012_153000.csv`. Un file di output già esistente non viene sovrascritto.

## Funzionamento

Lo script verifica i limiti regolabili dello strumento, passa al controllo remoto, mette l'uscita in standby, seleziona la modalità UI e imposta tensione e corrente. Controlla quindi l'OVP e i setpoint letti dal dispositivo prima di abilitare l'uscita.

Durante l'acquisizione interroga in sequenza `MU` e `MI` con una cadenza **nominale di 1 campione al secondo**. Ogni riga del CSV viene scritta immediatamente. Se la rete o lo strumento impiegano più di un secondo per rispondere, l'intervallo effettivo può aumentare; la colonna temporale riporta il tempo effettivo.

| Colonna | Contenuto |
| --- | --- |
| `timestamp_utc` | Data e ora UTC del campione, con millisecondi |
| `elapsed_s` | Secondi trascorsi dall'inizio dell'acquisizione |
| `voltage_V` | Tensione misurata in volt |
| `current_A` | Corrente misurata in ampere |

Interrompere con **Ctrl+C**. Il programma tenta di inviare `SB,S` per mettere l'uscita in standby anche se si verifica un errore durante l'acquisizione. Se la connessione si interrompe, il comando di standby potrebbe non raggiungere l'alimentatore: controllare lo stato dell'uscita sul dispositivo.

## Opzioni

```text
--host IP_O_NOME     Indirizzo dell'alimentatore (obbligatorio)
--port NUMERO        Porta TCP (default: 10001)
--voltage VOLT       Tensione richiesta in V (obbligatoria)
--current AMPERE     Limite di corrente in A (obbligatorio)
--ovp VOLT           Imposta la protezione da sovratensione
--output PERCORSO    Nome del file CSV da creare
--timeout SECONDI    Timeout delle interrogazioni (default: 2)
```

Eseguire `python labhp_logger.py --help` per la guida completa.
