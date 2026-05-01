package ai.alvoff.message;

import ai.alvoff.conversation.Conversation;
import io.hypersistence.utils.hibernate.type.json.JsonBinaryType;
import jakarta.persistence.*;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.hibernate.annotations.Type;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Entity
@Table(name = "messages")
@Getter @Setter
@NoArgsConstructor @AllArgsConstructor @Builder
public class Message {

    @Id
    @GeneratedValue
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "conversation_id", nullable = false)
    private Conversation conversation;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private Role role;

    @Column(columnDefinition = "TEXT")
    private String content;

    /** For assistant messages — array of block objects (template_id + data). Null for user messages. */
    @Type(JsonBinaryType.class)
    @Column(columnDefinition = "jsonb")
    private List<Object> blocks;

    /** For assistant messages — citation URLs. */
    @Type(JsonBinaryType.class)
    @Column(columnDefinition = "jsonb")
    private List<String> sources;

    /** For assistant messages — suggested follow-up queries. */
    @Type(JsonBinaryType.class)
    @Column(columnDefinition = "jsonb")
    private List<Object> followUps;

    @Column(nullable = false, updatable = false)
    private Instant createdAt;

    @PrePersist
    void onCreate() { createdAt = Instant.now(); }

    public enum Role { USER, ASSISTANT }
}
