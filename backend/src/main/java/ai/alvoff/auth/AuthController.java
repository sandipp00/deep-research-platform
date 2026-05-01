package ai.alvoff.auth;

import ai.alvoff.auth.dto.AuthResponse;
import ai.alvoff.auth.dto.LoginRequest;
import ai.alvoff.auth.dto.RegisterRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class AuthController {

    private final AuthService auth;

    @PostMapping("/register")
    public AuthResponse register(@Valid @RequestBody RegisterRequest req) {
        return auth.register(req);
    }

    @PostMapping("/login")
    public AuthResponse login(@Valid @RequestBody LoginRequest req) {
        return auth.login(req);
    }

    @GetMapping("/me")
    public Map<String, Object> me(@AuthenticationPrincipal User user) {
        return Map.of(
            "id", user.getId(),
            "email", user.getEmail(),
            "name", user.getName()
        );
    }
}
