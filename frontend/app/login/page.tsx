import { Suspense } from "react";
import LoginForm from "./LoginForm";

export default function LoginPage() {
  return (
    <main className="mx-auto flex w-full min-w-0 max-w-sm flex-1 flex-col justify-center p-6">
      <h1 className="text-xl font-semibold text-navy-100">Admin sign in</h1>
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </main>
  );
}
