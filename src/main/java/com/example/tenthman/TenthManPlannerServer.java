package com.example.tenthman;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executors;
import java.util.stream.Collectors;

/**
 * Minimal Java REST API for an "8th Man Rule" planner.
 */
public class TenthManPlannerServer {

    public static void main(String[] args) throws IOException {
        int port = Integer.parseInt(System.getenv().getOrDefault("PORT", "8080"));
        HttpServer server = HttpServer.create(new InetSocketAddress(port), 0);
        server.createContext("/api/v1/tenth-man/plan", TenthManPlannerServer::handlePlan);
        server.setExecutor(Executors.newFixedThreadPool(16));
        server.start();
        System.out.println("Tenth Man Planner API running on http://localhost:" + port);
    }

    private static void handlePlan(HttpExchange exchange) throws IOException {
        if (!"POST".equalsIgnoreCase(exchange.getRequestMethod())) {
            sendJson(exchange, 405, Map.of("error", "Only POST allowed"));
            return;
        }

        try (InputStream body = exchange.getRequestBody()) {
            String input = new String(body.readAllBytes(), StandardCharsets.UTF_8);
            PlanRequest request = PlanRequest.fromJson(input);
            validateRequest(request);

            PlannerEngine engine = new PlannerEngine();
            PlanResult result = engine.run(request);
            sendJson(exchange, 200, result.toMap());
        } catch (IllegalArgumentException e) {
            sendJson(exchange, 400, Map.of("error", e.getMessage()));
        } catch (Exception e) {
            sendJson(exchange, 500, Map.of("error", "Planner execution failed", "details", Objects.toString(e.getMessage())));
        }
    }

    private static void validateRequest(PlanRequest request) {
        if (request == null || blank(request.problem)) {
            throw new IllegalArgumentException("problem is required");
        }
        if (request.experts == null || request.experts.size() != 7) {
            throw new IllegalArgumentException("exactly 7 pro experts are required");
        }
        if (request.challenger == null) {
            throw new IllegalArgumentException("challenger (expert 8) is required");
        }
        if (request.rounds < 7) {
            throw new IllegalArgumentException("minimum rounds is 7");
        }
        request.experts.forEach(expert -> {
            if (blank(expert.endpoint)) {
                throw new IllegalArgumentException("every pro expert needs endpoint");
            }
        });
        if (blank(request.challenger.endpoint)) {
            throw new IllegalArgumentException("challenger needs endpoint");
        }
    }

    private static boolean blank(String value) {
        return value == null || value.isBlank();
    }

    private static void sendJson(HttpExchange exchange, int statusCode, Map<String, Object> payload) throws IOException {
        byte[] bytes = MiniJson.stringify(payload).getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().add("Content-Type", "application/json; charset=utf-8");
        exchange.sendResponseHeaders(statusCode, bytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(bytes);
        }
    }

    enum ExternalMode {
        NONE,
        WEB_SEARCH,
        RAG;

        static ExternalMode fromString(String raw) {
            if (raw == null || raw.isBlank()) return NONE;
            try {
                return ExternalMode.valueOf(raw.trim().toUpperCase());
            } catch (Exception ignored) {
                return NONE;
            }
        }
    }

    public static class PlannerEngine {
        private final HttpClient httpClient = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(20)).build();

        PlanResult run(PlanRequest request) {
            Instant start = Instant.now();
            EvidenceProvider evidenceProvider = EvidenceProvider.forMode(request.externalMode, request.webOrRagEndpoint, httpClient);
            List<RoundRecord> rounds = new ArrayList<>();
            String cumulativeCounterNarrative = "";

            for (int roundNo = 1; roundNo <= request.rounds; roundNo++) {
                int currentRound = roundNo;
                String evidence = evidenceProvider.lookup(request.problem, currentRound);

                List<CompletableFuture<ExpertResponse>> futures = request.experts.stream()
                        .map(expert -> CompletableFuture.supplyAsync(() -> callAgent(expert, proPrompt(request.problem, evidence, currentRound))))
                        .toList();

                List<ExpertResponse> proResponses = futures.stream().map(CompletableFuture::join)
                        .sorted(Comparator.comparingInt(r -> r.expertId)).toList();

                String proConsensus = synthesizeConsensus(proResponses);
                ExpertResponse challengerResponse = callAgent(request.challenger,
                        challengerPrompt(request.problem, evidence, proConsensus, cumulativeCounterNarrative, currentRound));

                cumulativeCounterNarrative = cumulativeCounterNarrative + "\n\n[Round " + currentRound + "] " + challengerResponse.content;
                rounds.add(new RoundRecord(currentRound, evidence, proResponses, proConsensus, challengerResponse));
            }

            String finalRecommendation = finalChallengeSummary(request.problem, rounds);
            String markdown = MarkdownBuilder.toMarkdown(request.problem, rounds, finalRecommendation);
            long runtimeMs = Duration.between(start, Instant.now()).toMillis();

            return new PlanResult(request.problem, request.rounds, request.externalMode, runtimeMs, rounds, finalRecommendation, markdown);
        }

        private ExpertResponse callAgent(ExpertConfig expert, String prompt) {
            try {
                Map<String, Object> payload = new LinkedHashMap<>();
                payload.put("prompt", prompt);
                payload.put("role", expert.role == null ? "" : expert.role);
                payload.put("name", expert.name == null ? "" : expert.name);

                HttpRequest request = HttpRequest.newBuilder()
                        .uri(URI.create(expert.endpoint))
                        .timeout(Duration.ofSeconds(90))
                        .header("Content-Type", "application/json")
                        .POST(HttpRequest.BodyPublishers.ofString(MiniJson.stringify(payload)))
                        .build();

                HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
                if (response.statusCode() >= 300) {
                    return ExpertResponse.error(expert.id, safeName(expert), "HTTP " + response.statusCode() + " from " + expert.endpoint);
                }

                String content = extractContent(response.body());
                return new ExpertResponse(expert.id, safeName(expert), expert.role, content, false);
            } catch (Exception ex) {
                return ExpertResponse.error(expert.id, safeName(expert), ex.getMessage());
            }
        }

        private String extractContent(String rawBody) {
            try {
                Object parsed = MiniJson.parse(rawBody);
                if (parsed instanceof Map<?, ?> map) {
                    Object text = map.get("response");
                    if (text == null) text = map.get("content");
                    if (text == null) text = map.get("answer");
                    return text == null ? rawBody : Objects.toString(text);
                }
                return rawBody;
            } catch (Exception ignored) {
                return rawBody;
            }
        }

        private static String safeName(ExpertConfig expert) {
            return blank(expert.name) ? "Expert-" + expert.id : expert.name;
        }

        private static String proPrompt(String problem, String evidence, int round) {
            return "Du bist ein Pro-Experte in Runde " + round + ".\n"
                    + "Problem: " + problem + "\n"
                    + "Evidenz: " + evidence + "\n"
                    + "Liefere strukturierte Argumente PRO Umsetzung (Risiken nennen, aber Fokus auf Machbarkeit). "
                    + "Format: Annahmen, Kernargumente, Risiken, Gegenmaßnahmen, nächste Schritte.";
        }

        private static String challengerPrompt(String problem, String evidence, String proConsensus, String priorCounterNarrative, int round) {
            return "Du bist der institutionelle Zweifler (8. Experte) in Runde " + round + ".\n"
                    + "Problem: " + problem + "\n"
                    + "Evidenz: " + evidence + "\n"
                    + "Konsens der 7 Pro-Experten:\n" + proConsensus + "\n"
                    + "Bisherige Gegenargumente:\n" + priorCounterNarrative + "\n"
                    + "Aufgabe: Brich den Konsens methodisch. Prüfe falsche Annahmen, Extremrisiken, zweite Ordnungseffekte,"
                    + " unbeachtete Stakeholder, Messfehler, Compliance/Sicherheit. "
                    + "Format: Hypothese, Angriffspunkte, was die 7 übersehen, Testplan zur Falsifikation.";
        }

        private static String synthesizeConsensus(List<ExpertResponse> responses) {
            String merged = responses.stream().map(r -> "- " + r.expertName + ": " + r.content).collect(Collectors.joining("\n"));
            return "Synthetischer PRO-Konsens auf Basis der 7 Beiträge:\n" + merged;
        }

        private static String finalChallengeSummary(String problem, List<RoundRecord> rounds) {
            RoundRecord lastRound = rounds.get(rounds.size() - 1);
            return "Entscheidungsempfehlung zum Problem: " + problem + "\n"
                    + "Empfehlung: Gestaffelte Pilotierung mit harten Abbruchkriterien.\n"
                    + "Begründung: Der 8. Experte identifizierte in Runde " + lastRound.round
                    + " die kritischsten Unsicherheiten; nur unter validierten Gegenbeweisen skalieren.";
        }
    }

    interface EvidenceProvider {
        String lookup(String problem, int round);

        static EvidenceProvider forMode(ExternalMode mode, String endpoint, HttpClient client) {
            ExternalMode resolved = mode == null ? ExternalMode.NONE : mode;
            return switch (resolved) {
                case NONE -> (problem, round) -> "Keine externe Evidenz (Mode NONE).";
                case WEB_SEARCH -> new RemoteEvidenceProvider("WEB_SEARCH", endpoint, client);
                case RAG -> new RemoteEvidenceProvider("RAG", endpoint, client);
            };
        }
    }

    static class RemoteEvidenceProvider implements EvidenceProvider {
        private final String mode;
        private final String endpoint;
        private final HttpClient client;

        RemoteEvidenceProvider(String mode, String endpoint, HttpClient client) {
            this.mode = mode;
            this.endpoint = endpoint;
            this.client = client;
        }

        @Override
        public String lookup(String problem, int round) {
            if (blank(endpoint)) {
                return mode + " nicht konfiguriert: endpoint fehlt.";
            }
            try {
                Map<String, Object> payload = Map.of("problem", problem, "round", round, "mode", mode);
                HttpRequest request = HttpRequest.newBuilder()
                        .uri(URI.create(endpoint))
                        .timeout(Duration.ofSeconds(40))
                        .header("Content-Type", "application/json")
                        .POST(HttpRequest.BodyPublishers.ofString(MiniJson.stringify(payload)))
                        .build();
                HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
                if (response.statusCode() >= 300) {
                    return mode + " Anfrage fehlgeschlagen: HTTP " + response.statusCode();
                }
                return "Externe Evidenz (" + mode + "): " + response.body();
            } catch (Exception e) {
                return mode + " Anfragefehler: " + e.getMessage();
            }
        }
    }

    static class MarkdownBuilder {
        static String toMarkdown(String problem, List<RoundRecord> rounds, String recommendation) {
            StringBuilder sb = new StringBuilder();
            sb.append("# Protokoll: 8-Mann-Regel Planer\n\n");
            sb.append("## Problem\n").append(problem).append("\n\n");
            sb.append("## Rundenprotokoll\n\n");

            for (RoundRecord round : rounds) {
                sb.append("### Runde ").append(round.round).append("\n\n");
                sb.append("**Evidenzbasis:** ").append(round.evidence).append("\n\n");
                sb.append("#### Beiträge der 7 Pro-Experten\n");
                round.proResponses.forEach(resp -> sb.append("- **").append(resp.expertName).append("**: ").append(resp.content).append("\n"));
                sb.append("\n#### Pro-Konsens\n").append(round.proConsensus).append("\n\n");
                sb.append("#### Angriff durch den 8. Experten\n").append(round.challengerResponse.content).append("\n\n---\n\n");
            }

            sb.append("## Entscheidungsempfehlung\n").append(recommendation).append("\n");
            return sb.toString();
        }
    }

    static class PlanRequest {
        String problem;
        int rounds = 7;
        ExternalMode externalMode = ExternalMode.NONE;
        String webOrRagEndpoint;
        List<ExpertConfig> experts;
        ExpertConfig challenger;

        static PlanRequest fromJson(String json) {
            Object parsed = MiniJson.parse(json);
            if (!(parsed instanceof Map<?, ?> map)) {
                throw new IllegalArgumentException("request must be a JSON object");
            }
            PlanRequest req = new PlanRequest();
            req.problem = asString(map.get("problem"));
            req.rounds = asInt(map.get("rounds"), 7);
            req.externalMode = ExternalMode.fromString(asString(map.get("externalMode")));
            req.webOrRagEndpoint = asString(map.get("webOrRagEndpoint"));
            req.experts = parseExperts(map.get("experts"));
            req.challenger = parseExpert(map.get("challenger"));
            return req;
        }

        private static List<ExpertConfig> parseExperts(Object raw) {
            if (!(raw instanceof List<?> list)) return null;
            List<ExpertConfig> experts = new ArrayList<>();
            for (Object item : list) {
                experts.add(parseExpert(item));
            }
            return experts;
        }

        private static ExpertConfig parseExpert(Object raw) {
            if (!(raw instanceof Map<?, ?> map)) return null;
            ExpertConfig expert = new ExpertConfig();
            expert.id = asInt(map.get("id"), 0);
            expert.name = asString(map.get("name"));
            expert.role = asString(map.get("role"));
            expert.endpoint = asString(map.get("endpoint"));
            return expert;
        }

        private static int asInt(Object value, int fallback) {
            if (value instanceof Number n) return n.intValue();
            if (value instanceof String s) {
                try {
                    return Integer.parseInt(s.trim());
                } catch (Exception ignored) {
                    return fallback;
                }
            }
            return fallback;
        }

        private static String asString(Object value) {
            return value == null ? null : Objects.toString(value);
        }
    }

    static class ExpertConfig {
        int id;
        String name;
        String role;
        String endpoint;
    }

    static class ExpertResponse {
        final int expertId;
        final String expertName;
        final String role;
        final String content;
        final boolean error;

        ExpertResponse(int expertId, String expertName, String role, String content, boolean error) {
            this.expertId = expertId;
            this.expertName = expertName;
            this.role = role;
            this.content = content;
            this.error = error;
        }

        static ExpertResponse error(int expertId, String expertName, String msg) {
            return new ExpertResponse(expertId, expertName, "", "FEHLER: " + Objects.toString(msg), true);
        }

        Map<String, Object> toMap() {
            return Map.of(
                    "expertId", expertId,
                    "expertName", expertName,
                    "role", role == null ? "" : role,
                    "content", content,
                    "error", error
            );
        }
    }

    static class RoundRecord {
        final int round;
        final String evidence;
        final List<ExpertResponse> proResponses;
        final String proConsensus;
        final ExpertResponse challengerResponse;

        RoundRecord(int round, String evidence, List<ExpertResponse> proResponses, String proConsensus, ExpertResponse challengerResponse) {
            this.round = round;
            this.evidence = evidence;
            this.proResponses = proResponses;
            this.proConsensus = proConsensus;
            this.challengerResponse = challengerResponse;
        }

        Map<String, Object> toMap() {
            List<Map<String, Object>> pro = proResponses.stream().map(ExpertResponse::toMap).toList();
            return Map.of(
                    "round", round,
                    "evidence", evidence,
                    "proResponses", pro,
                    "proConsensus", proConsensus,
                    "challengerResponse", challengerResponse.toMap()
            );
        }
    }

    static class PlanResult {
        final String problem;
        final int rounds;
        final ExternalMode externalMode;
        final long runtimeMs;
        final List<RoundRecord> protocol;
        final String recommendation;
        final String markdownProtocol;

        PlanResult(String problem, int rounds, ExternalMode externalMode, long runtimeMs, List<RoundRecord> protocol,
                   String recommendation, String markdownProtocol) {
            this.problem = problem;
            this.rounds = rounds;
            this.externalMode = externalMode;
            this.runtimeMs = runtimeMs;
            this.protocol = protocol;
            this.recommendation = recommendation;
            this.markdownProtocol = markdownProtocol;
        }

        Map<String, Object> toMap() {
            List<Map<String, Object>> roundsPayload = protocol.stream().map(RoundRecord::toMap).toList();
            return Map.of(
                    "problem", problem,
                    "rounds", rounds,
                    "externalMode", externalMode.name(),
                    "runtimeMs", runtimeMs,
                    "protocol", roundsPayload,
                    "recommendation", recommendation,
                    "markdownProtocol", markdownProtocol
            );
        }
    }

    /**
     * Tiny JSON parser/serializer for this service to avoid external runtime dependencies.
     */
    static class MiniJson {
        static Object parse(String json) {
            return new Parser(json).parse();
        }

        static String stringify(Object value) {
            StringBuilder sb = new StringBuilder();
            write(value, sb);
            return sb.toString();
        }

        @SuppressWarnings("unchecked")
        private static void write(Object value, StringBuilder sb) {
            if (value == null) {
                sb.append("null");
            } else if (value instanceof String s) {
                sb.append('"').append(escape(s)).append('"');
            } else if (value instanceof Number || value instanceof Boolean) {
                sb.append(value);
            } else if (value instanceof Map<?, ?> map) {
                sb.append('{');
                boolean first = true;
                for (Map.Entry<?, ?> entry : map.entrySet()) {
                    if (!first) sb.append(',');
                    first = false;
                    write(Objects.toString(entry.getKey()), sb);
                    sb.append(':');
                    write(entry.getValue(), sb);
                }
                sb.append('}');
            } else if (value instanceof List<?> list) {
                sb.append('[');
                boolean first = true;
                for (Object item : list) {
                    if (!first) sb.append(',');
                    first = false;
                    write(item, sb);
                }
                sb.append(']');
            } else {
                write(Objects.toString(value), sb);
            }
        }

        private static String escape(String s) {
            return s.replace("\\", "\\\\")
                    .replace("\"", "\\\"")
                    .replace("\n", "\\n")
                    .replace("\r", "\\r")
                    .replace("\t", "\\t");
        }

        static class Parser {
            private final String text;
            private int idx;

            Parser(String text) {
                this.text = text == null ? "" : text;
            }

            Object parse() {
                skipWs();
                Object val = parseValue();
                skipWs();
                return val;
            }

            private Object parseValue() {
                skipWs();
                if (idx >= text.length()) throw new IllegalArgumentException("invalid JSON");
                char c = text.charAt(idx);
                return switch (c) {
                    case '{' -> parseObject();
                    case '[' -> parseArray();
                    case '"' -> parseString();
                    case 't' -> parseLiteral("true", Boolean.TRUE);
                    case 'f' -> parseLiteral("false", Boolean.FALSE);
                    case 'n' -> parseLiteral("null", null);
                    default -> parseNumber();
                };
            }

            private Map<String, Object> parseObject() {
                expect('{');
                skipWs();
                Map<String, Object> map = new LinkedHashMap<>();
                if (peek('}')) {
                    idx++;
                    return map;
                }
                while (true) {
                    String key = parseString();
                    skipWs();
                    expect(':');
                    Object value = parseValue();
                    map.put(key, value);
                    skipWs();
                    if (peek(',')) {
                        idx++;
                        skipWs();
                        continue;
                    }
                    expect('}');
                    return map;
                }
            }

            private List<Object> parseArray() {
                expect('[');
                skipWs();
                List<Object> list = new ArrayList<>();
                if (peek(']')) {
                    idx++;
                    return list;
                }
                while (true) {
                    list.add(parseValue());
                    skipWs();
                    if (peek(',')) {
                        idx++;
                        skipWs();
                        continue;
                    }
                    expect(']');
                    return list;
                }
            }

            private String parseString() {
                expect('"');
                StringBuilder sb = new StringBuilder();
                while (idx < text.length()) {
                    char c = text.charAt(idx++);
                    if (c == '"') return sb.toString();
                    if (c == '\\') {
                        if (idx >= text.length()) throw new IllegalArgumentException("invalid escape");
                        char e = text.charAt(idx++);
                        switch (e) {
                            case '"' -> sb.append('"');
                            case '\\' -> sb.append('\\');
                            case '/' -> sb.append('/');
                            case 'b' -> sb.append('\b');
                            case 'f' -> sb.append('\f');
                            case 'n' -> sb.append('\n');
                            case 'r' -> sb.append('\r');
                            case 't' -> sb.append('\t');
                            case 'u' -> {
                                if (idx + 4 > text.length()) throw new IllegalArgumentException("invalid unicode escape");
                                String hex = text.substring(idx, idx + 4);
                                sb.append((char) Integer.parseInt(hex, 16));
                                idx += 4;
                            }
                            default -> throw new IllegalArgumentException("invalid escape sequence");
                        }
                    } else {
                        sb.append(c);
                    }
                }
                throw new IllegalArgumentException("unterminated string");
            }

            private Object parseNumber() {
                int start = idx;
                if (peek('-')) idx++;
                while (idx < text.length() && Character.isDigit(text.charAt(idx))) idx++;
                if (peek('.')) {
                    idx++;
                    while (idx < text.length() && Character.isDigit(text.charAt(idx))) idx++;
                }
                if (peek('e') || peek('E')) {
                    idx++;
                    if (peek('+') || peek('-')) idx++;
                    while (idx < text.length() && Character.isDigit(text.charAt(idx))) idx++;
                }
                String num = text.substring(start, idx);
                if (num.isEmpty() || "-".equals(num)) throw new IllegalArgumentException("invalid number");
                if (num.contains(".") || num.contains("e") || num.contains("E")) return Double.parseDouble(num);
                try {
                    return Integer.parseInt(num);
                } catch (NumberFormatException ex) {
                    return Long.parseLong(num);
                }
            }

            private Object parseLiteral(String token, Object value) {
                if (!text.startsWith(token, idx)) throw new IllegalArgumentException("invalid token");
                idx += token.length();
                return value;
            }

            private void skipWs() {
                while (idx < text.length() && Character.isWhitespace(text.charAt(idx))) idx++;
            }

            private void expect(char c) {
                if (idx >= text.length() || text.charAt(idx) != c) {
                    throw new IllegalArgumentException("expected '" + c + "'");
                }
                idx++;
            }

            private boolean peek(char c) {
                return idx < text.length() && text.charAt(idx) == c;
            }
        }
    }
}
