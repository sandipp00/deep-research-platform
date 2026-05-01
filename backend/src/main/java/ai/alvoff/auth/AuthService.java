package ai.alvoff.auth;

import ai.alvoff.auth.dto.AuthResponse;
import ai.alvoff.auth.dto.LoginRequest;
import ai.alvoff.auth.dto.RegisterRequest;
import lombok.RequiredArgsConstructor;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.http.HttpStatus.CONFLICT;
import static org.springframework.http.HttpStatus.UNAUTHORIZED;

@Service
@RequiredArgsConstructor
public class AuthService {

    private final UserRepository users;
    private final PasswordEncoder encoder;
    private final JwtService jwt;
    private final AuthenticationManager authManager;

    public AuthResponse register(RegisterRequest req) {
        if (users.existsByEmail(req.email())) {
            throw new ResponseStatusException(CONFLICT, "Email already registered");
        }
        User u = User.builder()
            .email(req.email().toLowerCase().trim())
            .passwordHash(encoder.encode(req.password()))
            .name(req.name().trim())
            .build();
        users.save(u);
        return new AuthResponse(jwt.generate(u), u.getId(), u.getEmail(), u.getName());
    }

    public AuthResponse login(LoginRequest req) {
        try {
            authManager.authenticate(
                new UsernamePasswordAuthenticationToken(req.email().toLowerCase().trim(), req.password())
            );
        } catch (BadCredentialsException e) {
            throw new ResponseStatusException(UNAUTHORIZED, "Invalid credentials");
        }
        User u = users.findByEmail(req.email().toLowerCase().trim())
            .orElseThrow(() -> new ResponseStatusException(UNAUTHORIZED, "Invalid credentials"));
        return new AuthResponse(jwt.generate(u), u.getId(), u.getEmail(), u.getName());
    }
}
