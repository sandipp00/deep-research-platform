import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Sparkles, Loader2 } from "lucide-react";
import { useAuth } from "@/store/auth";

export default function Register() {
  const nav = useNavigate();
  const register = useAuth((s) => s.register);
  const loading = useAuth((s) => s.loading);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErr(null);
    try {
      await register(email, password, name);
      nav("/");
    } catch (e: any) {
      setErr(e?.response?.data?.error || "Registration failed");
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className="w-full max-w-md glass-strong rounded-4xl p-8 shadow-glow"
      >
        <div className="flex items-center gap-2 mb-6">
          <div className="w-10 h-10 rounded-2xl bg-grad-vivid grid place-items-center">
            <Sparkles size={20} />
          </div>
          <div>
            <div className="font-display font-bold text-xl gradient-text leading-none">Lumen</div>
            <div className="text-xs text-zinc-400 mt-0.5">research, illuminated.</div>
          </div>
        </div>

        <h1 className="text-2xl font-display font-bold mb-1">Create your account</h1>
        <p className="text-zinc-400 text-sm mb-6">Free to try. No credit card needed.</p>

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="text-xs uppercase tracking-wider text-zinc-400">Name</label>
            <input
              className="field mt-1"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Your name"
              required
            />
          </div>
          <div>
            <label className="text-xs uppercase tracking-wider text-zinc-400">Email</label>
            <input
              className="field mt-1"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@domain.com"
              required
            />
          </div>
          <div>
            <label className="text-xs uppercase tracking-wider text-zinc-400">Password</label>
            <input
              className="field mt-1"
              type="password"
              autoComplete="new-password"
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              required
            />
          </div>
          {err && (
            <div className="text-sm text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded-xl px-3 py-2">
              {err}
            </div>
          )}
          <button className="btn-primary w-full" disabled={loading}>
            {loading ? <Loader2 className="animate-spin" size={18} /> : "Create account"}
          </button>
        </form>

        <div className="mt-6 text-sm text-zinc-400 text-center">
          Already have an account?{" "}
          <Link to="/login" className="text-accent-cyan hover:underline underline-offset-4">
            Sign in
          </Link>
        </div>
      </motion.div>
    </div>
  );
}
