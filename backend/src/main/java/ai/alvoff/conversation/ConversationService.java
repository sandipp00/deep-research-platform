package ai.alvoff.conversation;

import ai.alvoff.auth.User;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;
import java.util.UUID;

import static org.springframework.http.HttpStatus.NOT_FOUND;

@Service
@RequiredArgsConstructor
public class ConversationService {

    private final ConversationRepository conversations;

    @Transactional(readOnly = true)
    public List<Conversation> listForUser(User user) {
        return conversations.findByUserOrderByUpdatedAtDesc(user);
    }

    @Transactional
    public Conversation create(User user, String title) {
        Conversation c = Conversation.builder()
            .user(user)
            .title(title == null || title.isBlank() ? "New chat" : title.trim())
            .build();
        return conversations.save(c);
    }

    @Transactional(readOnly = true)
    public Conversation getOwned(User user, UUID id) {
        return conversations.findByIdAndUser(id, user)
            .orElseThrow(() -> new ResponseStatusException(NOT_FOUND, "Conversation not found"));
    }

    @Transactional
    public void delete(User user, UUID id) {
        Conversation c = getOwned(user, id);
        conversations.delete(c);
    }

    @Transactional
    public void touch(Conversation c) {
        c.setUpdatedAt(java.time.Instant.now());
        conversations.save(c);
    }

    @Transactional
    public void rename(User user, UUID id, String title) {
        Conversation c = getOwned(user, id);
        if (title != null && !title.isBlank()) {
            c.setTitle(title.trim());
            conversations.save(c);
        }
    }
}
