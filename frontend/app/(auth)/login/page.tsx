"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/use-auth-store";
import { LoginForm } from "@/components/auth/login-form";

export default function LoginPage() {
  const { token, isReady } = useAuthStore();
  const router = useRouter();

  useEffect(() => {
    if (isReady && token) {
      router.replace("/planner");
    }
  }, [token, isReady, router]);

  if (!isReady || token) return null;

  return <LoginForm />;
}
