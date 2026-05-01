package ai.alvoff.auth.dto;

import java.util.UUID;

public record AuthResponse(
    String token,
    UUID id,
    String email,
    String name
) {}
