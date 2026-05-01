package ai.alvoff.research;

import ai.alvoff.auth.User;
import ai.alvoff.conversation.Conversation;
import ai.alvoff.conversation.ConversationService;
import ai.alvoff.message.Message;
import ai.alvoff.message.MessageRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.Executors;

@RestController
@RequestMapping("/api/conversations/{id}")
@RequiredArgsConstructor
@Slf4j
public class ResearchController {

    private final ConversationService conversationService;
    private final MessageRepository messages;
    private final ResearchClient researchClient;
    private final ObjectMapper mapper;

    public record QueryRequest(@NotBlank @Size(max = 4000) String query) {}

    @PostMapping(value = "/query", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter query(
        @AuthenticationPrincipal User user,
        @PathVariable UUID id,
        @Valid @RequestBody QueryRequest req
    ) {
        Conversation conv = conversationService.getOwned(user, id);

        // Persist the user's message
        Message userMsg = Message.builder()
            .conversation(conv)
            .role(Message.Role.USER)
            .content(req.query())
            .build();
        messages.save(userMsg);

        // Auto-title from first user message
        if (conv.getTitle().equals("New chat")) {
            String title = req.query().length() > 60
                ? req.query().substring(0, 57) + "..."
                : req.query();
            conv.setTitle(title);
        }
        conversationService.touch(conv);

        // Build history for the agent (everything before this turn)
        List<Map<String, String>> history = new ArrayList<>();
        for (Message m : messages.findByConversationOrderByCreatedAtAsc(conv)) {
            if (m.getId().equals(userMsg.getId())) continue;
            history.add(Map.of(
                "role", m.getRole().name().toLowerCase(),
                "content", m.getContent() == null ? "" : m.getContent()
            ));
        }

        SseEmitter emitter = new SseEmitter(0L);  // no timeout, async runs forever
        var executor = Executors.newSingleThreadExecutor();

        // Send the persisted user-message id so the frontend can correlate
        try {
            emitter.send(SseEmitter.event()
                .name("user_message")
                .data(Map.of("id", userMsg.getId(), "createdAt", userMsg.getCreatedAt())));
        } catch (IOException e) {
            log.warn("Failed to emit user_message: {}", e.getMessage());
        }

        // Accumulate final assistant response
        final String[] finalText = {""};
        final List<Object>[] finalBlocks = new List[]{new ArrayList<>()};
        final List<String>[] finalSources = new List[]{new ArrayList<>()};
        final List<Object>[] finalFollowUps = new List[]{new ArrayList<>()};
        final boolean[] hasError = {false};
        final String[] errorMsg = {null};

        executor.execute(() -> {
            try {
                researchClient.streamResearch(req.query(), history, (eventName, dataJson) -> {
                    try {
                        // dataJson is already a JSON string; pass as plain text so Spring writes it raw,
                        // not double-encoded as a JSON string literal.
                        emitter.send(SseEmitter.event().name(eventName).data(dataJson));
                    } catch (IOException e) {
                        log.debug("Client disconnected during stream");
                    }

                    try {
                        JsonNode node = mapper.readTree(dataJson);
                        switch (eventName) {
                            case "blocks" -> {
                                JsonNode data = node.get("data");
                                if (data != null) {
                                    JsonNode blocks = data.get("blocks");
                                    if (blocks != null && blocks.isArray()) {
                                        finalBlocks[0] = mapper.convertValue(blocks, List.class);
                                        // First markdown block becomes the canonical text
                                        for (JsonNode b : blocks) {
                                            if ("markdown".equals(b.path("template_id").asText())) {
                                                finalText[0] = b.path("data").path("content").asText("");
                                                break;
                                            }
                                        }
                                    }
                                    JsonNode sources = data.get("sources");
                                    if (sources != null && sources.isArray()) {
                                        finalSources[0] = mapper.convertValue(sources, List.class);
                                    }
                                    JsonNode followUps = data.get("follow_ups");
                                    if (followUps != null && followUps.isArray()) {
                                        finalFollowUps[0] = mapper.convertValue(followUps, List.class);
                                    }
                                }
                            }
                            case "clarification" -> {
                                finalText[0] = node.path("content").asText("");
                            }
                            case "error" -> {
                                hasError[0] = true;
                                errorMsg[0] = node.path("content").asText("Unknown error");
                            }
                        }
                    } catch (Exception parseErr) {
                        log.debug("Failed to parse SSE event {}: {}", eventName, parseErr.getMessage());
                    }
                });

                // Persist assistant message
                Message assistant = Message.builder()
                    .conversation(conv)
                    .role(Message.Role.ASSISTANT)
                    .content(hasError[0] ? errorMsg[0] : finalText[0])
                    .blocks(finalBlocks[0])
                    .sources(finalSources[0])
                    .followUps(finalFollowUps[0])
                    .build();
                messages.save(assistant);
                conversationService.touch(conv);

                emitter.send(SseEmitter.event()
                    .name("persisted")
                    .data(Map.of("messageId", assistant.getId())));
                emitter.complete();

            } catch (Exception e) {
                log.error("Research stream failed", e);
                try {
                    emitter.send(SseEmitter.event()
                        .name("error")
                        .data(Map.of("status", "failed", "content", e.getMessage())));
                } catch (IOException ignored) {}
                emitter.completeWithError(e);
            } finally {
                executor.shutdown();
            }
        });

        emitter.onTimeout(() -> { emitter.complete(); executor.shutdownNow(); });
        emitter.onError((t) -> executor.shutdownNow());

        return emitter;
    }
}
