# 8-Mann-Regel Planer (Java REST API)

Dieses Projekt implementiert einen **agentischen Tenth-Man-Planer** als Java-REST-API:

- 7 Pro-Experten planen unabhängig und parallel.
- Die Pro-Argumente werden pro Runde zusammengeführt.
- Der 8. Experte (institutioneller Zweifler) greift den Konsens methodisch an.
- Mindestens 7 Runden werden durchgeführt.
- Ergebnis ist ein **Markdown-Protokoll inkl. Entscheidungsempfehlung**.
- Schritt 2 ist vorbereitet: Anbindung an **Websuche oder RAG** über ein externes REST-Endpoint.

## Umgebung anpassen (ohne Maven-Downloads)

Wenn Maven in der Umgebung blockiert ist (z. B. kein Zugriff auf Maven Central), kannst du das Projekt komplett mit JDK-Tools starten:

- Benötigt: **JDK 21**
- Build: `make build`
- Start: `make run`
- Smoke-Test: `make smoke-test`

Damit ist kein externer Dependency-Download nötig.

## Start (direkt)

```bash
javac --release 21 -d out src/main/java/com/example/tenthman/TenthManPlannerServer.java
java -cp out com.example.tenthman.TenthManPlannerServer
```

Standard-Port: `8080` (über `PORT` überschreibbar).

## API

### `POST /api/v1/tenth-man/plan`

Beispiel-Request:

```json
{
  "problem": "Soll ein KI-gestützter Kredit-Scoring-Prozess in 3 Ländern ausgerollt werden?",
  "rounds": 7,
  "externalMode": "NONE",
  "experts": [
    {"id": 1, "name": "Markt", "role": "Go-to-market", "endpoint": "http://localhost:9001/expert"},
    {"id": 2, "name": "Finanz", "role": "Business Case", "endpoint": "http://localhost:9002/expert"},
    {"id": 3, "name": "Tech", "role": "Architektur", "endpoint": "http://localhost:9003/expert"},
    {"id": 4, "name": "Legal", "role": "Regulatorik", "endpoint": "http://localhost:9004/expert"},
    {"id": 5, "name": "Risk", "role": "Risikomanagement", "endpoint": "http://localhost:9005/expert"},
    {"id": 6, "name": "Ops", "role": "Betrieb", "endpoint": "http://localhost:9006/expert"},
    {"id": 7, "name": "People", "role": "Change", "endpoint": "http://localhost:9007/expert"}
  ],
  "challenger": {"id": 8, "name": "Doubter", "role": "Institutioneller Zweifler", "endpoint": "http://localhost:9008/expert"}
}
```

Antwort enthält:

- strukturiertes Rundenprotokoll (`protocol`)
- finale Empfehlung (`recommendation`)
- fertiges Markdown-Protokoll (`markdownProtocol`)

## Erwartetes Agent-Endpoint-Format

Für Experten-Aufrufe sendet der Planer:

```json
{
  "prompt": "...",
  "role": "...",
  "name": "..."
}
```

Antwort des Experten kann z. B. eines dieser Felder enthalten:

- `response`
- `content`
- `answer`

Wenn keins davon vorhanden ist, wird der rohe Body als Antworttext übernommen.

## Schritt 2: Websuche / RAG

Setze `externalMode` auf:

- `WEB_SEARCH` oder
- `RAG`

und konfiguriere `webOrRagEndpoint`.

Der Planer ruft dann pro Runde dieses Endpoint auf mit:

```json
{
  "problem": "...",
  "round": 1,
  "mode": "WEB_SEARCH"
}
```

Die Rückgabe wird als Evidenz in die Prompts der Runde eingebaut.
