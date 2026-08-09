"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/use-auth-store";
import { SignupForm } from "@/components/auth/signup-form";

export default function SignupPage() {
  const { token, isReady } = useAuthStore();
  const router = useRouter();

  useEffect(() => {
    if (isReady && token) {
      router.replace("/");
    }
  }, [token, isReady, router]);

  if (!isReady || token) return null;

  return <SignupForm />;
}
