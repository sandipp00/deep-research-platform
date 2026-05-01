package ai.alvoff.conversation;

import ai.alvoff.auth.User;
import ai.alvoff.conversation.dto.ConversationDto;
import ai.alvoff.conversation.dto.CreateConversationRequest;
import ai.alvoff.message.MessageRepository;
import ai.alvoff.message.dto.MessageDto;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/api/conversations")
@RequiredArgsConstructor
public class ConversationController {

    private final ConversationService service;
    private final MessageRepository messages;

    @GetMapping
    public List<ConversationDto> list(@AuthenticationPrincipal User user) {
        return service.listForUser(user).stream().map(ConversationDto::from).toList();
    }

    @PostMapping
    public ConversationDto create(
        @AuthenticationPrincipal User user,
        @Valid @RequestBody(required = false) CreateConversationRequest req
    ) {
        String title = (req == null) ? null : req.title();
        return ConversationDto.from(service.create(user, title));
    }

    @GetMapping("/{id}")
    public ConversationDto get(@AuthenticationPrincipal User user, @PathVariable UUID id) {
        return ConversationDto.from(service.getOwned(user, id));
    }

    @PatchMapping("/{id}")
    public ResponseEntity<Void> rename(
        @AuthenticationPrincipal User user,
        @PathVariable UUID id,
        @RequestBody Map<String, String> body
    ) {
        service.rename(user, id, body.get("title"));
        return ResponseEntity.noContent().build();
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@AuthenticationPrincipal User user, @PathVariable UUID id) {
        service.delete(user, id);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/{id}/messages")
    public List<MessageDto> listMessages(@AuthenticationPrincipal User user, @PathVariable UUID id) {
        Conversation c = service.getOwned(user, id);
        return messages.findByConversationOrderByCreatedAtAsc(c).stream()
            .map(MessageDto::from)
            .toList();
    }
}
