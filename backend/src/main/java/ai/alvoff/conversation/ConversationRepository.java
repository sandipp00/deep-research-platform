package ai.alvoff.conversation;

import ai.alvoff.auth.User;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

public interface ConversationRepository extends JpaRepository<Conversation, UUID> {
    List<Conversation> findByUserOrderByUpdatedAtDesc(User user);
    Optional<Conversation> findByIdAndUser(UUID id, User user);
}
