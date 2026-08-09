"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, User } from "lucide-react";
import { toast } from "sonner";
import Link from "next/link";

import { registerUser } from "@/lib/api";
import { useAuthStore } from "@/store/use-auth-store";
import { Input } from "@/components/ui/input";

export function SignupForm() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const { setSession } = useAuthStore();
  const router = useRouter();

  async function submitAuth(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const cleanEmail = email.trim().toLowerCase();
    
    if (!cleanEmail || !password) {
      toast.error("Email and password are required");
      return;
    }
    
    if (password.length < 6) {
      toast.error("Password must be at least 6 characters");
      return;
    }

    setLoading(true);
    try {
      const data = await registerUser(cleanEmail, password);
      setSession({
        token: data.token,
        user: { id: data.userId, email: data.email, role: data.role },
      });
      toast.success("Account created");
      router.push("/");
    } catch (err: any) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm">
      <div className="mb-5 flex rounded-xl bg-zinc-100 p-1">
        <Link href="/login" className="flex-1 rounded-lg py-2 text-sm font-medium transition-all text-zinc-500 hover:text-zinc-700 text-center">
          Sign in
        </Link>
        <div className="flex-1 rounded-lg py-2 text-sm font-medium transition-all bg-white text-zinc-900 shadow-sm text-center">
          Create account
        </div>
      </div>

      <form onSubmit={submitAuth} className="space-y-4">
        <div>
          <label className="mb-1.5 block text-xs font-medium text-zinc-600" htmlFor="email">
            Email address
          </label>
          <Input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="founder@example.com"
            autoComplete="email"
            className="rounded-lg border-zinc-200 bg-zinc-50 text-sm"
          />
        </div>
        <div>
          <label className="mb-1.5 block text-xs font-medium text-zinc-600" htmlFor="password">
            Password
          </label>
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Minimum 6 characters"
            autoComplete="new-password"
            className="rounded-lg border-zinc-200 bg-zinc-50 text-sm"
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-zinc-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-zinc-800 disabled:opacity-60"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <User className="h-4 w-4" />}
          Create account
        </button>
      </form>
    </div>
  );
}
