/**
 * Attach the session token to every same-origin API call, in ONE place.
 *
 * There are 23 `fetch("/api/...")` call sites across the app. Threading a token
 * through all of them would work right up until one was missed — and a missed
 * call site is a page that silently 401s, which is exactly the kind of bug that
 * reaches production because the page it breaks is the one nobody clicked.
 *
 * So the token is attached by a single interceptor instead. It only touches
 * same-origin `/api/*` and `/flowise/*` requests, never anything else, and it
 * never overwrites an Authorization header a caller set deliberately.
 *
 * A 401 means the session is gone (expired, revoked, or the server restarted
 * with a cleared database). The interceptor clears the stored session and
 * notifies the app so it can show the login screen rather than leaving the user
 * looking at a page of failed requests.
 */
const TOKEN_KEY = "vitech_token";
export const SESSION_EXPIRED = "vitech:session-expired";

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private mode / storage disabled — the session simply won't persist */
  }
}

function isOurApi(url) {
  try {
    const u = new URL(url, window.location.origin);
    if (u.origin !== window.location.origin) return false;
    return u.pathname.startsWith("/api/") || u.pathname.startsWith("/flowise/");
  } catch {
    return false;
  }
}

let installed = false;

export function installAuthFetch() {
  if (installed || typeof window === "undefined") return;
  installed = true;
  const original = window.fetch.bind(window);

  window.fetch = async (input, init = {}) => {
    const url = typeof input === "string" ? input : input?.url || "";
    if (!isOurApi(url)) return original(input, init);

    const token = getToken();
    const headers = new Headers(
      init.headers || (typeof input !== "string" ? input.headers : undefined) || {}
    );
    if (token && !headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    const response = await original(input, { ...init, headers });

    // Do not fire on the login call itself: a wrong password is a 401 the login
    // form handles, not an expired session.
    if (response.status === 401 && !url.includes("/api/auth/login")) {
      setToken("");
      window.dispatchEvent(new CustomEvent(SESSION_EXPIRED));
    }
    return response;
  };
}
