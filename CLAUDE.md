<!--
This file contains instructions for Claude Code agents working on this
repository. It is publicly visible for transparency about how AI tools
are used in development. Not required reading for users or contributors.
-->

# fatture-cli — Istruzioni specifiche

## Cosa fa
CLI per interagire con l'API ufficiale di Fatture in Cloud (fattureincloud.it).
Permette a un agente AI di leggere, creare e gestire fatture, clienti e prodotti
senza aprire il browser.

## API Reference
- Documentazione ufficiale: https://developers.fattureincloud.it/
- Base URL: `https://api.fattureincloud.it/v2`
- Auth: OAuth2 Bearer Token
- Rate limit: 1000 req/ora per token

## Autenticazione
Fatture in Cloud usa OAuth2. Il flusso è:
1. L'utente crea un'app su https://developers.fattureincloud.it/
2. Ottiene `client_id` e `client_secret`
3. `fatture auth login --client-id xxx --client-secret yyy` avvia il flusso OAuth
4. Il token viene salvato in `~/.config/mayai-cli/fatture/credentials.json`

## Comandi da implementare (priorità)

### Fatture
```bash
fatture list invoices                          # lista fatture
fatture list invoices --year 2025             # filtro per anno
fatture list invoices --status not_paid       # filtro per stato
fatture get invoice <id>                      # dettaglio fattura
fatture create invoice --client <id> --file invoice.json  # crea fattura
```

### Clienti
```bash
fatture list clients                          # lista clienti
fatture get client <id>                       # dettaglio cliente
fatture search clients "Rossi"                # ricerca per nome
```

### Prodotti
```bash
fatture list products                         # lista prodotti/servizi
fatture get product <id>                      # dettaglio prodotto
```

### Auth
```bash
fatture auth login --client-id xxx --client-secret yyy
fatture auth status
fatture auth logout
```

## Struttura file
```
fatture-cli/
├── CLAUDE.md              # questo file
├── README.md
├── pyproject.toml
├── Makefile
├── fatture_cli/
│   ├── __init__.py
│   ├── main.py            # entry point + registrazione comandi
│   ├── api/
│   │   ├── __init__.py
│   │   ├── client.py      # httpx client con auth
│   │   └── endpoints.py   # costanti URL
│   ├── auth/
│   │   ├── __init__.py
│   │   └── oauth.py       # flusso OAuth2
│   ├── models/
│   │   ├── __init__.py
│   │   ├── invoice.py     # dataclass Fattura
│   │   └── client.py      # dataclass Cliente
│   └── output/
│       ├── __init__.py
│       └── formatter.py   # pretty print + json
└── tests/
    └── test_api.py
```

## Note importanti
- L'API richiede sempre il `company_id` — va salvato in credentials.json dopo il login
- Le fatture hanno molti campi opzionali — l'output deve mostrare solo quelli valorizzati
- Per i test usa la sandbox: https://sandbox.fattureincloud.it (stesso token)
