package ai.alvoff.message.dto;

import ai.alvoff.message.Message;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record MessageDto(
    UUID id,
    String role,
    String content,
    List<Object> blocks,
    List<String> sources,
    List<Object> followUps,
    Instant createdAt
) {
    public static MessageDto from(Message m) {
        return new MessageDto(
            m.getId(),
            m.getRole().name().toLowerCase(),
            m.getContent(),
            m.getBlocks(),
            m.getSources(),
            m.getFollowUps(),
            m.getCreatedAt()
        );
    }
}
