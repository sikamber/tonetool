import { useState, type FormEvent } from "react";
import { ApiError } from "../api/client";
import { useLogin } from "../api/hooks";

const field = "mt-1 block w-full rounded-md border border-zinc-700 bg-zinc-950 px-3 py-2 text-zinc-100";

export function LoginPage() {
  const login = useLogin();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const messages = login.error instanceof ApiError ? login.error.messages : login.error ? [login.error.message] : [];

  const submit = (event: FormEvent) => {
    event.preventDefault();
    login.mutate({ username, password });
  };

  return (
    <form onSubmit={submit} className="mx-auto max-w-sm space-y-4 rounded-lg border border-zinc-800 bg-zinc-900 p-6">
      <h2 className="text-lg font-medium">Log in</h2>
      <label className="block text-sm text-zinc-400">
        Username
        <input
          name="username"
          autoComplete="username"
          autoFocus
          required
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className={field}
        />
      </label>
      <label className="block text-sm text-zinc-400">
        Password
        <input
          name="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={field}
        />
      </label>
      {messages.length > 0 && (
        <ul role="alert" className="space-y-1 text-sm text-red-400">
          {messages.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      )}
      <button
        type="submit"
        disabled={login.isPending}
        className="w-full rounded-md bg-amber-400 px-4 py-2 font-medium text-zinc-950 hover:bg-amber-300 disabled:opacity-50"
      >
        {login.isPending ? "Logging in…" : "Log in"}
      </button>
    </form>
  );
}
