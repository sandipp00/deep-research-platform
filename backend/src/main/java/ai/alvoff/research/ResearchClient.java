package ai.alvoff.research;

import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.function.BiConsumer;

@Component
@RequiredArgsConstructor
@Slf4j
public class ResearchClient {

    private final ObjectMapper mapper;

    @Value("${app.research-agent.url}")
    private String agentUrl;

    private final HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(15))
        .build();

    /**
     * Stream SSE events from the Python agent. The consumer is invoked once per
     * complete event with (eventName, jsonDataString). Returns when the stream
     * closes (after `done` or `error`, or on connection close).
     */
    public void streamResearch(
        String query,
        List<Map<String, String>> history,
        BiConsumer<String, String> onEvent
    ) throws Exception {
        Map<String, Object> body = Map.of(
            "query", query,
            "conversation_history", history
        );
        HttpRequest req = HttpRequest.newBuilder()
            .uri(URI.create(agentUrl + "/research"))
            .timeout(Duration.ofMinutes(10))
            .header("Content-Type", "application/json")
            .header("Accept", "text/event-stream")
            .POST(HttpRequest.BodyPublishers.ofString(mapper.writeValueAsString(body)))
            .build();

        HttpResponse<InputStream> resp = client.send(req, HttpResponse.BodyHandlers.ofInputStream());
        if (resp.statusCode() / 100 != 2) {
            String err = new String(resp.body().readAllBytes(), StandardCharsets.UTF_8);
            throw new RuntimeException("Research agent returned " + resp.statusCode() + ": " + err);
        }

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(resp.body(), StandardCharsets.UTF_8))) {

            String currentEvent = null;
            StringBuilder dataBuf = new StringBuilder();
            String line;

            while ((line = reader.readLine()) != null) {
                if (line.isEmpty()) {
                    if (currentEvent != null && dataBuf.length() > 0) {
                        try {
                            onEvent.accept(currentEvent, dataBuf.toString());
                        } catch (Exception consumerErr) {
                            log.warn("SSE consumer threw: {}", consumerErr.getMessage());
                        }
                    }
                    currentEvent = null;
                    dataBuf.setLength(0);
                } else if (line.startsWith("event: ")) {
                    currentEvent = line.substring(7).trim();
                } else if (line.startsWith("data: ")) {
                    if (dataBuf.length() > 0) dataBuf.append("\n");
                    dataBuf.append(line.substring(6));
                }
                // ignore comments (": ...") and other lines
            }
        }
    }
}
