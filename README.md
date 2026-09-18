# Tebra SOAP ChatGPT connector

This plugin exposes Tebra's SOAP API as MCP tools for ChatGPT/Codex.

The hosted MCP endpoint is `/mcp` when deployed with `MCP_TRANSPORT=streamable-http`.

## Configure once

Run:

```bash
python3 /root/plugins/tebra-soap/scripts/configure_credentials.py
```

Enter the Tebra API username, API password, and customer key when prompted. The password and customer key are hidden and stored in a local file with owner-only permissions.

## Current tools

- Check connection configuration
- List and describe SOAP operations from the live WSDL
- View upcoming appointments
- Find patients
- List providers and practices
- Call any allow-listed read-only Tebra operation

Write operations will be added after the live WSDL and read connection have been verified.
