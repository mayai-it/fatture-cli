# fatture-cli

CLI per l'API di Fatture in Cloud, pensato sia per umani che per agenti AI.
Output compatto in lettura terminale, NDJSON con `--json` per pipe verso
jq o LLM.

Parte di [MayAI](https://mayai.it).

## Installazione

```bash
pip install mayai-fatture-cli
```

Richiede Python 3.11+ e un'app sviluppatore gratuita su
https://developers.fattureincloud.it/.

## Quick start

```bash
# 1. Autenticati (apre il browser per il consenso OAuth2)
fatture auth login --client-id YOUR_ID --client-secret YOUR_SECRET

# 2. Verifica
fatture auth status

# 3. Elenca le 10 fatture pagate più recenti, come NDJSON
fatture --json list invoices --status paid --limit 10

# 4. Cerca un cliente per nome
fatture search clients "Rossi"
```

## Server MCP

`fatture-cli` include un server MCP nativo, che permette ad agenti AI
(Claude, Cursor, Continue, Zed) di accedere ai dati di Fatture in Cloud
direttamente. Vedere il [README in inglese](README.md#mcp-server) per la
configurazione.

## Documentazione completa

La documentazione completa è in inglese: vedere [README.md](README.md).
Per le domande frequenti e troubleshooting, vedere [docs/FAQ.md](docs/FAQ.md).

## Licenza

MIT — vedere [LICENSE](LICENSE).
